import csv
import io
import os
import secrets
import time
from collections import defaultdict

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from backend.database import engine, Base, get_db
from backend.models import Team, Registration

Base.metadata.create_all(bind=engine)

SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# docs_url/redoc_url/openapi_url=None -> don't expose the API structure publicly.
app = FastAPI(
    title="無人機足球研習營報名系統",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# https_only=True -> session cookie is only sent over HTTPS (Railway enforces TLS).
app.add_middleware(
    SessionMiddleware, secret_key=SESSION_SECRET, max_age=3600, https_only=True
)

templates = Jinja2Templates(directory="backend/templates")


# ── security helpers ──────────────────────────────────────────────────────

def client_ip(request: Request) -> str:
    """Best-effort real client IP (Railway sits behind a proxy)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# In-memory rate limiting. The app runs as a single uvicorn worker, so a plain
# dict is sufficient; it resets on redeploy, which is acceptable here.
_login_fails = defaultdict(list)
_register_hits = defaultdict(list)

LOGIN_MAX = 5            # failed admin logins...
LOGIN_WINDOW = 300       # ...within 5 min -> locked out for the rest of the window
REGISTER_MAX = 40        # registrations... (loose enough for group sign-ups on shared Wi-Fi)
REGISTER_WINDOW = 60     # ...per minute per IP


def _recent(stamps, window):
    now = time.time()
    return [t for t in stamps if now - t < window]


def login_locked(ip):
    _login_fails[ip] = _recent(_login_fails[ip], LOGIN_WINDOW)
    return len(_login_fails[ip]) >= LOGIN_MAX


def record_login_fail(ip):
    _login_fails[ip].append(time.time())


def clear_login_fails(ip):
    _login_fails.pop(ip, None)


def register_rate_ok(ip):
    _register_hits[ip] = _recent(_register_hits[ip], REGISTER_WINDOW)
    if len(_register_hits[ip]) >= REGISTER_MAX:
        return False
    _register_hits[ip].append(time.time())
    return True


# Per-field length caps. SQLite ignores VARCHAR(n), so enforce here to stop
# oversized payloads filling the volume / polluting the data.
MAX_LEN = {
    "name": 50, "gender": 4, "birth_date": 20, "taiwan_passport": 30,
    "tw_id": 20, "phone": 30, "first_time_in_china": 4, "diet_type": 6,
    "team_name": 60, "organization": 100, "team_code": 20,
}


def check_lengths(**fields):
    return all(
        v is None or len(v) <= MAX_LEN.get(k, 100) for k, v in fields.items()
    )


def csv_safe(value):
    """Neutralise CSV/Excel formula injection by prefixing risky leading chars."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


# Self-service lookup rate limit (needs both ID + phone, but still throttle).
_lookup_hits = defaultdict(list)
LOOKUP_MAX = 10
LOOKUP_WINDOW = 60


def lookup_rate_ok(ip):
    _lookup_hits[ip] = _recent(_lookup_hits[ip], LOOKUP_WINDOW)
    if len(_lookup_hits[ip]) >= LOOKUP_MAX:
        return False
    _lookup_hits[ip].append(time.time())
    return True


def find_duplicate(db, tw_id, taiwan_passport):
    """A person counts as already registered if either ID already exists."""
    return (
        db.query(Registration)
        .filter(
            (Registration.tw_id == tw_id)
            | (Registration.taiwan_passport == taiwan_passport)
        )
        .first()
    )


def reg_number(reg):
    return f"DSR-{reg.id:05d}"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


def require_admin(request: Request):
    if not request.session.get("admin_logged_in"):
        raise HTTPException(status_code=303, detail="Redirecting to login")


# ── public routes ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/register/leader", response_class=HTMLResponse)
def register_leader_form(request: Request):
    return templates.TemplateResponse(request, "register_leader.html")


@app.post("/register/leader")
def register_leader_submit(
    request: Request,
    name: str = Form(...),
    gender: str = Form(...),
    birth_date: str = Form(...),
    taiwan_passport: str = Form(...),
    tw_id: str = Form(...),
    phone: str = Form(...),
    first_time_in_china: str = Form(...),
    diet_type: str = Form(...),
    no_beef: bool = Form(False),
    team_name: str = Form(...),
    organization: str = Form(""),
    db: Session = Depends(get_db),
):
    if not register_rate_ok(client_ip(request)):
        return templates.TemplateResponse(
            request, "register_leader.html",
            {"error": "操作過於頻繁，請稍候再試。"}, status_code=429,
        )
    if not check_lengths(
        name=name, gender=gender, birth_date=birth_date,
        taiwan_passport=taiwan_passport, tw_id=tw_id, phone=phone,
        first_time_in_china=first_time_in_china, diet_type=diet_type,
        team_name=team_name, organization=organization,
    ):
        return templates.TemplateResponse(
            request, "register_leader.html",
            {"error": "輸入資料長度超過限制，請確認後重試。"}, status_code=400,
        )
    if find_duplicate(db, tw_id, taiwan_passport):
        return templates.TemplateResponse(
            request, "register_leader.html",
            {"error": "此身分證字號或台胞證號已報名過，請勿重複報名。如需查詢請至「查詢報名」頁面。"},
            status_code=400,
        )

    team = Team(team_code=Team.generate_code(db), team_name=team_name)
    db.add(team)
    db.flush()

    reg = Registration(
        role="leader",
        name=name,
        gender=gender,
        birth_date=birth_date,
        taiwan_passport=taiwan_passport,
        tw_id=tw_id,
        phone=phone,
        first_time_in_china=first_time_in_china,
        diet_type=diet_type,
        no_beef=no_beef,
        organization=organization or None,
        team_id=team.id,
    )
    db.add(reg)
    db.commit()

    return templates.TemplateResponse(request, "success.html", {
        "reg_no": reg_number(reg),
        "team_code": team.team_code,
        "team_name": team.team_name,
        "role": "領隊",
    })


@app.get("/register/member", response_class=HTMLResponse)
def register_member_form(request: Request):
    return templates.TemplateResponse(request, "register_member.html")


@app.post("/register/member")
def register_member_submit(
    request: Request,
    name: str = Form(...),
    gender: str = Form(...),
    birth_date: str = Form(...),
    taiwan_passport: str = Form(...),
    tw_id: str = Form(...),
    phone: str = Form(...),
    first_time_in_china: str = Form(...),
    diet_type: str = Form(...),
    no_beef: bool = Form(False),
    team_code: str = Form(...),
    db: Session = Depends(get_db),
):
    if not register_rate_ok(client_ip(request)):
        return templates.TemplateResponse(
            request, "register_member.html",
            {"error": "操作過於頻繁，請稍候再試。"}, status_code=429,
        )
    if not check_lengths(
        name=name, gender=gender, birth_date=birth_date,
        taiwan_passport=taiwan_passport, tw_id=tw_id, phone=phone,
        first_time_in_china=first_time_in_china, diet_type=diet_type,
        team_code=team_code,
    ):
        return templates.TemplateResponse(
            request, "register_member.html",
            {"error": "輸入資料長度超過限制，請確認後重試。"}, status_code=400,
        )
    if find_duplicate(db, tw_id, taiwan_passport):
        return templates.TemplateResponse(
            request, "register_member.html",
            {"error": "此身分證字號或台胞證號已報名過，請勿重複報名。如需查詢請至「查詢報名」頁面。"},
            status_code=400,
        )

    team = db.query(Team).filter(Team.team_code == team_code).first()
    if not team:
        return templates.TemplateResponse(request, "register_member.html", {
            "error": f"隊伍代碼「{team_code}」不存在，請確認後重試。",
        })

    reg = Registration(
        role="member",
        name=name,
        gender=gender,
        birth_date=birth_date,
        taiwan_passport=taiwan_passport,
        tw_id=tw_id,
        phone=phone,
        first_time_in_china=first_time_in_china,
        diet_type=diet_type,
        no_beef=no_beef,
        team_id=team.id,
    )
    db.add(reg)
    db.commit()

    return templates.TemplateResponse(request, "success.html", {
        "reg_no": reg_number(reg),
        "team_code": team.team_code,
        "team_name": team.team_name,
        "role": "學員",
    })


# ── self-service lookup ──────────────────────────────────────────────────

@app.get("/lookup", response_class=HTMLResponse)
def lookup_form(request: Request):
    return templates.TemplateResponse(request, "lookup.html")


@app.post("/lookup", response_class=HTMLResponse)
def lookup_submit(
    request: Request,
    tw_id: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    if not lookup_rate_ok(client_ip(request)):
        return templates.TemplateResponse(
            request, "lookup.html",
            {"error": "查詢過於頻繁，請稍候再試。"}, status_code=429,
        )
    # Require BOTH id + phone to match -> avoids single-field enumeration.
    reg = (
        db.query(Registration)
        .filter(Registration.tw_id == tw_id, Registration.phone == phone)
        .first()
    )
    if not reg:
        return templates.TemplateResponse(request, "lookup.html", {
            "error": "查無資料，請確認身分證字號與手機號碼是否與報名時一致。",
        })
    team = reg.team
    return templates.TemplateResponse(request, "lookup.html", {
        "result": {
            "reg_no": reg_number(reg),
            "name": reg.name,
            "role": "領隊" if reg.role == "leader" else "學員",
            "team_code": team.team_code if team else "",
            "team_name": team.team_name if team else "",
            "created_at": reg.created_at.strftime("%Y-%m-%d %H:%M") if reg.created_at else "",
        },
    })


# ── admin routes ────────────────────────────────────────────────────────

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_form(request: Request):
    if request.session.get("admin_logged_in"):
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse(request, "admin_login.html")


@app.post("/admin/login")
def admin_login_submit(request: Request, password: str = Form(...)):
    ip = client_ip(request)
    if login_locked(ip):
        return templates.TemplateResponse(
            request, "admin_login.html",
            {"error": "登入嘗試次數過多，請於 5 分鐘後再試。"}, status_code=429,
        )
    if secrets.compare_digest(password, ADMIN_PASSWORD):
        clear_login_fails(ip)
        request.session["admin_logged_in"] = True
        return RedirectResponse("/admin", status_code=302)
    record_login_fail(ip)
    return templates.TemplateResponse(request, "admin_login.html", {
        "error": "密碼錯誤",
    })


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


@app.post("/admin/delete/{reg_id}")
def admin_delete(request: Request, reg_id: int, db: Session = Depends(get_db)):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse("/admin/login", status_code=302)

    reg = db.get(Registration, reg_id)
    if reg:
        team = reg.team
        db.delete(reg)
        # If this was the last member of its team, drop the empty team too.
        if team is not None:
            remaining = (
                db.query(Registration)
                .filter(Registration.team_id == team.id, Registration.id != reg_id)
                .count()
            )
            if remaining == 0:
                db.delete(team)
        db.commit()
    return RedirectResponse("/admin", status_code=302)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse("/admin/login", status_code=302)

    registrations = (
        db.query(Registration, Team.team_code, Team.team_name)
        .outerjoin(Team, Registration.team_id == Team.id)
        .order_by(Registration.created_at.desc())
        .all()
    )
    stats = {
        "total": db.query(Registration).count(),
        "leaders": db.query(Registration).filter(Registration.role == "leader").count(),
        "members": db.query(Registration).filter(Registration.role == "member").count(),
        "teams": db.query(Team).count(),
    }
    return templates.TemplateResponse(request, "admin_dashboard.html", {
        "registrations": registrations,
        "stats": stats,
    })


@app.get("/admin/export.csv")
def admin_export_csv(request: Request, db: Session = Depends(get_db)):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse("/admin/login", status_code=302)

    rows = (
        db.query(Registration, Team.team_code, Team.team_name)
        .outerjoin(Team, Registration.team_id == Team.id)
        .order_by(Registration.created_at.asc())
        .all()
    )

    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output)
    writer.writerow([
        "序號", "身份", "隊伍代碼", "隊伍名稱", "姓名", "性別",
        "出生年月", "台胞證號", "台灣身分證號", "手機號碼",
        "首次來大陸", "葷/素", "不吃牛肉", "所屬單位", "報名時間",
    ])
    for idx, (reg, team_code, team_name) in enumerate(rows, start=1):
        writer.writerow([csv_safe(v) for v in (
            idx,
            "領隊" if reg.role == "leader" else "學員",
            team_code or "",
            team_name or "",
            reg.name,
            reg.gender,
            reg.birth_date,
            reg.taiwan_passport or "",
            reg.tw_id,
            reg.phone,
            reg.first_time_in_china,
            reg.diet_type,
            "是" if reg.no_beef else "否",
            reg.organization or "",
            reg.created_at.strftime("%Y-%m-%d %H:%M") if reg.created_at else "",
        )])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=registrations.csv"},
    )
