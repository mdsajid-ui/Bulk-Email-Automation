# Bulk Email Automator ✉️

A modern, fast, and secure web application designed to send bulk emails to 100+ recipients with attachments in a single click.

---

## Features
- **One-Click Send**: Attach any file (PDF, Word, Excel, Images, Zip, etc.) and dispatch it to hundreds of recipients simultaneously.
- **Recipient Ingestion**:
  - Drag & drop CSV or Excel spreadsheets (`.xlsx`, `.xls`, `.csv`).
  - Direct paste option for comma, semicolon, or newline-separated email addresses.
  - Automatic email validation and duplicate removal.
- **Personalization**:
  - Insert dynamic tags into subject and body like `{{name}}` or `{{company}}` matching your spreadsheet columns.
- **SMTP Support & Presets**:
  - One-click presets for **Gmail**, **Microsoft 365 / Outlook**, and **Custom SMTP**.
  - Built-in **Test Connection** button to verify credentials before sending.
  - Rate-limiting delay controls (0.2s, 1s, 2s, 5s) to avoid spam filters.
- **Real-Time Monitoring**:
  - Live progress bar with percentage.
  - Live activity feed showing each recipient, status (sent/failed), timestamp, and error messages.
  - Emergency cancel/stop button.
  - Downloadable CSV delivery report.
- **Dry-Run Mode**:
  - Simulate email blasts without actually emailing recipients to preview the process safely.

---

## Quick Start (How to Run)

### Method 1: Double-Click (Windows)
Double click `run.bat` in this folder. It will start the server and open `http://localhost:5000` automatically in your default browser.

### Method 2: Command Line
Open a terminal in this directory:
```bash
py app.py
```
Then visit [http://127.0.0.1:5000](http://127.0.0.1:5000) in your web browser.

---

## Email Provider Setup Tips

### 1. Gmail
- **SMTP Host**: `smtp.gmail.com`
- **Port**: `587` (STARTTLS)
- **Email**: Your Gmail address
- **Password**: A 16-character **App Password** (Generate at: Google Account > Security > 2-Step Verification > App passwords).

### 2. Microsoft 365 / Outlook
- **SMTP Host**: `smtp.office365.com`
- **Port**: `587` (STARTTLS)
- **Email**: Your Microsoft 365 / Outlook email
- **Password**: Your password or App Password.

---

## File Structure
- `app.py`: Flask application server and REST / SSE streaming endpoints.
- `email_engine.py`: SMTP engine with attachment caching, rate pacing, and background worker threads.
- `templates/index.html`: Responsive, modern single-page dashboard.
- `static/app.js`: Frontend logic for file uploads, live status streaming, and alerts.
- `sample_recipients.csv`: Sample CSV file ready for testing.
- `test_bulk_email.py`: Pytest test suite.
- `run.bat`: Quick launcher for Windows.
