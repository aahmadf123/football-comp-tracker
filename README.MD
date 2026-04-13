# University of Toledo Football Compensation Tracker

A secure web application for tracking, managing, and reporting football player compensation data.

## Features

- **Role-Based Access Control** — Admin, Coach, General Manager with different permissions
- **CSV Upload/Export** — Import and export player data via CSV (read/write)
- **Full CRUD** — Add, edit, delete players with inline editing
- **Sortable & Filterable** — Sort by any column, filter by position/year/campus/contract
- **Dashboard** — Summary stats, charts, compensation breakdowns
- **Audit Trail** — Every change is logged with user, timestamp, and IP
- **Security** — Password hashing (bcrypt), CSRF protection, rate limiting, session management, XSS prevention
- **Auto-Calculate** — Total = Rev Share + Stipend, computed automatically
- **Responsive Design** — Works on desktop, tablet, and mobile
- **Print-Friendly** — Clean print layout for reports
- **University of Toledo Branding** — Midnight Blue & Gold theme

## Tech Stack

- **Backend:** Python 3 + Flask
- **Database:** SQLite
- **Frontend:** Bootstrap 5, DataTables, jQuery
- **Auth:** Flask-Login + bcrypt
- **Security:** Flask-WTF (CSRF), Flask-Limiter (rate limiting)

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
python app.py

# 3. Open browser
# http://127.0.0.1:5000
```

## Default Login

| Username | Password       | Role  |
|----------|----------------|-------|
| admin    | Rockets2024!   | Admin |

**Change the default password immediately after first login.**

## User Roles

| Role  | View | Add | Edit | Delete | Upload CSV | Manage Users | Audit Log |
|-------|------|-----|------|--------|------------|--------------|-----------|
| Admin | ✅   | ✅  | ✅   | ✅     | ✅         | ✅           | ✅        |
| GM    | ✅   | ✅  | ✅   | ✅     | ❌         | ❌           | ✅        |
| Coach | ✅   | ✅  | ✅   | ❌     | ❌         | ❌           | ❌        |

## CSV Format

```
Last Name,First Name,Position,Year,On/Off Campus,Rev Share $,Contract Length,Stipend,Total
Smith,John,QB,JR,On,$5000.00,12 months,$1500.00,$6500.00
```
