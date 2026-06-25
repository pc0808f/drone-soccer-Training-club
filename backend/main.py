import csv
import io
import os
import secrets

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

app = FastAPI(title="無人機足球研習營報名系統")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=3600)

templates = Jinja2Templates(directory="backend/templates")


# ── helpers ──────────────────────────────────────────────────────────────

def require_admin(request: Request):
    if not request.session.get("admin_logged_in"):
        raise HTTPException(status_code=303, detail="Redirecting to login")


# ── public routes ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/register/leader", response_class=HTMLResponse)
def register_leader_form(request: Request):
    return templates.TemplateResponse("register_leader.html", {"request": request})


@app.post("/register/leader")
def register_leader_submit(
    request: Request,
    name: str = Form(...),
    gender: str = Form(...),
    birth_date: str = Form(...),
    taiwan_passport: str = Form(""),
    tw_id: str = Form(...),
    phone: str = Form(...),
    first_time_in_china: str = Form(...),
    diet_type: str = Form(...),
    no_beef: bool = Form(False),
    team_name: str = Form(...),
    organization: str = Form(""),
    db: Session = Depends(get_db),
):
    team = Team(team_code=Team.generate_code(db), team_name=team_name)
    db.add(team)
    db.flush()

    reg = Registration(
        role="leader",
        name=name,
        gender=gender,
        birth_date=birth_date,
        taiwan_passport=taiwan_passport or None,
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

    return templates.TemplateResponse("success.html", {
        "request": request,
        "team_code": team.team_code,
        "team_name": team.team_name,
        "role": "領隊",
    })


@app.get("/register/member", response_class=HTMLResponse)
def register_member_form(request: Request):
    return templates.TemplateResponse("register_member.html", {"request": request})


@app.post("/register/member")
def register_member_submit(
    request: Request,
    name: str = Form(...),
    gender: str = Form(...),
    birth_date: str = Form(...),
    taiwan_passport: str = Form(""),
    tw_id: str = Form(...),
    phone: str = Form(...),
    first_time_in_china: str = Form(...),
    diet_type: str = Form(...),
    no_beef: bool = Form(False),
    team_code: str = Form(...),
    db: Session = Depends(get_db),
):
    team = db.query(Team).filter(Team.team_code == team_code).first()
    if not team:
        return templates.TemplateResponse("register_member.html", {
            "request": request,
            "error": f"隊伍代碼「{team_code}」不存在，請確認後重試。",
        })

    reg = Registration(
        role="member",
        name=name,
        gender=gender,
        birth_date=birth_date,
        taiwan_passport=taiwan_passport or None,
        tw_id=tw_id,
        phone=phone,
        first_time_in_china=first_time_in_china,
        diet_type=diet_type,
        no_beef=no_beef,
        team_id=team.id,
    )
    db.add(reg)
    db.commit()

    return templates.TemplateResponse("success.html", {
        "request": request,
        "team_code": team.team_code,
        "team_name": team.team_name,
        "role": "學員",
    })


# ── admin routes ────────────────────────────────────────────────────────

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_form(request: Request):
    if request.session.get("admin_logged_in"):
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.post("/admin/login")
def admin_login_submit(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["admin_logged_in"] = True
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("admin_login.html", {
        "request": request,
        "error": "密碼錯誤",
    })


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


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
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
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
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "序號", "身份", "隊伍代碼", "隊伍名稱", "姓名", "性別",
        "出生年月", "台胞證號", "台灣身分證號", "手機號碼",
        "首次來大陸", "葷/素", "不吃牛肉", "所屬單位", "報名時間",
    ])
    for idx, (reg, team_code, team_name) in enumerate(rows, start=1):
        writer.writerow([
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
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=registrations.csv"},
    )
