from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


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
    contract_length = db.Column(db.String(20), nullable=False)  # "6 months" or "12 months"
    stipend = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def calculate_total(self):
        self.total = (self.rev_share or 0.0) + (self.stipend or 0.0)

    def to_dict(self):
        return {
            "id": self.id,
            "last_name": self.last_name,
            "first_name": self.first_name,
            "position": self.position,
            "year": self.year,
            "on_off_campus": self.on_off_campus,
            "rev_share": self.rev_share,
            "contract_length": self.contract_length,
            "stipend": self.stipend,
            "total": self.total,
            "notes": self.notes or "",
            "updated_at": self.updated_at.strftime("%m/%d/%Y %I:%M %p") if self.updated_at else "",
        }

    def __repr__(self):
        return f"<Player {self.first_name} {self.last_name}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # create, update, delete, upload, login, logout
    entity_type = db.Column(db.String(50), nullable=False)  # player, user, csv
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", backref="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} by User {self.user_id}>"
