import os
import re
import smtplib
import ssl
import time
import mimetypes
from email.message import EmailMessage
from typing import List, Dict, Any, Optional, Tuple

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def is_valid_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))

class SMTPConfig:
    def __init__(
        self,
        host: str = "smtp.gmail.com",
        port: int = 587,
        username: str = "",
        password: str = "",
        use_ssl: bool = False,
        sender_name: str = "",
        reply_to: str = ""
    ):
        self.host = (host or "smtp.gmail.com").strip()
        try:
            self.port = int(port)
        except (ValueError, TypeError):
            self.port = 587
        self.username = (username or "").strip()
        self.password = (password or "").strip()
        self.use_ssl = bool(use_ssl) or (self.port == 465)
        self.sender_name = (sender_name or "").strip()
        self.reply_to = (reply_to or "").strip()

        # Intelligent Auto-Correction: Fix host if user enters a Gmail address with an Outlook host
        user_lower = self.username.lower()
        if user_lower.endswith(("@gmail.com", "@googlemail.com")):
            if "office365" in self.host.lower() or "outlook" in self.host.lower() or not self.host:
                self.host = "smtp.gmail.com"
                if self.port != 465:
                    self.port = 587
        elif user_lower.endswith(("@outlook.com", "@hotmail.com", "@live.com")):
            if "gmail" in self.host.lower() or not self.host:
                self.host = "smtp.office365.com"
                self.port = 587

    def validate(self) -> Tuple[bool, str]:
        if not self.host:
            return False, "SMTP Host is required."
        if not self.username:
            return False, "Sender Email / Username is required."
        if not self.password:
            return False, "Password or App Password is required."
        return True, ""

    def test_connection(self) -> Tuple[bool, str]:
        valid, msg = self.validate()
        if not valid:
            return False, msg

        context = ssl.create_default_context()
        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15) as server:
                    server.login(self.username, self.password)
                    return True, f"SMTP connection and authentication successful ({self.host}:{self.port})!"
            else:
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.username, self.password)
                    return True, f"SMTP connection and authentication successful ({self.host}:{self.port})!"
        except smtplib.SMTPAuthenticationError as e:
            raw_err = e.smtp_error.decode('utf-8', errors='ignore') if hasattr(e, 'smtp_error') else str(e)
            if "5.7.3" in raw_err or "OUTLOOK.COM" in raw_err:
                if self.username.lower().endswith("@gmail.com"):
                    return False, "Host Mismatch: Your email is @gmail.com but server was set to Microsoft Outlook (smtp.office365.com). Switch Host to smtp.gmail.com and use a 16-letter Google App Password."
                return False, f"Microsoft 365 Authentication Failed: {raw_err}. Ensure SMTP AUTH is enabled or use an App Password."
            elif "535" in str(e) or "5.7.8" in raw_err or "Username and Password not accepted" in raw_err:
                return False, "Gmail Authentication Failed: Google requires a 16-character Google App Password (not your regular account password). Generate one at https://myaccount.google.com/apppasswords"
            return False, f"Authentication failed: {raw_err}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

class BulkEmailTask:
    def __init__(
        self,
        task_id: str,
        config: SMTPConfig,
        recipients: List[Dict[str, Any]],
        subject_template: str,
        body_template: str,
        is_html: bool = False,
        attachment_paths: Optional[List[str]] = None,
        delay_seconds: float = 1.0,
        dry_run: bool = False
    ):
        self.task_id = task_id
        self.config = config
        self.recipients = recipients
        self.subject_template = subject_template
        self.body_template = body_template
        self.is_html = is_html
        self.attachment_paths = attachment_paths or []
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.dry_run = dry_run

        self.status = "queued"  # queued, running, completed, stopped, error
        self.total = len(recipients)
        self.sent_count = 0
        self.failed_count = 0
        self.current_index = 0
        self.current_email = ""
        self.stop_requested = False
        self.logs: List[Dict[str, Any]] = []
        self.error_summary: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def request_stop(self):
        self.stop_requested = True

    def get_progress(self) -> Dict[str, Any]:
        percent = 0
        if self.total > 0:
            percent = round(((self.sent_count + self.failed_count) / self.total) * 100, 1)
        return {
            "task_id": self.task_id,
            "status": self.status,
            "total": self.total,
            "sent": self.sent_count,
            "failed": self.failed_count,
            "current_index": self.current_index,
            "current_email": self.current_email,
            "progress_percent": percent,
            "dry_run": self.dry_run,
            "logs": self.logs[-50:],  # return latest 50 logs for UI
            "all_logs_count": len(self.logs),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error_summary": self.error_summary
        }

    def _render_template(self, text: str, recipient: Dict[str, Any]) -> str:
        """Replace placeholders like {{name}} or {name} with recipient values."""
        if not text:
            return ""
        rendered = text
        for key, val in recipient.items():
            val_str = str(val) if val is not None else ""
            rendered = rendered.replace(f"{{{{{key}}}}}", val_str)
            rendered = rendered.replace(f"{{{key}}}", val_str)
        return rendered

    def _build_message(self, recipient: Dict[str, Any], cached_attachments: List[Tuple[str, str, str, bytes]]) -> EmailMessage:
        msg = EmailMessage()
        subj = self._render_template(self.subject_template, recipient)
        body = self._render_template(self.body_template, recipient)
        to_addr = recipient.get("email", "").strip()

        msg["Subject"] = subj
        if self.config.sender_name:
            msg["From"] = f"{self.config.sender_name} <{self.config.username}>"
        else:
            msg["From"] = self.config.username

        msg["To"] = to_addr
        if self.config.reply_to:
            msg["Reply-To"] = self.config.reply_to

        if self.is_html:
            # Set a simple plain text fallback and HTML body
            plain_fallback = re.sub(r"<[^>]+>", " ", body)
            msg.set_content(plain_fallback)
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)

        # Attach pre-cached attachments
        for filename, maintype, subtype, file_bytes in cached_attachments:
            msg.add_attachment(file_bytes, maintype=maintype, subtype=subtype, filename=filename)

        return msg

    def run(self):
        self.status = "running"
        self.start_time = time.time()

        # Cache attachments into memory once so we don't re-read disk 100 times
        cached_attachments = []
        for path in self.attachment_paths:
            if os.path.exists(path):
                filename = os.path.basename(path)
                ctype, encoding = mimetypes.guess_type(path)
                if ctype is None or encoding is not None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)
                try:
                    with open(path, "rb") as f:
                        file_bytes = f.read()
                    cached_attachments.append((filename, maintype, subtype, file_bytes))
                except Exception as e:
                    self.logs.append({
                        "email": "SYSTEM",
                        "status": "warning",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "message": f"Could not read attachment {filename}: {str(e)}"
                    })

        context = ssl.create_default_context()
        smtp_server = None

        try:
            if not self.dry_run:
                if self.config.use_ssl:
                    smtp_server = smtplib.SMTP_SSL(self.config.host, self.config.port, context=context, timeout=25)
                else:
                    smtp_server = smtplib.SMTP(self.config.host, self.config.port, timeout=25)
                    smtp_server.ehlo()
                    smtp_server.starttls(context=context)
                    smtp_server.ehlo()
                smtp_server.login(self.config.username, self.config.password)

            for i, recipient in enumerate(self.recipients):
                if self.stop_requested:
                    self.status = "stopped"
                    self.logs.append({
                        "email": "SYSTEM",
                        "status": "stopped",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "message": "Sending was stopped by user."
                    })
                    break

                to_email = recipient.get("email", "").strip()
                self.current_index = i + 1
                self.current_email = to_email

                if not is_valid_email(to_email):
                    self.failed_count += 1
                    self.logs.append({
                        "email": to_email or "(empty)",
                        "status": "failed",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "message": "Invalid email address syntax."
                    })
                    continue

                try:
                    msg = self._build_message(recipient, cached_attachments)
                    if self.dry_run:
                        # Simulated send for testing
                        time.sleep(0.05)
                    else:
                        # Attempt send, reconnect if connection disconnected
                        try:
                            smtp_server.send_message(msg)
                        except (smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException) as conn_err:
                            # Reconnect and retry once
                            time.sleep(1)
                            if self.config.use_ssl:
                                smtp_server = smtplib.SMTP_SSL(self.config.host, self.config.port, context=context, timeout=25)
                            else:
                                smtp_server = smtplib.SMTP(self.config.host, self.config.port, timeout=25)
                                smtp_server.ehlo()
                                smtp_server.starttls(context=context)
                                smtp_server.ehlo()
                            smtp_server.login(self.config.username, self.config.password)
                            smtp_server.send_message(msg)

                    self.sent_count += 1
                    self.logs.append({
                        "email": to_email,
                        "status": "sent",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "message": "Sent successfully" + (" (Dry-Run)" if self.dry_run else "")
                    })
                except Exception as send_err:
                    self.failed_count += 1
                    self.logs.append({
                        "email": to_email,
                        "status": "failed",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "message": str(send_err)
                    })

                # Safe pacing delay between emails
                if self.delay_seconds > 0 and (i + 1) < len(self.recipients):
                    time.sleep(self.delay_seconds)

            if not self.stop_requested:
                self.status = "completed"

        except Exception as top_err:
            self.status = "error"
            self.error_summary = str(top_err)
            self.logs.append({
                "email": "SYSTEM",
                "status": "error",
                "timestamp": time.strftime("%H:%M:%S"),
                "message": f"Fatal SMTP error: {str(top_err)}"
            })
        finally:
            if smtp_server is not None:
                try:
                    smtp_server.quit()
                except Exception:
                    pass
            self.end_time = time.time()
