# Candidate Assignment Reports & Bulk Email Automator 🚀

[![GitHub Pages](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-success?style=for-the-badge&logo=github)](https://mdsajid-ui.github.io/Candidate-Assignment-Reports/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![Fast & Modern](https://img.shields.io/badge/UI-TailwindCSS-indigo?style=for-the-badge&logo=tailwindcss)](https://tailwindcss.com)

A web application designed for training and education teams to automate **Weekly LMS Assignment Evaluation Reports**, **Industrial Tool Milestone Tracking (Excel, SQL, Python, Power BI, Tableau, Machine Learning)**, and **1-Click Bulk Email Dispatching**.

🔗 **Live GitHub Pages Dashboard:** [https://mdsajid-ui.github.io/Candidate-Assignment-Reports/](https://mdsajid-ui.github.io/Candidate-Assignment-Reports/)  
📦 **GitHub Repository:** [https://github.com/mdsajid-ui/Candidate-Assignment-Reports](https://github.com/mdsajid-ui/Candidate-Assignment-Reports)

---

## 📧 Outgoing Email & SMTP Setup (Why it's required & How to setup)

When you click **"Send Report"** or **"Send All Pending"**, the app delivers the personalized evaluation email to the candidate's real inbox using SMTP. If sender credentials are not yet configured, the app prompts you with options:

### Option A: Send Real Emails via Gmail (Quick 3-Step Setup)
Because Google requires Two-Factor Authentication (2FA), your standard account login password will not work. You need a **Google 16-Character App Password**:
1. Open your Google Account &rarr; **Security** &rarr; Ensure **2-Step Verification** is turned ON.
2. Visit [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Under App Name, enter `Assignment Reports` and click **Create**.
4. Copy the 16-letter password into the **Password** field in the **⚙️ SMTP Setup** modal (or in `.env`).
5. Click **Save Settings** &mdash; your device will remember the credentials.

### Option B: Test in Simulation Mode (Instant &bull; No Password Needed)
Want to verify reports without entering an email password?
- When clicking **Send Report**, choose **"Send in Simulation Mode"** in the prompt dialog.
- The system renders the complete HTML report card, verifies all calculations, marks the student as `Simulated / Sent`, and updates your dashboard counters without making an actual SMTP connection.

### Option C: Configure via Environment Variables / `.env`
You can copy `.env.example` to `.env` in the root folder:
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=skabdulsajid8144@gmail.com
SMTP_PASS=your-16-char-app-password
SMTP_SENDER_NAME=SK Sajid | DV Analytics Mentorship Team
```
When configured, the backend automatically uses these settings for all dispatches.

---

## 🌟 Key Capabilities

### 1. Weekly LMS Assignment Reporting & Industrial Milestones
- **6 Core Data Analytics & Engineering Tools**:
  - **Excel**: 4 Assignments (SVG Donut Tracking)
  - **SQL**: 5 Assignments
  - **Python**: 5 Assignments
  - **Power BI**: 4 Assignments
  - **Tableau**: 4 Assignments
  - **Machine Learning**: 1 Capstone Project
- **Sajid's Pre-Seeded Industrial Record**:
  - Pre-configured with **Excel (4/4)**, **SQL (5/5)**, **Python (5/5)**, and **ML Capstone (100% Completed)** &rarr; **`65.2%` Industrial Placement Readiness**.
- **Interactive Mentorship & Upload Hub**:
  - Live threaded student-mentor messaging.
  - Drag-and-drop submission uploads (`.ipynb`, `.sql`, `.pbix`, `.xlsx`, `.pdf`, `.zip`).
  - Real-time tool counters and Capstone project toggles.
- **Pure Vector Inline SVG Donuts**:
  - Render flawlessly across Gmail, Outlook, Apple Mail, and mobile browsers with zero broken images.
- **Auto-Linked Student Directory**: Pre-loaded with **6,390 students** from the master database.

---

## 🚀 How to Run

### Method 1: Use Live on GitHub Pages (No installation needed)
👉 **[https://mdsajid-ui.github.io/Candidate-Assignment-Reports/](https://mdsajid-ui.github.io/Candidate-Assignment-Reports/)**

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


---

## 🚀 Deploy to Vercel (1-Click Hosting)

This project includes a ready-to-deploy [`vercel.json`](vercel.json) configuration for instantaneous hosting on Vercel.

### Method 1: Deploy with Vercel Web Dashboard (Recommended)
1. Push your changes to your GitHub repository ([`Candidate-Assignment-Reports`](https://github.com/mdsajid-ui/Candidate-Assignment-Reports)).
2. Go to **[vercel.com](https://vercel.com)** &rarr; Log in &rarr; Click **"Add New Project"**.
3. Import your **`Candidate-Assignment-Reports`** repository.
4. Framework Preset: **Other** (Root Directory: `./`).
5. Click **Deploy** &mdash; Vercel will build and assign you a global live URL (e.g. `https://candidate-assignment-reports.vercel.app`).

### Method 2: Deploy with Vercel CLI
```bash
npm i -g vercel
vercel login
vercel --prod
```
All static reporting data, the interactive Lamp Login, executive report card previews, and client-side processing will work out of the box with zero configuration!
