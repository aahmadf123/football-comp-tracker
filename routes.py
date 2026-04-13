from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, Response
from flask_login import login_required, current_user
from models import db, Player, AuditLog, BudgetCap, PositionCap, PlayerHistory, PLAYER_STATUSES
from auth import role_required, log_audit
from utils import (
    import_csv, export_csv, sync_csv_to_disk, preview_csv_import,
    record_player_history, send_notification,
    VALID_POSITIONS, VALID_YEARS, VALID_CAMPUS, VALID_CONTRACT_LENGTHS,
    parse_currency,
)
from config import Config
from datetime import date
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

    # Status breakdown
    status_counts = {}
    for p in players:
        st = p.status or "Signed"
        status_counts[st] = status_counts.get(st, 0) + 1

    # Campus and contract breakdown
    on_campus = sum(1 for p in players if p.on_off_campus == "On")
    off_campus = sum(1 for p in players if p.on_off_campus == "Off")
    six_month = sum(1 for p in players if p.contract_length == "6 months")
    twelve_month = sum(1 for p in players if p.contract_length == "12 months")

    # Contract expiry alerts (within 60 days)
    expiring_contracts = []
    for p in players:
        days = p.days_until_expiry
        if days is not None and days <= 60:
            expiring_contracts.append({
                "id": p.id,
                "name": f"{p.first_name} {p.last_name}",
                "position": p.position or "",
                "days_until_expiry": days,
                "contract_end_date": p.contract_end_date.strftime("%m/%d/%Y") if p.contract_end_date else "",
                "status": p.status or "Signed",
            })
    expiring_contracts.sort(key=lambda x: x["days_until_expiry"])

    # Top 10 players by compensation
    top_players = sorted(players, key=lambda p: p.total or 0, reverse=True)[:10]

    # Budget cap
    budget_cap = BudgetCap.query.first()
    budget_pct = 0
    rev_share_pct = 0
    stipend_pct = 0
    if budget_cap and budget_cap.total_budget > 0:
        budget_pct = min(100, round(total_compensation / budget_cap.total_budget * 100, 1))
    if budget_cap and budget_cap.rev_share_budget > 0:
        rev_share_pct = min(100, round(total_rev_share / budget_cap.rev_share_budget * 100, 1))
    if budget_cap and budget_cap.stipend_budget > 0:
        stipend_pct = min(100, round(total_stipend / budget_cap.stipend_budget * 100, 1))

    # Position cap warnings
    pos_caps = {pc.position: pc.max_players for pc in PositionCap.query.all()}
    position_cap_warnings = []
    for pos, cnt in position_counts.items():
        cap = pos_caps.get(pos, 0)
        if cap > 0 and cnt >= cap:
            position_cap_warnings.append({"position": pos, "count": cnt, "max": cap})

    # Chart data (sorted for visualization)
    pos_chart = sorted(
        [{"pos": k, "total": v, "count": position_counts.get(k, 0)} for k, v in position_totals.items()],
        key=lambda x: x["total"], reverse=True
    )[:15]

    rev_chart = sorted(
        [{"pos": k, "rev": sum(p.rev_share or 0 for p in players if (p.position or "Unknown") == k),
          "stip": sum(p.stipend or 0 for p in players if (p.position or "Unknown") == k)}
         for k in position_counts],
        key=lambda x: x["rev"] + x["stip"], reverse=True
    )[:12]

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
        status_counts=status_counts,
        on_campus=on_campus,
        off_campus=off_campus,
        six_month=six_month,
        twelve_month=twelve_month,
        expiring_contracts=expiring_contracts,
        top_players=top_players,
        budget_cap=budget_cap,
        budget_pct=budget_pct,
        rev_share_pct=rev_share_pct,
        stipend_pct=stipend_pct,
        position_cap_warnings=position_cap_warnings,
        pos_chart=pos_chart,
        rev_chart=rev_chart,
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
        status_options=PLAYER_STATUSES,
        can_see_comp=current_user.can_see_compensation(),
    )


@main_bp.route("/api/players")
@login_required
def api_players():
    redact = not current_user.can_see_compensation()
    players = Player.query.order_by(Player.last_name, Player.first_name).all()
    return jsonify([p.to_dict(redact_comp=redact) for p in players])


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
    notes = str(data.get("notes", "")).strip()[:500]
    status = str(data.get("status", "Signed")).strip().title()
    if status not in PLAYER_STATUSES:
        status = "Signed"

    # Parse contract start date
    contract_start_date = None
    csd_raw = str(data.get("contract_start_date", "")).strip()
    if csd_raw:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                contract_start_date = date.fromisoformat(csd_raw) if fmt == "%Y-%m-%d" else None
                if fmt == "%Y-%m-%d":
                    contract_start_date = date.fromisoformat(csd_raw)
                    break
            except ValueError:
                pass

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
        contract_start_date=contract_start_date,
        stipend=stipend,
        total=rev_share + stipend,
        status=status,
        notes=notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.session.add(player)
    db.session.flush()  # get player.id before committing
    record_player_history(player, current_user.id)
    db.session.commit()

    log_audit(current_user.id, "create", "player", player.id,
              f"Added player: {first_name} {last_name}")
    send_notification(
        f"New Player Added: {first_name} {last_name}",
        f"{current_user.full_name} added {first_name} {last_name} ({position}, {year}) with total compensation ${player.total:,.2f}.",
    )

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

    for field in ["last_name", "first_name", "position", "year", "on_off_campus", "contract_length", "notes", "status"]:
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
            if field == "status":
                new_val = new_val.title()
                if new_val not in PLAYER_STATUSES:
                    new_val = "Signed"
            old_val = getattr(player, field)
            if old_val != new_val:
                changes.append(f"{field}: '{old_val}' → '{new_val}'")
                setattr(player, field, new_val)

    # Handle contract_start_date
    if "contract_start_date" in data:
        csd_raw = str(data["contract_start_date"]).strip()
        new_csd = None
        if csd_raw:
            try:
                new_csd = date.fromisoformat(csd_raw)
            except ValueError:
                pass
        if player.contract_start_date != new_csd:
            changes.append(f"contract_start_date: '{player.contract_start_date}' → '{new_csd}'")
            player.contract_start_date = new_csd

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
    if changes:
        record_player_history(player, current_user.id)
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
    send_notification(
        f"Player Deleted: {name}",
        f"{current_user.full_name} deleted player {name} from the roster.",
    )

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
            send_notification(
                "CSV Roster Upload",
                f"{current_user.full_name} uploaded a CSV with {count} players {'(replaced all data)' if replace else '(appended)'}.",
            )
            flash(f"Successfully imported {count} players.", "success")
            return redirect(url_for("main.players"))

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


# --- Import Preview ---

@main_bp.route("/api/import-preview", methods=["POST"])
@role_required("admin")
def api_import_preview():
    if "csv_file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["csv_file"]
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only CSV files accepted"}), 400
    result = preview_csv_import(file.stream)
    return jsonify(result)


# --- Player Profile ---

@main_bp.route("/players/<int:player_id>/profile")
@login_required
def player_profile(player_id):
    player = Player.query.get_or_404(player_id)
    history = player.history.order_by(PlayerHistory.changed_at.asc()).all()
    can_see_comp = current_user.can_see_compensation()
    return render_template("player_profile.html", player=player, history=history,
                           can_see_comp=can_see_comp)


# --- Player History API ---

@main_bp.route("/api/players/<int:player_id>/history")
@login_required
def api_player_history(player_id):
    if not current_user.can_see_compensation():
        return jsonify({"error": "Permission denied"}), 403
    player = Player.query.get_or_404(player_id)
    history = player.history.order_by(PlayerHistory.changed_at.asc()).all()
    return jsonify([h.to_dict() for h in history])


# --- Contract Expiry Alerts API ---

@main_bp.route("/api/contract-alerts")
@login_required
def api_contract_alerts():
    players = Player.query.all()
    alerts = []
    for p in players:
        days = p.days_until_expiry
        if days is not None and days <= 60:
            alerts.append({
                "id": p.id,
                "name": f"{p.first_name} {p.last_name}",
                "position": p.position or "",
                "days_until_expiry": days,
                "contract_end_date": p.contract_end_date.strftime("%m/%d/%Y") if p.contract_end_date else "",
                "status": p.status or "Signed",
            })
    alerts.sort(key=lambda x: x["days_until_expiry"])
    return jsonify(alerts)


# --- Depth Chart ---

@main_bp.route("/depth-chart")
@login_required
def depth_chart():
    players_by_position = {}
    for pos in VALID_POSITIONS:
        group = Player.query.filter_by(position=pos).order_by(Player.year, Player.last_name).all()
        if group:
            players_by_position[pos] = group
    can_see_comp = current_user.can_see_compensation()
    return render_template("depth_chart.html", players_by_position=players_by_position,
                           positions=VALID_POSITIONS, can_see_comp=can_see_comp)


# --- Budget Cap ---

@main_bp.route("/budget-cap")
@role_required("admin", "gm")
def budget_cap_page():
    cap = BudgetCap.query.first()
    players = Player.query.all()
    total_spent = sum(p.total or 0 for p in players)
    rev_share_spent = sum(p.rev_share or 0 for p in players)
    stipend_spent = sum(p.stipend or 0 for p in players)
    pos_caps = {pc.position: pc.max_players for pc in PositionCap.query.all()}
    position_counts = {}
    for p in players:
        pos = p.position or "Unknown"
        position_counts[pos] = position_counts.get(pos, 0) + 1
    return render_template(
        "budget_cap.html",
        cap=cap,
        pos_caps=pos_caps,
        positions=VALID_POSITIONS,
        total_spent=total_spent,
        rev_share_spent=rev_share_spent,
        stipend_spent=stipend_spent,
        position_counts=position_counts,
    )


@main_bp.route("/api/budget-cap", methods=["GET"])
@login_required
def api_get_budget_cap():
    if not current_user.can_manage_caps():
        return jsonify({"error": "Permission denied"}), 403
    cap = BudgetCap.query.first()
    if not cap:
        return jsonify({"total_budget": 0, "rev_share_budget": 0, "stipend_budget": 0, "season": "2025-2026"})
    return jsonify({
        "id": cap.id, "season": cap.season,
        "total_budget": cap.total_budget,
        "rev_share_budget": cap.rev_share_budget,
        "stipend_budget": cap.stipend_budget,
    })


@main_bp.route("/api/budget-cap", methods=["PUT"])
@role_required("admin", "gm")
def api_update_budget_cap():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    cap = BudgetCap.query.first()
    if not cap:
        cap = BudgetCap()
        db.session.add(cap)
    cap.season = str(data.get("season", "2025-2026"))[:20]
    cap.total_budget = parse_currency(data.get("total_budget", 0))
    cap.rev_share_budget = parse_currency(data.get("rev_share_budget", 0))
    cap.stipend_budget = parse_currency(data.get("stipend_budget", 0))
    cap.updated_by = current_user.id
    db.session.commit()
    log_audit(current_user.id, "update", "budget_cap", cap.id,
              f"Budget cap set: ${cap.total_budget:,.2f} total")
    return jsonify({"message": "Budget cap updated"})


@main_bp.route("/api/position-caps", methods=["GET"])
@login_required
def api_get_position_caps():
    if not current_user.can_manage_caps():
        return jsonify({"error": "Permission denied"}), 403
    caps = PositionCap.query.all()
    return jsonify({pc.position: pc.max_players for pc in caps})


@main_bp.route("/api/position-caps", methods=["PUT"])
@role_required("admin", "gm")
def api_update_position_caps():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    for pos, max_count in data.items():
        if pos not in VALID_POSITIONS:
            continue
        pc = PositionCap.query.filter_by(position=pos).first()
        if not pc:
            pc = PositionCap(position=pos)
            db.session.add(pc)
        pc.max_players = max(0, int(max_count))
    db.session.commit()
    log_audit(current_user.id, "update", "position_caps", None, "Position caps updated")
    return jsonify({"message": "Position caps updated"})
