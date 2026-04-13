from datetime import datetime, date, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

PLAYER_STATUSES = ["Offered", "Negotiating", "Signed", "Declined"]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="coach")  # admin, coach, gm
    full_name = db.Column(db.String(120), nullable=False)
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.is_active_user

    def has_role(self, role):
        return self.role == role

    def can_upload_csv(self):
        return self.role == "admin"

    def can_manage_users(self):
        return self.role == "admin"

    def can_edit_players(self):
        return self.role in ("admin", "coach", "gm")

    def can_delete_players(self):
        return self.role in ("admin", "gm")

    def can_add_players(self):
        return self.role in ("admin", "coach", "gm")

    def can_see_compensation(self):
        return self.role in ("admin", "gm")

    def can_manage_caps(self):
        return self.role in ("admin", "gm")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(100), nullable=False, index=True)
    first_name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(20), nullable=False)
    year = db.Column(db.String(20), nullable=False)
    on_off_campus = db.Column(db.String(20), nullable=False)
    rev_share = db.Column(db.Float, default=0.0)
    contract_length = db.Column(db.String(20), nullable=False)
    contract_start_date = db.Column(db.Date, nullable=True)
    stipend = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="Signed")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def calculate_total(self):
        self.total = (self.rev_share or 0.0) + (self.stipend or 0.0)

    @property
    def contract_end_date(self):
        if not self.contract_start_date or not self.contract_length:
            return None
        days = 365 if "12" in self.contract_length else 182
        return self.contract_start_date + timedelta(days=days)

    @property
    def days_until_expiry(self):
        end = self.contract_end_date
        if end is None:
            return None
        return (end - date.today()).days

    def to_dict(self, redact_comp=False):
        return {
            "id": self.id,
            "last_name": self.last_name,
            "first_name": self.first_name,
            "position": self.position or "",
            "year": self.year or "",
            "on_off_campus": self.on_off_campus or "",
            "rev_share": 0 if redact_comp else (self.rev_share or 0),
            "contract_length": self.contract_length or "",
            "contract_start_date": self.contract_start_date.isoformat() if self.contract_start_date else "",
            "stipend": 0 if redact_comp else (self.stipend or 0),
            "total": 0 if redact_comp else (self.total or 0),
            "status": self.status or "Signed",
            "notes": self.notes or "",
            "updated_at": self.updated_at.strftime("%m/%d/%Y %I:%M %p") if self.updated_at else "",
            "days_until_expiry": self.days_until_expiry,
            "contract_end_date": self.contract_end_date.isoformat() if self.contract_end_date else "",
            "redacted": redact_comp,
        }

    def __repr__(self):
        return f"<Player {self.first_name} {self.last_name}>"


class PlayerHistory(db.Model):
    __tablename__ = "player_history"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    rev_share = db.Column(db.Float, default=0.0)
    stipend = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20))
    position = db.Column(db.String(20))
    year = db.Column(db.String(20))
    notes = db.Column(db.Text)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    player = db.relationship(
        "Player", backref=db.backref("history", cascade="all, delete-orphan", lazy="dynamic")
    )
    changed_by_user = db.relationship("User", foreign_keys=[changed_by])

    def to_dict(self):
        return {
            "id": self.id,
            "rev_share": self.rev_share or 0,
            "stipend": self.stipend or 0,
            "total": self.total or 0,
            "status": self.status or "Signed",
            "position": self.position or "",
            "year": self.year or "",
            "changed_at": self.changed_at.strftime("%m/%d/%Y %I:%M %p") if self.changed_at else "",
            "changed_by": self.changed_by_user.full_name if self.changed_by_user else "System",
        }


class BudgetCap(db.Model):
    __tablename__ = "budget_caps"

    id = db.Column(db.Integer, primary_key=True)
    season = db.Column(db.String(20), nullable=False, default="2025-2026")
    total_budget = db.Column(db.Float, default=0.0)
    rev_share_budget = db.Column(db.Float, default=0.0)
    stipend_budget = db.Column(db.Float, default=0.0)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    updated_by_user = db.relationship("User", foreign_keys=[updated_by])


class PositionCap(db.Model):
    __tablename__ = "position_caps"

    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.String(20), unique=True, nullable=False, index=True)
    max_players = db.Column(db.Integer, default=0)  # 0 = no limit


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} by User {self.user_id}>"
