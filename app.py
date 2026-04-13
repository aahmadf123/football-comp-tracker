import os
from datetime import datetime
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
from models import db, User
from auth import auth_bp, hash_password
from routes import main_bp


def _run_migrations(engine):
    """Add new columns to existing tables without dropping data (SQLite compatible)."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE players ADD COLUMN status VARCHAR(20) DEFAULT 'Signed'",
        "ALTER TABLE players ADD COLUMN contract_start_date DATE",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists — safe to ignore


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure directories exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["DATA_FOLDER"], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    csrf = CSRFProtect(app)

    # Rate limiting on login to prevent brute force
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )
    limiter.limit("5 per minute")(auth_bp)

    # AJAX requests use X-CSRFToken header (set in base.html), which Flask-WTF checks automatically

    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Template context
    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow}

    # Security headers
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # Create database tables and default admin user
    with app.app_context():
        db.create_all()
        _run_migrations(db.engine)
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                email="admin@rockets.utoledo.edu",
                full_name="System Administrator",
                password_hash=hash_password("Rockets2024!"),
                role="admin",
            )
            db.session.add(admin)
            db.session.commit()
            print(">>> Default admin user created.")
            print(">>> Username: admin")
            print(">>> Password: Rockets2024!")
            print(">>> CHANGE THIS PASSWORD IMMEDIATELY after first login!")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="127.0.0.1", port=5000)
