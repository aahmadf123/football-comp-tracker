import csv
import os
import io
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
    "Stipend",
    "Total",
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
    errors = []

    last_name = row.get("Last Name", "").strip()
    first_name = row.get("First Name", "").strip()
    position = row.get("Position", "").strip().upper()
    year = row.get("Year", "").strip().upper()
    campus = row.get("On/Off Campus", "").strip().title()
    rev_share = parse_currency(row.get("Rev Share $", 0))
    contract_raw = row.get("Contract Length", "").strip()
    stipend = parse_currency(row.get("Stipend", 0))

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

    total = rev_share + stipend

    cleaned = {
        "last_name": last_name,
        "first_name": first_name,
        "position": position,
        "year": year,
        "on_off_campus": campus,
        "rev_share": rev_share,
        "contract_length": contract_length,
        "stipend": stipend,
        "total": total,
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
            stipend=data["stipend"],
            total=data["total"],
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
            f"${p.stipend:,.2f}" if p.stipend else "$0.00",
            f"${p.total:,.2f}" if p.total else "$0.00",
        ])

    return output.getvalue()


def sync_csv_to_disk(csv_path):
    """Write current player data to CSV file on disk."""
    csv_content = export_csv()
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        f.write(csv_content)
