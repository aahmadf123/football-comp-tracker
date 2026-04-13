import csv
import os
import io
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models import db, Player
from datetime import datetime


CSV_COLUMNS = [
    "Last Name",
    "First Name",
    "Position",
    "Year",
    "On/Off Campus",
    "Rev Share $",
    "Contract Length",
    "Contract Start Date",
    "Stipend",
    "Total",
    "Status",
]

VALID_POSITIONS = [
    "QB", "RB", "WR", "TE", "OL", "OT", "OG", "C",
    "DL", "DE", "DT", "LB", "CB", "S", "FS", "SS",
    "K", "P", "LS", "KR", "PR", "ATH", "OLB", "ILB",
    "MLB", "NT", "WLB", "SLB", "DB", "H", "EDGE",
]

VALID_YEARS = ["FR", "SO", "JR", "SR", "RS FR", "RS SO", "RS JR", "RS SR", "GR"]

VALID_CAMPUS = ["On", "Off"]

VALID_CONTRACT_LENGTHS = ["6 months", "12 months"]


def parse_currency(value):
    """Parse a currency string like '$1,234.56' into a float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def validate_row(row, row_num):
    """Validate a CSV row and return (cleaned_data, errors)."""
    from models import PLAYER_STATUSES
    errors = []

    last_name = row.get("Last Name", "").strip()
    first_name = row.get("First Name", "").strip()
    position = row.get("Position", "").strip().upper()
    year = row.get("Year", "").strip().upper()
    campus = row.get("On/Off Campus", "").strip().title()
    rev_share = parse_currency(row.get("Rev Share $", 0))
    contract_raw = row.get("Contract Length", "").strip()
    stipend = parse_currency(row.get("Stipend", 0))
    status_raw = row.get("Status", "Signed").strip().title()
    contract_start_raw = row.get("Contract Start Date", "").strip()

    if not last_name:
        errors.append(f"Row {row_num}: Last Name is required.")
    if not first_name:
        errors.append(f"Row {row_num}: First Name is required.")
    if position and position not in VALID_POSITIONS:
        errors.append(f"Row {row_num}: Invalid position '{position}'.")
    if year and year not in VALID_YEARS:
        errors.append(f"Row {row_num}: Invalid year '{year}'.")
    if campus and campus not in VALID_CAMPUS:
        errors.append(f"Row {row_num}: On/Off Campus must be 'On' or 'Off'.")

    # Normalize contract length
    contract_length = ""
    if "12" in str(contract_raw):
        contract_length = "12 months"
    elif "6" in str(contract_raw):
        contract_length = "6 months"
    elif contract_raw:
        errors.append(f"Row {row_num}: Contract Length must be '6 months' or '12 months'.")

    if rev_share < 0:
        errors.append(f"Row {row_num}: Rev Share cannot be negative.")
    if stipend < 0:
        errors.append(f"Row {row_num}: Stipend cannot be negative.")

    # Normalize status
    status = status_raw if status_raw in PLAYER_STATUSES else "Signed"

    # Parse contract start date
    contract_start_date = None
    if contract_start_raw:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
            try:
                from datetime import date
                contract_start_date = datetime.strptime(contract_start_raw, fmt).date()
                break
            except ValueError:
                continue

    total = rev_share + stipend

    cleaned = {
        "last_name": last_name,
        "first_name": first_name,
        "position": position,
        "year": year,
        "on_off_campus": campus,
        "rev_share": rev_share,
        "contract_length": contract_length,
        "contract_start_date": contract_start_date,
        "stipend": stipend,
        "total": total,
        "status": status,
    }
    return cleaned, errors


def import_csv(file_stream, user_id, replace=False):
    """Import players from a CSV file stream. Returns (count, errors)."""
    errors = []
    players_data = []

    try:
        content = file_stream.read().decode("utf-8-sig")  # Handle BOM
        reader = csv.DictReader(io.StringIO(content))

        # Validate headers
        if reader.fieldnames:
            headers = [h.strip() for h in reader.fieldnames]
            required = {"Last Name", "First Name"}
            if not required.issubset(set(headers)):
                return 0, [f"CSV must contain at least these headers: {', '.join(required)}"]

        for i, row in enumerate(reader, start=2):
            cleaned, row_errors = validate_row(row, i)
            if row_errors:
                errors.extend(row_errors)
            else:
                players_data.append(cleaned)

    except UnicodeDecodeError:
        return 0, ["File encoding error. Please save your CSV as UTF-8."]
    except csv.Error as e:
        return 0, [f"CSV parsing error: {str(e)}"]

    if errors:
        return 0, errors

    # If replacing, delete all existing players
    if replace:
        Player.query.delete()

    # Insert validated players
    for data in players_data:
        player = Player(
            last_name=data["last_name"],
            first_name=data["first_name"],
            position=data["position"],
            year=data["year"],
            on_off_campus=data["on_off_campus"],
            rev_share=data["rev_share"],
            contract_length=data["contract_length"],
            contract_start_date=data.get("contract_start_date"),
            stipend=data["stipend"],
            total=data["total"],
            status=data.get("status", "Signed"),
            created_by=user_id,
            updated_by=user_id,
        )
        db.session.add(player)

    db.session.commit()
    return len(players_data), errors


def export_csv():
    """Export all players to a CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)

    players = Player.query.order_by(Player.last_name, Player.first_name).all()
    for p in players:
        writer.writerow([
            p.last_name,
            p.first_name,
            p.position,
            p.year,
            p.on_off_campus,
            f"${p.rev_share:,.2f}" if p.rev_share else "$0.00",
            p.contract_length,
            p.contract_start_date.isoformat() if p.contract_start_date else "",
            f"${p.stipend:,.2f}" if p.stipend else "$0.00",
            f"${p.total:,.2f}" if p.total else "$0.00",
            p.status or "Signed",
        ])

    return output.getvalue()


def preview_csv_import(file_stream):
    """Parse CSV and return preview without committing to DB."""
    errors = []
    new_players = []
    update_players = []

    try:
        content = file_stream.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))

        if reader.fieldnames:
            headers = [h.strip() for h in reader.fieldnames]
            required = {"Last Name", "First Name"}
            if not required.issubset(set(headers)):
                return {"errors": [f"CSV must have at least: {', '.join(required)}"], "new": [], "update": []}

        for i, row in enumerate(reader, start=2):
            cleaned, row_errors = validate_row(row, i)
            if row_errors:
                errors.extend(row_errors)
                continue

            existing = Player.query.filter(
                db.func.lower(Player.last_name) == cleaned["last_name"].lower(),
                db.func.lower(Player.first_name) == cleaned["first_name"].lower(),
            ).first()

            entry = {
                "last_name": cleaned["last_name"],
                "first_name": cleaned["first_name"],
                "position": cleaned["position"],
                "year": cleaned["year"],
                "rev_share": cleaned["rev_share"],
                "stipend": cleaned["stipend"],
                "total": cleaned["total"],
                "status": cleaned.get("status", "Signed"),
            }
            if existing:
                entry["existing_total"] = existing.total or 0
                update_players.append(entry)
            else:
                new_players.append(entry)

    except UnicodeDecodeError:
        return {"errors": ["File encoding error. Please save as UTF-8."], "new": [], "update": []}
    except csv.Error as e:
        return {"errors": [f"CSV parsing error: {str(e)}"], "new": [], "update": []}

    return {"new": new_players, "update": update_players, "errors": errors}


def record_player_history(player, changed_by_id):
    """Snapshot current player state into history."""
    from models import PlayerHistory
    snap = PlayerHistory(
        player_id=player.id,
        changed_by=changed_by_id,
        rev_share=player.rev_share,
        stipend=player.stipend,
        total=player.total,
        status=player.status,
        position=player.position,
        year=player.year,
        notes=player.notes,
    )
    db.session.add(snap)


def send_notification(subject, body):
    """Send email to all admin/gm users. Silent no-op if MAIL_SERVER not configured."""
    from flask import current_app
    from models import User
    cfg = current_app.config
    mail_server = cfg.get("MAIL_SERVER", "")
    if not mail_server:
        return

    try:
        users = User.query.filter(
            User.role.in_(["admin", "gm"]),
            User.is_active_user == True,
        ).all()
        recipients = [u.email for u in users if u.email]
        if not recipients:
            return

        sender = cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("MAIL_USERNAME", "noreply@localhost")
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = f"[UT Football Tracker] {subject}"
        msg.attach(MIMEText(body, "plain"))

        port = int(cfg.get("MAIL_PORT", 587))
        with smtplib.SMTP(mail_server, port, timeout=5) as server:
            if cfg.get("MAIL_USE_TLS", True):
                server.starttls()
            username = cfg.get("MAIL_USERNAME", "")
            password = cfg.get("MAIL_PASSWORD", "")
            if username and password:
                server.login(username, password)
            server.sendmail(sender, recipients, msg.as_string())
    except Exception:
        pass  # Never crash the app for email failures


def sync_csv_to_disk(csv_path):
    """Write current player data to CSV file on disk."""
    csv_content = export_csv()
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        f.write(csv_content)
