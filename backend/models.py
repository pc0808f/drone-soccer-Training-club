import random
import string
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from backend.database import Base


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    team_code = Column(String(20), unique=True, nullable=False, index=True)
    team_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    members = relationship("Registration", back_populates="team")

    @classmethod
    def generate_code(cls, db):
        prefix = "DST"
        while True:
            suffix = "".join(random.choices(string.digits, k=4))
            code = f"{prefix}-{suffix}"
            if not db.query(cls).filter(cls.team_code == code).first():
                return code


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    gender = Column(String(10), nullable=False)
    birth_date = Column(String(20), nullable=False)
    taiwan_passport = Column(String(50), nullable=True)
    tw_id = Column(String(20), nullable=False)
    phone = Column(String(20), nullable=False)
    first_time_in_china = Column(String(10), nullable=False)
    diet_type = Column(String(10), nullable=False)
    no_beef = Column(Boolean, default=False)
    organization = Column(String(100), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    team = relationship("Team", back_populates="members")
