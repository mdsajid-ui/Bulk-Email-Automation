import os
import io
import csv
import json
import uuid
import threading
import time
from typing import Dict, Any, List
from flask import Flask, render_template, request, jsonify, send_file, Response
import pandas as pd
from email_engine import SMTPConfig, BulkEmailTask, is_valid_email
from assignment_processor import assignment_processor
from student_directory import student_directory


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ATTACHMENTS_DIR = os.path.join(UPLOAD_DIR, "attachments")
CONFIG_FILE = os.path.join(BASE_DIR, "smtp_saved_config.json")

os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload size

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response


# Global state for current running task and attachments
active_task: BulkEmailTask = None
task_lock = threading.Lock()
current_attachments: List[Dict[str, Any]] = []

def load_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass
load_env_file()

def get_saved_smtp_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f) or {}
        except Exception:
            pass
    return cfg

def save_smtp_config(data: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save SMTP config: {e}")

def resolve_smtp_config(smtp_data: dict) -> SMTPConfig:
    saved = {} if smtp_data.get("ignore_saved") else get_saved_smtp_config()
    host = (smtp_data.get("host") or "").strip() or saved.get("host") or os.environ.get("SMTP_HOST", "smtp.gmail.com")
    raw_port = smtp_data.get("port") or saved.get("port") or os.environ.get("SMTP_PORT", 587)
    try:
        port = int(raw_port)
    except Exception:
        port = 587
    username = (smtp_data.get("username") or "").strip() or saved.get("username") or os.environ.get("SMTP_USER", "")
    password = (smtp_data.get("password") or "").strip() or saved.get("password") or os.environ.get("SMTP_PASS", "")
    sender_name = (smtp_data.get("sender_name") or "").strip() or saved.get("sender_name") or os.environ.get("SMTP_SENDER_NAME", "DV Analytics Assignment Team")
    reply_to = (smtp_data.get("reply_to") or "").strip() or saved.get("reply_to") or os.environ.get("SMTP_REPLY_TO", "")
    use_ssl = bool(smtp_data.get("use_ssl", False) or saved.get("use_ssl", False))
    return SMTPConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        use_ssl=use_ssl,
        sender_name=sender_name,
        reply_to=reply_to
    )

@app.route("/")
def index():
    return send_file(os.path.join(BASE_DIR, "index.html"))

@app.route("/sample-report")
@app.route("/report-format")
@app.route("/sample_candidate_report.html")
def sample_report():
    sample_path = os.path.join(BASE_DIR, "sample_candidate_report.html")
    if os.path.exists(sample_path):
        return send_file(sample_path)
    return "Sample report not found", 404


@app.route("/sample_recipients.csv")
@app.route("/download-sample/csv")
def download_sample_csv():
    csv_path = os.path.join(BASE_DIR, "sample_recipients.csv")
    if not os.path.exists(csv_path):
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("email,name,company\njohn.doe@example.com,John Doe,Acme Corp\njane.smith@example.com,Jane Smith,Global Tech\nalex.innovate@example.com,Alex Johnson,Innovate Labs\n")
    return send_file(csv_path, mimetype="text/csv", as_attachment=True, download_name="sample_recipients.csv")

@app.route("/sample_recipients.xlsx")
@app.route("/download-sample/excel")
def download_sample_excel():
    xlsx_path = os.path.join(BASE_DIR, "sample_recipients.xlsx")
    if not os.path.exists(xlsx_path):
        df = pd.DataFrame([
            {"email": "john.doe@example.com", "name": "John Doe", "company": "Acme Corp"},
            {"email": "jane.smith@example.com", "name": "Jane Smith", "company": "Global Tech"},
            {"email": "alex.innovate@example.com", "name": "Alex Johnson", "company": "Innovate Labs"}
        ])
        df.to_excel(xlsx_path, index=False)
    return send_file(
        xlsx_path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="sample_recipients.xlsx"
    )


@app.route("/api/upload-recipients", methods=["POST"])
def upload_recipients():
    file = request.files.get("file")
    paste_text = request.form.get("paste_text", "").strip()

    recipients = []
    headers = []

    if file and file.filename:
        filename = file.filename.lower()
        file_bytes = file.read()
        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_bytes), dtype=str)
            elif filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
            else:
                return jsonify({"success": False, "error": "Unsupported file format. Please upload CSV or Excel (.xlsx, .xls)."}), 400

            # Clean dataframe
            df = df.fillna("")
            headers = list(df.columns)
            
            # Locate email column
            email_col = None
            for col in headers:
                if "email" in str(col).lower() or "mail" in str(col).lower():
                    email_col = col
                    break
            if not email_col and len(headers) > 0:
                # Find first column where values look like emails
                for col in headers:
                    sample_vals = df[col].dropna().astype(str).tolist()[:5]
                    if any("@" in v for v in sample_vals):
                        email_col = col
                        break
            if not email_col and len(headers) > 0:
                email_col = headers[0]

            for _, row in df.iterrows():
                row_dict = {str(k): str(v).strip() for k, v in row.items()}
                to_email = row_dict.get(email_col, "").strip() if email_col else ""
                row_dict["email"] = to_email
                if to_email:
                    recipients.append(row_dict)

        except Exception as e:
            return jsonify({"success": False, "error": f"Error parsing file: {str(e)}"}), 400

    elif paste_text:
        # Parse pasted email addresses (separated by commas, semicolons, or newlines)
        lines = re_split_tokens = [t.strip() for t in re_split_addresses(paste_text) if t.strip()]
        headers = ["email"]
        for addr in lines:
            if addr:
                recipients.append({"email": addr})
    else:
        return jsonify({"success": False, "error": "No file or text provided."}), 400

    # Validate and deduplicate
    seen_emails = set()
    valid_recipients = []
    invalid_recipients = []

    for r in recipients:
        email = r.get("email", "").strip()
        if is_valid_email(email):
            if email.lower() not in seen_emails:
                seen_emails.add(email.lower())
                valid_recipients.append(r)
        else:
            invalid_recipients.append(r)

    preview = valid_recipients[:10]
    return jsonify({
        "success": True,
        "total_count": len(valid_recipients),
        "valid_count": len(valid_recipients),
        "invalid_count": len(invalid_recipients),
        "headers": headers,
        "recipients": valid_recipients,
        "preview": preview
    })

def re_split_addresses(text: str) -> List[str]:
    import re
    return re.split(r"[\r\n,;]+", text)

@app.route("/api/upload-attachments", methods=["POST"])
def upload_attachments():
    global current_attachments
    uploaded_files = request.files.getlist("attachments")
    if not uploaded_files:
        return jsonify({"success": False, "error": "No attachments provided"}), 400

    for file in uploaded_files:
        if file and file.filename:
            safe_name = os.path.basename(file.filename)
            file_id = f"{uuid.uuid4().hex[:8]}_{safe_name}"
            save_path = os.path.join(ATTACHMENTS_DIR, file_id)
            file.save(save_path)
            size_bytes = os.path.getsize(save_path)

            current_attachments.append({
                "id": file_id,
                "name": safe_name,
                "size_bytes": size_bytes,
                "size_display": format_size(size_bytes),
                "path": save_path
            })

    return jsonify({"success": True, "attachments": current_attachments})

@app.route("/api/remove-attachment", methods=["POST"])
def remove_attachment():
    global current_attachments
    data = request.json or {}
    att_id = data.get("id")
    filtered = []
    for att in current_attachments:
        if att["id"] == att_id:
            try:
                if os.path.exists(att["path"]):
                    os.remove(att["path"])
            except Exception:
                pass
        else:
            filtered.append(att)
    current_attachments = filtered
    return jsonify({"success": True, "attachments": current_attachments})

@app.route("/api/clear-attachments", methods=["POST"])
def clear_attachments():
    global current_attachments
    for att in current_attachments:
        try:
            if os.path.exists(att["path"]):
                os.remove(att["path"])
        except Exception:
            pass
    current_attachments = []
    return jsonify({"success": True, "attachments": []})

@app.route("/api/get-attachments", methods=["GET"])
def get_attachments():
    return jsonify({"success": True, "attachments": current_attachments})

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

@app.route("/api/test-smtp", methods=["POST"])
def test_smtp():
    data = request.json or {}
    cfg = resolve_smtp_config(data)
    success, msg = cfg.test_connection()
    if success and data.get("save_settings"):
        saved_dict = {
            "host": cfg.host,
            "port": cfg.port,
            "username": cfg.username,
            "sender_name": cfg.sender_name,
            "reply_to": cfg.reply_to,
            "use_ssl": cfg.use_ssl
        }
        if cfg.password:
            saved_dict["password"] = cfg.password
        save_smtp_config(saved_dict)
    return jsonify({"success": success, "message": msg})

@app.route("/api/get-smtp", methods=["GET"])
def get_smtp():
    saved = get_saved_smtp_config()
    has_pass = bool(saved.get("password") or os.environ.get("SMTP_PASS"))
    return jsonify({
        "success": True,
        "config": {
            "host": saved.get("host") or os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            "port": saved.get("port") or int(os.environ.get("SMTP_PORT", 587)),
            "username": saved.get("username") or os.environ.get("SMTP_USER", ""),
            "sender_name": saved.get("sender_name") or os.environ.get("SMTP_SENDER_NAME", "DV Analytics Assignment Team"),
            "reply_to": saved.get("reply_to") or os.environ.get("SMTP_REPLY_TO", ""),
            "use_ssl": bool(saved.get("use_ssl", False)),
            "has_password": has_pass
        }
    })

@app.route("/api/save-smtp", methods=["POST"])
def save_smtp():
    data = request.json or {}
    existing = get_saved_smtp_config()
    saved_dict = {
        "host": data.get("host", existing.get("host", "smtp.gmail.com")),
        "port": int(data.get("port", existing.get("port", 587))),
        "username": data.get("username", existing.get("username", "")),
        "sender_name": data.get("sender_name", existing.get("sender_name", "DV Analytics Assignment Team")),
        "reply_to": data.get("reply_to", existing.get("reply_to", "")),
        "use_ssl": bool(data.get("use_ssl", existing.get("use_ssl", False)))
    }
    if data.get("password"):
        saved_dict["password"] = data.get("password")
    elif existing.get("password"):
        saved_dict["password"] = existing.get("password")

    save_smtp_config(saved_dict)
    return jsonify({"success": True, "message": "Settings saved successfully."})

@app.route("/api/send-bulk", methods=["POST"])
def send_bulk():
    global active_task
    with task_lock:
        if active_task and active_task.status == "running":
            return jsonify({"success": False, "error": "Another bulk send task is already in progress."}), 409

        data = request.json or {}
        recipients = data.get("recipients", [])
        if not recipients:
            return jsonify({"success": False, "error": "No recipients provided."}), 400

        subject = data.get("subject", "").strip()
        if not subject:
            return jsonify({"success": False, "error": "Subject line is required."}), 400

        body = data.get("body", "").strip()
        if not body:
            return jsonify({"success": False, "error": "Email body message is required."}), 400

        is_html = data.get("is_html", False)
        delay_seconds = data.get("delay_seconds", 1.0)
        dry_run = data.get("dry_run", False) or data.get("simulate", False)

        smtp_data = data.get("smtp", {})
        config = resolve_smtp_config(smtp_data)

        if not dry_run:
            valid, err_msg = config.validate()
            if not valid:
                return jsonify({
                    "success": False,
                    "error": f"SMTP Setup required: {err_msg}",
                    "requires_smtp": True
                }), 400

        # Attachment file paths
        att_paths = [att["path"] for att in current_attachments if os.path.exists(att["path"])]

        task_id = str(uuid.uuid4())[:8]
        active_task = BulkEmailTask(
            task_id=task_id,
            config=config,
            recipients=recipients,
            subject_template=subject,
            body_template=body,
            is_html=is_html,
            attachment_paths=att_paths,
            delay_seconds=delay_seconds,
            dry_run=dry_run
        )

        # Launch background worker
        worker = threading.Thread(target=active_task.run, daemon=True)
        worker.start()

        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": f"Bulk sending initiated for {len(recipients)} recipients.",
            "attachment_count": len(att_paths)
        })

@app.route("/api/send-status", methods=["GET"])
def send_status():
    global active_task
    with task_lock:
        if not active_task:
            return jsonify({"success": True, "has_task": False, "status": "idle"})
        return jsonify({"success": True, "has_task": True, "progress": active_task.get_progress()})

@app.route("/api/send-status-stream")
def send_status_stream():
    """SSE endpoint for live progress streaming."""
    def event_stream():
        while True:
            with task_lock:
                if active_task:
                    prog = active_task.get_progress()
                    yield f"data: {json.dumps(prog)}\n\n"
                    if prog["status"] in ["completed", "stopped", "error"]:
                        break
                else:
                    yield f"data: {json.dumps({'status': 'idle'})}\n\n"
                    break
            time.sleep(0.5)

    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/api/stop-send", methods=["POST"])
def stop_send():
    global active_task
    with task_lock:
        if active_task and active_task.status == "running":
            active_task.request_stop()
            return jsonify({"success": True, "message": "Stop signal sent to sender."})
        return jsonify({"success": False, "error": "No active task running."}), 400

@app.route("/api/export-report", methods=["GET"])
def export_report():
    global active_task
    with task_lock:
        if not active_task or not active_task.logs:
            return jsonify({"error": "No delivery logs available to export."}), 404

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Email", "Status", "Timestamp", "Message / Error"])
        for entry in active_task.logs:
            writer.writerow([
                entry.get("email", ""),
                entry.get("status", ""),
                entry.get("timestamp", ""),
                entry.get("message", "")
            ])

        output.seek(0)
        bytes_io = io.BytesIO(output.getvalue().encode("utf-8"))
        filename = f"email_delivery_report_{active_task.task_id}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(
            bytes_io,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

# ================= LMS WEEKLY ASSIGNMENT REPORT ROUTES =================

assignment_batch_state = {
    "status": "idle", # idle, running, completed, stopped, error
    "total": 0,
    "sent": 0,
    "failed": 0,
    "current_student": "",
    "logs": [],
    "stop_requested": False
}
assignment_batch_lock = threading.Lock()

@app.route("/api/assignment/upload", methods=["POST"])
def assignment_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file uploaded."}), 400

    filename = file.filename
    try:
        content = file.read()
        df = assignment_processor.parse_file(content, filename=filename)
        candidates = assignment_processor.aggregate_candidates(df)
        batches = sorted(list(set(c["batch"] for c in candidates if c["batch"])))

        return jsonify({
            "success": True,
            "filename": filename,
            "total_rows": len(df),
            "total_candidates": len(candidates),
            "batches": batches
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to parse assignment report: {str(e)}"}), 400

@app.route("/api/assignment/load-default", methods=["POST"])
def assignment_load_default():
    local_repo_file = os.path.join(BASE_DIR, "Assignment (10).xls")
    downloads_file = r"C:\Users\mdsaj\Downloads\Assignment (10).xls"
    default_path = local_repo_file if os.path.exists(local_repo_file) else downloads_file
    if not os.path.exists(default_path):
        return jsonify({"success": False, "error": f"Default file not found at {default_path}"}), 404

    try:
        df = assignment_processor.parse_file(default_path, filename="Assignment (10).xls")
        candidates = assignment_processor.aggregate_candidates(df)
        batches = sorted(list(set(c["batch"] for c in candidates if c["batch"])))

        return jsonify({
            "success": True,
            "filename": "Assignment (10).xls",
            "total_rows": len(df),
            "total_candidates": len(candidates),
            "batches": batches
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to load Assignment (10).xls: {str(e)}"}), 400

@app.route("/api/assignment/candidates", methods=["GET"])
def assignment_get_candidates():
    if not assignment_processor.cached_candidates and assignment_processor.cached_df is not None:
        assignment_processor.aggregate_candidates()

    candidates = assignment_processor.cached_candidates or []
    
    # Refresh delivery statuses from DB
    statuses = student_directory.get_delivery_statuses()
    for c in candidates:
        sid = c.get("student_id")
        if sid in statuses:
            c["status"] = statuses[sid].get("status", "pending")
            c["last_sent_at"] = statuses[sid].get("last_sent_at")
            c["last_error"] = statuses[sid].get("last_error")

    # Filters
    batch_filter = request.args.get("batch", "").strip()
    status_filter = request.args.get("status", "").strip() # 'pending', 'sent', 'failed'
    search_query = request.args.get("search", "").strip().lower()

    filtered = candidates
    if batch_filter:
        filtered = [c for c in filtered if c.get("batch") == batch_filter]
    if status_filter and status_filter != "all":
        filtered = [c for c in filtered if c.get("status") == status_filter]
    if search_query:
        filtered = [
            c for c in filtered 
            if search_query in c.get("student_name", "").lower()
            or search_query in c.get("student_id", "").lower()
            or search_query in c.get("email", "").lower()
        ]

    # Metrics
    total = len(candidates)
    sent_count = sum(1 for c in candidates if c.get("status") == "sent")
    pending_count = sum(1 for c in candidates if c.get("status") != "sent")

    return jsonify({
        "success": True,
        "total_unfiltered": total,
        "filtered_count": len(filtered),
        "metrics": {
            "total_candidates": total,
            "sent_count": sent_count,
            "pending_count": pending_count
        },
        "candidates": filtered
    })

@app.route("/api/assignment/preview/<student_id>", methods=["GET"])
def assignment_preview(student_id):
    cand = next((c for c in assignment_processor.cached_candidates if c.get("student_id") == student_id), None)
    if not cand:
        return "<div style='font-family:sans-serif; padding:20px; color:#ef4444;'>Student candidate not found.</div>", 404

    trainer_note = request.args.get("note", "")
    html = assignment_processor.generate_html_report(cand, trainer_notes=trainer_note)
    return html

@app.route("/api/assignment/update-email", methods=["POST"])
def assignment_update_email():
    data = request.json or {}
    sid = data.get("student_id", "").strip()
    email = data.get("email", "").strip()
    name = data.get("student_name", "").strip()
    batch = data.get("batch", "").strip()

    if not sid:
        return jsonify({"success": False, "error": "student_id is required"}), 400
    if email and not is_valid_email(email):
        return jsonify({"success": False, "error": "Invalid email syntax"}), 400

    student_directory.update_email(sid, email, student_name=name, batch=batch)

    # Update in memory cache
    for c in assignment_processor.cached_candidates:
        if c.get("student_id") == sid:
            c["email"] = email
            break

    return jsonify({"success": True, "message": f"Updated email for {name or sid} to {email}"})

@app.route("/api/assignment/send-one", methods=["POST"])
def assignment_send_one():
    data = request.json or {}
    sid = data.get("student_id", "").strip()
    cand = next((c for c in assignment_processor.cached_candidates if c.get("student_id") == sid), None)
    if not cand:
        return jsonify({"success": False, "error": f"Candidate with ID '{sid}' not found in loaded report."}), 404

    # Allow email override in payload
    if data.get("email"):
        cand["email"] = data["email"].strip()
        student_directory.update_email(sid, cand["email"], student_name=cand.get("student_name"), batch=cand.get("batch"))

    dry_run = data.get("dry_run", False) or data.get("simulate", False)
    trainer_notes = data.get("trainer_notes", "")
    smtp_data = data.get("smtp", {})
    smtp_cfg = resolve_smtp_config(smtp_data)

    if not dry_run:
        valid, err = smtp_cfg.validate()
        if not valid:
            return jsonify({
                "success": False,
                "error": f"SMTP Setup required: {err}",
                "requires_smtp": True,
                "missing": err
            }), 400

    result = assignment_processor.send_candidate_report(cand, smtp_cfg, trainer_notes=trainer_notes, dry_run=dry_run)
    if result["success"]:
        cand["status"] = "simulated" if dry_run else "sent"
        cand["last_sent_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if dry_run:
            result["simulated"] = True
    else:
        cand["status"] = "failed"
        cand["last_error"] = result.get("error")

    return jsonify(result)

@app.route("/api/assignment/send-batch", methods=["POST"])
def assignment_send_batch():
    global assignment_batch_state
    with assignment_batch_lock:
        if assignment_batch_state["status"] == "running":
            return jsonify({"success": False, "error": "A batch report dispatch is already running."}), 409

        data = request.json or {}
        student_ids = data.get("student_ids", [])
        
        # If student_ids empty, default to all pending candidates
        if not student_ids:
            candidates_to_send = [c for c in assignment_processor.cached_candidates if c.get("status") != "sent"]
        else:
            id_set = set(student_ids)
            candidates_to_send = [c for c in assignment_processor.cached_candidates if c.get("student_id") in id_set]

        if not candidates_to_send:
            return jsonify({"success": False, "error": "No candidates to send reports to."}), 400

        dry_run = data.get("dry_run", False) or data.get("simulate", False)
        trainer_notes = data.get("trainer_notes", "")
        delay_seconds = float(data.get("delay_seconds", 1.0))
        smtp_data = data.get("smtp", {})
        smtp_cfg = resolve_smtp_config(smtp_data)

        if not dry_run:
            valid, err = smtp_cfg.validate()
            if not valid:
                return jsonify({
                    "success": False,
                    "error": f"SMTP Setup required: {err}",
                    "requires_smtp": True,
                    "missing": err
                }), 400

        # Initialize batch state
        assignment_batch_state = {
            "status": "running",
            "total": len(candidates_to_send),
            "sent": 0,
            "failed": 0,
            "current_student": "",
            "logs": [],
            "stop_requested": False
        }

        def worker():
            global assignment_batch_state
            for i, cand in enumerate(candidates_to_send):
                with assignment_batch_lock:
                    if assignment_batch_state["stop_requested"]:
                        assignment_batch_state["status"] = "stopped"
                        break
                    assignment_batch_state["current_student"] = cand.get("student_name", "")

                res = assignment_processor.send_candidate_report(cand, smtp_cfg, trainer_notes=trainer_notes, dry_run=dry_run)
                
                with assignment_batch_lock:
                    time_str = time.strftime("%H:%M:%S")
                    if res["success"]:
                        assignment_batch_state["sent"] += 1
                        cand["status"] = "simulated" if dry_run else "sent"
                        assignment_batch_state["logs"].append({
                            "student": cand.get("student_name"),
                            "email": cand.get("email"),
                            "status": "simulated" if dry_run else "sent",
                            "timestamp": time_str,
                            "message": "[Simulation Mode] Report prepared and verified" if dry_run else "Report delivered successfully"
                        })
                    else:
                        assignment_batch_state["failed"] += 1
                        cand["status"] = "failed"
                        assignment_batch_state["logs"].append({
                            "student": cand.get("student_name"),
                            "email": cand.get("email"),
                            "status": "failed",
                            "timestamp": time_str,
                            "message": res.get("error")
                        })

                if delay_seconds > 0 and i < len(candidates_to_send) - 1:
                    time.sleep(delay_seconds)

            with assignment_batch_lock:
                if assignment_batch_state["status"] == "running":
                    assignment_batch_state["status"] = "completed"

        threading.Thread(target=worker, daemon=True).start()

        return jsonify({
            "success": True,
            "message": f"Initiated report batch sending for {len(candidates_to_send)} candidates."
        })

@app.route("/api/assignment/batch-status", methods=["GET"])
def assignment_batch_status():
    with assignment_batch_lock:
        state = dict(assignment_batch_state)
        percent = 0
        if state["total"] > 0:
            percent = round(((state["sent"] + state["failed"]) / state["total"]) * 100, 1)
        state["progress_percent"] = percent
        state["logs"] = state["logs"][-30:] # return last 30
        return jsonify({"success": True, "batch": state})

@app.route("/api/assignment/batch-stop", methods=["POST"])
def assignment_batch_stop():
    global assignment_batch_state
    with assignment_batch_lock:
        if assignment_batch_state["status"] == "running":
            assignment_batch_state["stop_requested"] = True
            return jsonify({"success": True, "message": "Stop signal sent."})
        return jsonify({"success": False, "error": "No batch currently running."}), 400

@app.route("/api/assignment/update-curriculum", methods=["POST"])
def assignment_update_curriculum():
    data = request.json or {}
    sid = data.get("student_id", "").strip()
    cand = next((c for c in assignment_processor.cached_candidates if c.get("student_id") == sid), None)
    name = data.get("student_name", "") or (cand.get("student_name") if cand else "")
    
    excel = int(data.get("excel", 0))
    sql = int(data.get("sql", 0))
    python = int(data.get("python", 0))
    power_bi = int(data.get("power_bi", 0))
    tableau = int(data.get("tableau", 0))
    ml_project = 1 if data.get("ml_project") else 0
    notes = data.get("notes", "")

    student_directory.save_student_curriculum(sid, name, excel, sql, python, power_bi, tableau, ml_project, notes)

    if cand:
        cand["curriculum"] = assignment_processor.calculate_curriculum(cand)
        return jsonify({"success": True, "curriculum": cand["curriculum"]})
    return jsonify({"success": True})

@app.route("/api/assignment/upload-submission", methods=["POST"])
def assignment_upload_submission():
    file = request.files.get("file")
    sid = request.form.get("student_id", "").strip()
    tool = request.form.get("tool", "excel").strip().lower()
    desc = request.form.get("description", "").strip()

    cand = next((c for c in assignment_processor.cached_candidates if c.get("student_id") == sid), None)
    if not cand:
        return jsonify({"success": False, "error": f"Candidate with ID {sid} not found."}), 404

    filename = file.filename if file else "Manual_Submission"
    date_str = time.strftime("%d-%m-%Y")
    
    if file and file.filename:
        save_folder = os.path.join(BASE_DIR, "uploads", sid)
        os.makedirs(save_folder, exist_ok=True)
        file.save(os.path.join(save_folder, filename))

    tool_app_map = {
        "excel": "EXCEL BASE AND ADVANCED",
        "sql": "SQL SERVER",
        "python": "PYTHON PROGRAMMING",
        "power_bi": "POWER BI",
        "tableau": "TABLEAU",
        "ml": "MACHINE LEARNING CAPSTONE",
        "machine_learning": "MACHINE LEARNING CAPSTONE"
    }
    app_name = tool_app_map.get(tool, tool.upper())
    submission_desc = desc or f"Verified Submission: {filename}"

    cand["submissions"].insert(0, {
        "date": date_str,
        "application": app_name,
        "description": submission_desc
    })
    cand["submissions_count"] = len(cand["submissions"])
    cand["latest_date"] = date_str
    cand["latest_submission"] = submission_desc

    cand["curriculum"] = assignment_processor.calculate_curriculum(cand)
    return jsonify({
        "success": True,
        "message": f"Successfully uploaded {filename} for {cand['student_name']}!",
        "curriculum": cand["curriculum"],
        "submissions_count": cand["submissions_count"]
    })

@app.route("/api/assignment/mentor-chat", methods=["POST"])
def assignment_mentor_chat():
    data = request.json or {}
    sid = data.get("student_id", "").strip()
    user_msg = data.get("message", "").strip()
    cand = next((c for c in assignment_processor.cached_candidates if c.get("student_id") == sid), None)
    student_name = cand.get("student_name", "Student") if cand else "Student"

    u_lower = user_msg.lower()
    if "project" in u_lower or "capstone" in u_lower or "ml" in u_lower or "machine learning" in u_lower:
        reply = f"Hello {student_name}! Your Machine Learning Capstone Project requirements have been reviewed. Sajid and the academic committee will verify your deployment repository and schedule your project defense viva."
    elif "sql" in u_lower or "python" in u_lower or "excel" in u_lower:
        reply = f"Great question regarding the curriculum modules, {student_name}. Mrs. Lakshmi (Mentorship Lead: +91 7907991738) has been tagged and will assist you with sample datasets and query optimization."
    elif "interview" in u_lower or "placement" in u_lower or "job" in u_lower:
        reply = f"Congratulations on your progress, {student_name}! Since your tool completion metrics are high, Mr. Ajith (+91 9916000655) will initiate your placement screening and schedule your corporate mock interview."
    else:
        reply = f"Thank you for contacting DV Analytics Mentorship, {student_name}. Your message has been logged with Mr. Sajid (+91 8431424165) and Mrs. Lakshmi. We will get back to you shortly!"

    return jsonify({
        "success": True,
        "reply": reply,
        "mentor": "DV Analytics Mentorship Team",
        "timestamp": time.strftime("%I:%M %p")
    })

if __name__ == "__main__":
    print("Starting Bulk Email Automation App on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
