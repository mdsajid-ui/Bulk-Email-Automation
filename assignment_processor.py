import os
import io
import re
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
from bs4 import BeautifulSoup
from student_directory import student_directory
from email_engine import SMTPConfig, is_valid_email
import smtplib
import ssl
from email.message import EmailMessage

class AssignmentProcessor:
    def __init__(self):
        self.cached_df: Optional[pd.DataFrame] = None
        self.cached_candidates: List[Dict[str, Any]] = []

    def parse_file(self, file_path_or_bytes, filename: str = "") -> pd.DataFrame:
        """Parse LMS export file whether it is HTML disguised as .xls, real Excel, or CSV."""
        df = None
        
        # Check if file_path_or_bytes is a path
        if isinstance(file_path_or_bytes, str) and os.path.exists(file_path_or_bytes):
            with open(file_path_or_bytes, "rb") as f:
                content = f.read()
        elif isinstance(file_path_or_bytes, bytes):
            content = file_path_or_bytes
        else:
            content = file_path_or_bytes.read()

        # Check for HTML content in .xls export
        if b"<table" in content.lower() or b"<html" in content.lower() or b"<style" in content.lower():
            try:
                dfs = pd.read_html(io.BytesIO(content))
                if dfs:
                    df = dfs[0]
            except Exception as e:
                # Fallback to BeautifulSoup manual table parse
                df = self._parse_html_table_fallback(content)
        elif filename.lower().endswith((".xlsx", ".xls")):
            try:
                df = pd.read_excel(io.BytesIO(content))
            except Exception:
                # Might be HTML after all
                dfs = pd.read_html(io.BytesIO(content))
                if dfs:
                    df = dfs[0]
        elif filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            # Try read_html first then read_excel
            try:
                dfs = pd.read_html(io.BytesIO(content))
                df = dfs[0]
            except Exception:
                df = pd.read_excel(io.BytesIO(content))

        if df is None or df.empty:
            raise ValueError("Could not extract any table rows from the provided assignment file.")

        # Clean and standardize columns
        col_map = {}
        for col in df.columns:
            c_str = str(col).strip()
            c_lower = c_str.lower()
            if "student id" in c_lower or "studentid" in c_lower or "reg" in c_lower:
                col_map[col] = "student_id"
            elif "student name" in c_lower or "name" in c_lower or "firstname" in c_lower:
                col_map[col] = "student_name"
            elif "batch" in c_lower:
                col_map[col] = "batch"
            elif "application" in c_lower or "course" in c_lower or "subject" in c_lower or "module" in c_lower:
                col_map[col] = "application"
            elif "description" in c_lower or "assignment" in c_lower:
                col_map[col] = "description"
            elif "date" in c_lower:
                col_map[col] = "date"

        df = df.rename(columns=col_map)
        df = df.fillna("")
        
        # Clean string whitespace
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            if col == "student_name":
                # Normalize multiple spaces inside name
                df[col] = df[col].apply(lambda n: " ".join(n.split()))

        self.cached_df = df
        return df

    def _parse_html_table_fallback(self, content: bytes) -> pd.DataFrame:
        soup = BeautifulSoup(content.decode("utf-8", errors="ignore"), "html.parser")
        table = soup.find("table")
        if not table:
            return pd.DataFrame()

        rows = table.find_all("tr")
        if not rows:
            return pd.DataFrame()

        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        data = []
        for tr in rows[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells:
                data.append(cells)

        return pd.DataFrame(data, columns=headers if len(headers) == len(data[0]) else None)

    def aggregate_candidates(self, df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
        if df is None:
            df = self.cached_df
        if df is None:
            return []

        delivery_statuses = student_directory.get_delivery_statuses()
        candidates_map = {}

        for _, row in df.iterrows():
            sid = row.get("student_id", "").strip()
            name = row.get("student_name", "").strip()
            batch = row.get("batch", "").strip()
            app = row.get("application", "").strip()
            desc = row.get("description", "").strip()
            date_str = row.get("date", "").strip()

            key = sid or name
            if not key:
                continue

            if key not in candidates_map:
                # Match email from directory
                master_info = student_directory.lookup_student(student_id=sid, student_name=name)
                matched_email = master_info.get("email", "") if master_info else ""
                matched_phone = master_info.get("phone", "") if master_info else ""

                # Check if report was already sent
                status_rec = delivery_statuses.get(sid, {})

                candidates_map[key] = {
                    "student_id": sid,
                    "student_name": name,
                    "batch": batch,
                    "email": matched_email,
                    "phone": matched_phone,
                    "submissions": [],
                    "modules": {},
                    "latest_date": date_str,
                    "latest_submission": desc,
                    "status": status_rec.get("status", "pending"),
                    "last_sent_at": status_rec.get("last_sent_at", None),
                    "last_error": status_rec.get("last_error", None)
                }

            cand = candidates_map[key]
            cand["submissions"].append({
                "date": date_str,
                "application": app,
                "description": desc
            })
            if app:
                cand["modules"][app] = cand["modules"].get(app, 0) + 1

            # Update latest submission if more recent
            if date_str:
                cand["latest_date"] = date_str
                cand["latest_submission"] = desc or app

        # Sort submissions chronologically descending for each candidate
        candidates_list = list(candidates_map.values())
        for c in candidates_list:
            c["submissions_count"] = len(c["submissions"])
            # Reverse so newest are first
            c["submissions"] = list(reversed(c["submissions"]))

        # Sort candidates by student name
        candidates_list.sort(key=lambda x: x["student_name"].lower())
        self.cached_candidates = candidates_list
        return candidates_list

    def generate_html_report(self, candidate: Dict[str, Any], trainer_note: str = "", trainer_notes: str = "") -> str:
        """Generate a sleek, modern, professional HTML assignment report email."""
        effective_note = trainer_note or trainer_notes
        name = candidate.get("student_name", "Student")
        sid = candidate.get("student_id", "-")
        batch = candidate.get("batch", "-")
        subs = candidate.get("submissions", [])
        total_subs = len(subs)
        modules = candidate.get("modules", {})
        report_date = time.strftime("%d %B %Y")

        # Module breakdown tags
        module_cards_html = ""
        for mod, count in modules.items():
            module_cards_html += f"""
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 14px; margin-right:8px; margin-bottom:8px; display:inline-block; vertical-align:top;">
                <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;">{mod}</div>
                <div style="font-size:16px; font-weight:800; color:#1e293b; margin-top:2px;">{count} <span style="font-size:11px; font-weight:500; color:#94a3b8;">submissions</span></div>
            </div>
            """

        # Table rows of submissions
        rows_html = ""
        for idx, s in enumerate(subs):
            bg = "#ffffff" if idx % 2 == 0 else "#f8fafc"
            s_date = s.get("date", "-")
            s_app = s.get("application", "-")
            s_desc = s.get("description", "-") or "-"
            rows_html += f"""
            <tr style="background:{bg}; border-bottom:1px solid #edf2f7;">
                <td style="padding:10px 14px; font-size:12px; color:#64748b; font-family:monospace;">{idx + 1}</td>
                <td style="padding:10px 14px; font-size:12px; color:#1e293b; font-weight:600; white-space:nowrap;">{s_date}</td>
                <td style="padding:10px 14px; font-size:12px; color:#4338ca; font-weight:600;">{s_app}</td>
                <td style="padding:10px 14px; font-size:12px; color:#334155;">{s_desc}</td>
                <td style="padding:10px 14px; text-align:center;">
                    <span style="background:#ecfdf5; color:#059669; border:1px solid #a7f3d0; font-size:10px; font-weight:700; padding:3px 8px; border-radius:12px;">Verified</span>
                </td>
            </tr>
            """

        # Trainer Note
        note_block = ""
        if effective_note:
            note_block = f"""
            <div style="background:#eff6ff; border-left:4px solid #3b82f6; border-radius:6px; padding:12px 16px; margin-bottom:24px;">
                <div style="font-size:12px; font-weight:700; color:#1e40af; margin-bottom:4px;">Trainer Remarks / Guidance</div>
                <div style="font-size:13px; color:#1e3a8a; line-height:1.5;">{effective_note}</div>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly LMS Assignment Report</title>
</head>
<body style="margin:0; padding:0; background-color:#f1f5f9; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#f1f5f9; padding:24px 12px;">
        <tr>
            <td align="center">
                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:680px; background:#ffffff; border-radius:16px; overflow:hidden; box-shadow:0 4px 15px rgba(0,0,0,0.05); border:1px solid #e2e8f0;">
                    
                    <!-- Header Banner -->
                    <tr>
                        <td style="background:linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%); padding:30px 32px; color:#ffffff;">
                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td>
                                        <div style="display:inline-block; background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.25); border-radius:20px; padding:4px 12px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">
                                            DV Data &amp; Analytics &bull; LMS Assignment Portal
                                        </div>
                                        <h1 style="margin:0; font-size:22px; font-weight:800; letter-spacing:-0.5px; color:#ffffff;">
                                            Weekly Assignment Progress Report
                                        </h1>
                                        <p style="margin:4px 0 0; font-size:13px; color:#c7d2fe;">
                                            Evaluation &bull; Generated on {report_date}
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Candidate Summary Card -->
                    <tr>
                        <td style="padding:24px 32px 16px;">
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:16px;">
                                <tr>
                                    <td width="50%" style="vertical-align:top;">
                                        <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;">Student Name</div>
                                        <div style="font-size:17px; font-weight:800; color:#0f172a; margin-top:2px;">{name}</div>
                                        <div style="font-size:12px; color:#64748b; margin-top:2px; font-family:monospace;">ID: {sid}</div>
                                    </td>
                                    <td width="50%" style="vertical-align:top; text-align:right;">
                                        <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;">Batch / Program</div>
                                        <div style="font-size:15px; font-weight:700; color:#4338ca; margin-top:2px;">{batch}</div>
                                        <div style="font-size:12px; color:#059669; font-weight:600; margin-top:2px;">&bull; Active Learner</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Metrics Stats -->
                    <tr>
                        <td style="padding:0 32px 20px;">
                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td width="32%" style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; padding:14px; text-align:center;">
                                        <div style="font-size:24px; font-weight:800; color:#166534;">{total_subs}</div>
                                        <div style="font-size:11px; font-weight:700; color:#15803d; text-transform:uppercase; margin-top:2px;">Assignments Completed</div>
                                    </td>
                                    <td width="2%"></td>
                                    <td width="32%" style="background:#eef2ff; border:1px solid #c7d2fe; border-radius:10px; padding:14px; text-align:center;">
                                        <div style="font-size:24px; font-weight:800; color:#3730a3;">{len(modules)}</div>
                                        <div style="font-size:11px; font-weight:700; color:#4338ca; text-transform:uppercase; margin-top:2px;">Modules Covered</div>
                                    </td>
                                    <td width="2%"></td>
                                    <td width="32%" style="background:#fefce8; border:1px solid #fef08a; border-radius:10px; padding:14px; text-align:center;">
                                        <div style="font-size:14px; font-weight:800; color:#854d0e; padding-top:6px;">{candidate.get('latest_date', '-')}</div>
                                        <div style="font-size:11px; font-weight:700; color:#a16207; text-transform:uppercase; margin-top:6px;">Latest Submission</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Subject Breakdown -->
                    <tr>
                        <td style="padding:0 32px 16px;">
                            <div style="font-size:13px; font-weight:700; color:#334155; margin-bottom:8px;">Subject Submission Breakdown</div>
                            <div>{module_cards_html}</div>
                        </td>
                    </tr>

                    <!-- Trainer Remarks (if any) -->
                    <tr>
                        <td style="padding:0 32px;">
                            {note_block}
                        </td>
                    </tr>

                    <!-- Submissions Log Table -->
                    <tr>
                        <td style="padding:8px 32px 24px;">
                            <div style="font-size:13px; font-weight:700; color:#334155; margin-bottom:10px;">Submission History Details</div>
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="border:1px solid #e2e8f0; border-radius:10px; overflow:hidden;">
                                <thead>
                                    <tr style="background:#f1f5f9; border-bottom:1px solid #cbd5e1;">
                                        <th align="left" style="padding:10px 14px; font-size:11px; font-weight:700; color:#475569; text-transform:uppercase;">#</th>
                                        <th align="left" style="padding:10px 14px; font-size:11px; font-weight:700; color:#475569; text-transform:uppercase;">Date</th>
                                        <th align="left" style="padding:10px 14px; font-size:11px; font-weight:700; color:#475569; text-transform:uppercase;">Module</th>
                                        <th align="left" style="padding:10px 14px; font-size:11px; font-weight:700; color:#475569; text-transform:uppercase;">Session / Assignment</th>
                                        <th align="center" style="padding:10px 14px; font-size:11px; font-weight:700; color:#475569; text-transform:uppercase;">Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {rows_html}
                                </tbody>
                            </table>
                        </td>
                    </tr>

                    <!-- Support & Mentorship Footer -->
                    <tr>
                        <td style="background:#f8fafc; border-top:1px solid #e2e8f0; padding:24px 32px; font-size:12px; color:#64748b;">
                            <div style="font-weight:700; color:#334155; margin-bottom:6px;">Need Help or Mentorship?</div>
                            <p style="margin:0 0 12px; line-height:1.5;">
                                Keep up the great work! Consistent submission of assignments directly determines your industrial project readiness and placement qualification.
                            </p>
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="border-top:1px dashed #cbd5e1; padding-top:10px; font-size:11px;">
                                <tr>
                                    <td><strong>Finance &amp; LMS Access:</strong> Mr. Sajid &bull; 8431424165</td>
                                    <td><strong>Student Mentorship:</strong> Mrs. Lakshmi &bull; 7907991738</td>
                                </tr>
                                <tr>
                                    <td style="padding-top:4px;"><strong>Academic Escalations:</strong> Mr. Ajith &bull; 9916000655</td>
                                    <td style="padding-top:4px;"><strong>Class Schedules:</strong> Ms. Sanjana &bull; 9611276828</td>
                                </tr>
                            </table>
                            <div style="text-align:center; margin-top:18px; color:#94a3b8; font-size:11px;">
                                &copy; 2026 DV Data &amp; Analytics Pvt Ltd. All rights reserved.
                            </div>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
        return html

    def send_candidate_report(self, candidate: Dict[str, Any], smtp_config: SMTPConfig, trainer_notes: str = "", dry_run: bool = False) -> Dict[str, Any]:
        email = candidate.get("email", "").strip()
        name = candidate.get("student_name", "Student")
        sid = candidate.get("student_id", "")
        batch = candidate.get("batch", "")
        subs_count = len(candidate.get("submissions", []))

        if not is_valid_email(email):
            err = f"No valid email address available for {name} ({sid}). Please enter an email first."
            student_directory.update_delivery_status(sid, name, email, batch, "failed", err, subs_count)
            return {"success": False, "error": err}

        html_body = self.generate_html_report(candidate, trainer_notes)
        subject = f"Weekly Assignment Progress Report &bull; {name} ({batch})"

        if dry_run:
            time.sleep(0.05)
            student_directory.update_delivery_status(sid, name, email, batch, "sent", "Dry-Run Simulation", subs_count)
            return {"success": True, "message": f"Simulated report delivery to {email}"}

        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            if smtp_config.sender_name:
                msg["From"] = f"{smtp_config.sender_name} <{smtp_config.username}>"
            else:
                msg["From"] = smtp_config.username
            msg["To"] = email
            if smtp_config.reply_to:
                msg["Reply-To"] = smtp_config.reply_to

            plain_text = f"Dear {name},\n\nYour weekly assignment report has been generated. Total submissions: {subs_count}.\nPlease view this email in an HTML-compatible email client."
            msg.set_content(plain_text)
            msg.add_alternative(html_body, subtype="html")

            context = ssl.create_default_context()
            if smtp_config.use_ssl:
                with smtplib.SMTP_SSL(smtp_config.host, smtp_config.port, context=context, timeout=20) as server:
                    server.login(smtp_config.username, smtp_config.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=20) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(smtp_config.username, smtp_config.password)
                    server.send_message(msg)

            student_directory.update_delivery_status(sid, name, email, batch, "sent", "", subs_count)
            return {"success": True, "message": f"Report successfully delivered to {email}!"}

        except Exception as e:
            err = str(e)
            student_directory.update_delivery_status(sid, name, email, batch, "failed", err, subs_count)
            return {"success": False, "error": err}

assignment_processor = AssignmentProcessor()
