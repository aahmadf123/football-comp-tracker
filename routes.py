from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, Response
from flask_login import login_required, current_user
from models import db, Player, AuditLog
from auth import role_required, log_audit
from utils import (
    import_csv, export_csv, sync_csv_to_disk,
    VALID_POSITIONS, VALID_YEARS, VALID_CAMPUS, VALID_CONTRACT_LENGTHS,
    parse_currency,
)
from config import Config
import os
import re

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    players = Player.query.all()
    total_players = len(players)
    total_compensation = sum(p.total or 0 for p in players)
    total_rev_share = sum(p.rev_share or 0 for p in players)
    total_stipend = sum(p.stipend or 0 for p in players)

    # Position breakdown
    position_counts = {}
    position_totals = {}
    for p in players:
        pos = p.position or "Unknown"
        position_counts[pos] = position_counts.get(pos, 0) + 1
        position_totals[pos] = position_totals.get(pos, 0) + (p.total or 0)

    # Year breakdown
    year_counts = {}
    for p in players:
        yr = p.year or "Unknown"
        year_counts[yr] = year_counts.get(yr, 0) + 1

    # Campus breakdown
    on_campus = sum(1 for p in players if p.on_off_campus == "On")
    off_campus = sum(1 for p in players if p.on_off_campus == "Off")

    # Contract breakdown
    six_month = sum(1 for p in players if p.contract_length == "6 months")
    twelve_month = sum(1 for p in players if p.contract_length == "12 months")

    # Recent activity
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()

    return render_template(
        "dashboard.html",
        total_players=total_players,
        total_compensation=total_compensation,
        total_rev_share=total_rev_share,
        total_stipend=total_stipend,
        position_counts=position_counts,
        position_totals=position_totals,
        year_counts=year_counts,
        on_campus=on_campus,
        off_campus=off_campus,
        six_month=six_month,
        twelve_month=twelve_month,
        recent_logs=recent_logs,
    )


# --- Player CRUD ---

@main_bp.route("/players")
@login_required
def players():
    return render_template(
        "players.html",
        positions=VALID_POSITIONS,
        years=VALID_YEARS,
        campus_options=VALID_CAMPUS,
        contract_options=VALID_CONTRACT_LENGTHS,
    )


@main_bp.route("/api/players")
@login_required
def api_players():
    players = Player.query.order_by(Player.last_name, Player.first_name).all()
    return jsonify([p.to_dict() for p in players])


@main_bp.route("/api/players", methods=["POST"])
@login_required
def api_add_player():
    if not current_user.can_add_players():
        return jsonify({"error": "Permission denied"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate required fields
    last_name = str(data.get("last_name", "")).strip()
    first_name = str(data.get("first_name", "")).strip()
    if not last_name or not first_name:
        return jsonify({"error": "First Name and Last Name are required"}), 400

    # Validate and sanitize inputs
    position = str(data.get("position", "")).strip().upper()
    year = str(data.get("year", "")).strip().upper()
    on_off_campus = str(data.get("on_off_campus", "")).strip().title()
    contract_length = str(data.get("contract_length", "")).strip()
    rev_share = parse_currency(data.get("rev_share", 0))
    stipend = parse_currency(data.get("stipend", 0))
    notes = str(data.get("notes", "")).strip()[:500]  # Limit notes length

    # Sanitize text inputs to prevent XSS
    last_name = re.sub(r'[<>"\']', '', last_name)[:100]
    first_name = re.sub(r'[<>"\']', '', first_name)[:100]

    if rev_share < 0 or stipend < 0:
        return jsonify({"error": "Monetary values cannot be negative"}), 400

    player = Player(
        last_name=last_name,
        first_name=first_name,
        position=position,
        year=year,
        on_off_campus=on_off_campus,
        rev_share=rev_share,
        contract_length=contract_length,
        stipend=stipend,
        total=rev_share + stipend,
        notes=notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.session.add(player)
    db.session.commit()

    log_audit(current_user.id, "create", "player", player.id,
              f"Added player: {first_name} {last_name}")

    # Sync to CSV
    sync_csv_to_disk(Config.CSV_FILE)

    return jsonify(player.to_dict()), 201


@main_bp.route("/api/players/<int:player_id>", methods=["PUT"])
@login_required
def api_update_player(player_id):
    if not current_user.can_edit_players():
        return jsonify({"error": "Permission denied"}), 403

    player = Player.query.get_or_404(player_id)
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Track changes for audit
    changes = []

    for field in ["last_name", "first_name", "position", "year", "on_off_campus", "contract_length", "notes"]:
        if field in data:
            new_val = str(data[field]).strip()
            if field in ("last_name", "first_name"):
                new_val = re.sub(r'[<>"\']', '', new_val)[:100]
            if field == "position":
                new_val = new_val.upper()
            if field == "year":
                new_val = new_val.upper()
            if field == "on_off_campus":
                new_val = new_val.title()
            if field == "notes":
                new_val = new_val[:500]
            old_val = getattr(player, field)
            if old_val != new_val:
                changes.append(f"{field}: '{old_val}' → '{new_val}'")
                setattr(player, field, new_val)

    for field in ["rev_share", "stipend"]:
        if field in data:
            new_val = parse_currency(data[field])
            if new_val < 0:
                return jsonify({"error": f"{field} cannot be negative"}), 400
            old_val = getattr(player, field)
            if old_val != new_val:
                changes.append(f"{field}: ${old_val:,.2f} → ${new_val:,.2f}")
                setattr(player, field, new_val)

    player.calculate_total()
    player.updated_by = current_user.id
    db.session.commit()

    if changes:
        log_audit(current_user.id, "update", "player", player.id,
                  f"Updated {player.first_name} {player.last_name}: {'; '.join(changes)}")

    # Sync to CSV
    sync_csv_to_disk(Config.CSV_FILE)

    return jsonify(player.to_dict())


@main_bp.route("/api/players/<int:player_id>", methods=["DELETE"])
@login_required
def api_delete_player(player_id):
    if not current_user.can_delete_players():
        return jsonify({"error": "Permission denied. Only Admin and GM can delete players."}), 403

    player = Player.query.get_or_404(player_id)
    name = f"{player.first_name} {player.last_name}"
    db.session.delete(player)
    db.session.commit()

    log_audit(current_user.id, "delete", "player", player_id, f"Deleted player: {name}")

    # Sync to CSV
    sync_csv_to_disk(Config.CSV_FILE)

    return jsonify({"message": f"Player '{name}' deleted successfully"})


# --- CSV Upload/Export ---

@main_bp.route("/upload", methods=["GET", "POST"])
@role_required("admin")
def upload_csv():
    if request.method == "POST":
        if "csv_file" not in request.files:
            flash("No file selected.", "danger")
            return redirect(url_for("main.upload_csv"))

        file = request.files["csv_file"]
        if file.filename == "":
            flash("No file selected.", "danger")
            return redirect(url_for("main.upload_csv"))

        if not file.filename.lower().endswith(".csv"):
            flash("Only CSV files are accepted.", "danger")
            return redirect(url_for("main.upload_csv"))

        replace = request.form.get("replace_data") == "on"
        count, errors = import_csv(file.stream, current_user.id, replace=replace)

        if errors:
            for error in errors[:20]:  # Limit displayed errors
                flash(error, "danger")
            if len(errors) > 20:
                flash(f"... and {len(errors) - 20} more errors.", "danger")
        else:
            log_audit(current_user.id, "upload", "csv", None,
                      f"Uploaded CSV: {count} players {'(replaced)' if replace else '(appended)'}")
            # Sync to disk
            sync_csv_to_disk(Config.CSV_FILE)
            flash(f"Successfully imported {count} players.", "success")

        return redirect(url_for("main.upload_csv"))

    return render_template("upload.html")


@main_bp.route("/export")
@login_required
def export():
    csv_content = export_csv()
    log_audit(current_user.id, "export", "csv", None, "Exported player data to CSV")
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=players_export.csv"},
    )


# --- Audit Log ---

@main_bp.route("/audit-log")
@role_required("admin", "gm")
def audit_log():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template("audit_log.html", logs=logs)
