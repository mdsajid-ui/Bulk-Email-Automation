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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ATTACHMENTS_DIR = os.path.join(UPLOAD_DIR, "attachments")
CONFIG_FILE = os.path.join(BASE_DIR, "smtp_saved_config.json")

os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload size

# Global state for current running task and attachments
active_task: BulkEmailTask = None
task_lock = threading.Lock()
current_attachments: List[Dict[str, Any]] = []

def get_saved_smtp_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_smtp_config(data: dict):
    # Save config without sensitive app password by default, or with password if requested
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save SMTP config: {e}")

@app.route("/")
def index():
    saved_cfg = get_saved_smtp_config()
    return render_template("index.html", saved_config=saved_cfg)

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
    cfg = SMTPConfig(
        host=data.get("host"),
        port=data.get("port", 587),
        username=data.get("username"),
        password=data.get("password"),
        use_ssl=data.get("use_ssl", False),
        sender_name=data.get("sender_name", ""),
        reply_to=data.get("reply_to", "")
    )
    success, msg = cfg.test_connection()
    if success and data.get("save_settings"):
        # Save host, port, username, sender_name, etc.
        save_smtp_config({
            "host": cfg.host,
            "port": cfg.port,
            "username": cfg.username,
            "sender_name": cfg.sender_name,
            "reply_to": cfg.reply_to,
            "use_ssl": cfg.use_ssl
        })
    return jsonify({"success": success, "message": msg})

@app.route("/api/save-smtp", methods=["POST"])
def save_smtp():
    data = request.json or {}
    save_smtp_config({
        "host": data.get("host", "smtp.gmail.com"),
        "port": data.get("port", 587),
        "username": data.get("username", ""),
        "sender_name": data.get("sender_name", ""),
        "reply_to": data.get("reply_to", ""),
        "use_ssl": data.get("use_ssl", False)
    })
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
        dry_run = data.get("dry_run", False)

        smtp_data = data.get("smtp", {})
        config = SMTPConfig(
            host=smtp_data.get("host"),
            port=smtp_data.get("port", 587),
            username=smtp_data.get("username"),
            password=smtp_data.get("password"),
            use_ssl=smtp_data.get("use_ssl", False),
            sender_name=smtp_data.get("sender_name", ""),
            reply_to=smtp_data.get("reply_to", "")
        )

        if not dry_run:
            valid, err_msg = config.validate()
            if not valid:
                return jsonify({"success": False, "error": err_msg}), 400

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

if __name__ == "__main__":
    print("Starting Bulk Email Automation App on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
