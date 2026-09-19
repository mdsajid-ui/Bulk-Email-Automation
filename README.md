# DV Analytics &bull; LMS Assignment Report & Bulk Email Automator 🚀

[![GitHub Pages](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-success?style=for-the-badge&logo=github)](https://mdsajid-ui.github.io/Bulk-Email-Automation/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![Fast & Modern](https://img.shields.io/badge/UI-TailwindCSS-indigo?style=for-the-badge&logo=tailwindcss)](https://tailwindcss.com)

A web application designed for education teams to automate **Weekly LMS Assignment Evaluation Reports** and **1-Click Bulk Email Dispatching**.

🔗 **Live Web Dashboard:** [https://mdsajid-ui.github.io/Bulk-Email-Automation/](https://mdsajid-ui.github.io/Bulk-Email-Automation/)

---

## 🌟 Key Capabilities

### 1. Weekly LMS Assignment Reporting
- **Multi-Format Ingestion**: Parses LMS exports in any format: `.xls` (HTML table exports), `.xlsx`, or `.csv` (e.g. `Assignment (10).xls` with **13,590+ rows**).
- **Candidate Aggregation**: Groups submissions by candidate (`Student ID`, `Student Name`, `Batch`), tracking:
  - Total assignments completed (e.g. `14 submissions`)
  - Modules covered (e.g. `Python Programming`, `SQL Server`, `Excel Base & Advanced`)
  - Latest submission details & timestamps
- **Auto-Linked Student Directory**: Pre-loaded with **6,390 students** from the master database, automatically resolving student emails by Student ID and Name.
- **Inline Email Editing**: Missing an email? Edit or add any student's email address with 1 click right in the table.
- **1-Click Report Dispatch**:
  - **Individual Candidate Send**: Click **"Send Report"** on any candidate to email them immediately.
  - **Send All Pending**: 1-click batch dispatch for all active students in the selected batch.
- **Interactive Report Preview**: Inspect the exact branded, responsive HTML report email before sending.

### 2. General Bulk Email Automator
- Broadcast any file attachments (PDFs, docs, images, spreadsheets, archives) to 100+ recipients simultaneously in 1 click.
- Upload recipient lists via CSV or Excel (`.xlsx`, `.xls`) or paste emails directly.
- Downloadable **Sample CSV** and **Sample Excel** templates generated in 1 click.
- SMTP presets for **Gmail**, **Microsoft 365 / Outlook**, and **Custom SMTP**.
- Safety pacing interval (0.5s to 5s) to safeguard against provider spam rate limits.
- Downloadable CSV delivery report receipts.

---

## 🚀 How to Run

### Method 1: Use Live on GitHub Pages (No installation needed)
Open the deployed dashboard directly in your browser:
👉 **[https://mdsajid-ui.github.io/Bulk-Email-Automation/](https://mdsajid-ui.github.io/Bulk-Email-Automation/)**

- Drop your weekly LMS file (`.xls`, `.xlsx`, `.csv`) directly into the browser.
- The web app parses all records, matches student emails, and generates preview reports completely client-side!

### Method 2: One-Click Launch on Windows (Local Python Engine)
1. Clone or download this repository.
2. Double-click **`run.bat`** in the project folder.
3. Your default web browser will automatically open [http://127.0.0.1:5000](http://127.0.0.1:5000).

### Method 3: Command Line
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
py app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## 📁 Repository Structure
```text
├── index.html                 # Root single-page application for GitHub Pages
├── app.py                     # Flask backend server with REST & streaming APIs
├── assignment_processor.py    # LMS report parser, candidate aggregator & HTML report builder
├── student_directory.py       # Student master database seed & lookup engine
├── student_directory.json     # Pre-compiled student master directory (2,000+ verified emails)
├── sample_recipients.csv      # Sample CSV template
├── sample_recipients.xlsx     # Sample Excel template
├── run.bat                    # One-click Windows batch launcher
├── requirements.txt           # Python package requirements
├── templates/
│   └── index.html             # Server-rendered template mirror
└── tests/
    ├── test_bulk_email.py         # Test suite for bulk email engine
    └── test_assignment_report.py  # Test suite for LMS assignment processor
```

---

## 🧪 Testing & Verification
Run the automated test suite with pytest:
```bash
py -m pytest -v
```
All 6 automated tests verify email validation, MIME construction with attachments, LMS file parsing (13,590 rows), student master directory lookups, and API endpoints.

---

## 📄 License
Created for DV Data & Analytics Pvt Ltd. All rights reserved.
