from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from models import db, User, AuditLog
from datetime import datetime
import bcrypt
import re

auth_bp = Blueprint("auth", __name__)


# --- Forms ---

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Password", validators=[DataRequired()])


class CreateUserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm Password", validators=[DataRequired(), EqualTo("password", message="Passwords must match")]
    )
    role = SelectField("Role", choices=[("coach", "Coach"), ("gm", "General Manager"), ("admin", "Admin")])

    def validate_username(self, field):
        if not re.match(r'^[a-zA-Z0-9_]+$', field.data):
            raise ValidationError("Username can only contain letters, numbers, and underscores.")
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Username already exists.")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("Email already registered.")

    def validate_password(self, field):
        password = field.data
        if not re.search(r'[A-Z]', password):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', password):
            raise ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'[0-9]', password):
            raise ValidationError("Password must contain at least one digit.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValidationError("Password must contain at least one special character.")


class EditUserForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=120)])
    role = SelectField("Role", choices=[("coach", "Coach"), ("gm", "General Manager"), ("admin", "Admin")])
    is_active = BooleanField("Active")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match")]
    )


# --- Helpers ---

def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def log_audit(user_id, action, entity_type, entity_id=None, details=None):
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=request.remote_addr,
    )
    db.session.add(log)
    db.session.commit()


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("main.dashboard"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


# --- Routes ---

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user and user.is_active_user and check_password(form.password.data, user.password_hash):
            login_user(user, remember=False)
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_audit(user.id, "login", "user", user.id, "User logged in")
            flash(f"Welcome back, {user.full_name}!", "success")
            next_page = request.args.get("next")
            # Prevent open redirect
            if next_page and not next_page.startswith("/"):
                next_page = None
            return redirect(next_page or url_for("main.dashboard"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    log_audit(current_user.id, "logout", "user", current_user.id, "User logged out")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not check_password(form.current_password.data, current_user.password_hash):
            flash("Current password is incorrect.", "danger")
        else:
            current_user.password_hash = hash_password(form.new_password.data)
            db.session.commit()
            log_audit(current_user.id, "update", "user", current_user.id, "Password changed")
            flash("Password updated successfully.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("change_password.html", form=form)


# --- User Management (Admin Only) ---

@auth_bp.route("/users")
@role_required("admin")
def manage_users():
    users = User.query.order_by(User.username).all()
    return render_template("users.html", users=users)


@auth_bp.route("/users/create", methods=["GET", "POST"])
@role_required("admin")
def create_user():
    form = CreateUserForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data,
            password_hash=hash_password(form.password.data),
            role=form.role.data,
        )
        db.session.add(user)
        db.session.commit()
        log_audit(current_user.id, "create", "user", user.id, f"Created user: {user.username} ({user.role})")
        flash(f"User '{user.username}' created successfully.", "success")
        return redirect(url_for("auth.manage_users"))
    return render_template("create_user.html", form=form)


@auth_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = EditUserForm(obj=user)

    if form.validate_on_submit():
        # Check email uniqueness for other users
        existing = User.query.filter(User.email == form.email.data, User.id != user_id).first()
        if existing:
            flash("Email already registered to another user.", "danger")
        else:
            user.email = form.email.data
            user.full_name = form.full_name.data
            user.role = form.role.data
            user.is_active_user = form.is_active.data
            db.session.commit()
            log_audit(current_user.id, "update", "user", user.id, f"Updated user: {user.username}")
            flash(f"User '{user.username}' updated.", "success")
            return redirect(url_for("auth.manage_users"))
    elif request.method == "GET":
        form.is_active.data = user.is_active_user

    return render_template("edit_user.html", form=form, user=user)


@auth_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@role_required("admin")
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    # Reset to a temporary password
    temp_password = "Rockets2024!"
    user.password_hash = hash_password(temp_password)
    db.session.commit()
    log_audit(current_user.id, "update", "user", user.id, f"Password reset for: {user.username}")
    flash(f"Password for '{user.username}' reset to temporary password: {temp_password}", "warning")
    return redirect(url_for("auth.manage_users"))
