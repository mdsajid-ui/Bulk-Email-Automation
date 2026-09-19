import os
import io
import time
import pytest
from email_engine import is_valid_email, SMTPConfig, BulkEmailTask
from app import app, current_attachments

def test_email_validation():
    assert is_valid_email("user@example.com") is True
    assert is_valid_email("first.last+tag@sub.domain.org") is True
    assert is_valid_email("invalid-email") is False
    assert is_valid_email("user@") is False
    assert is_valid_email("") is False

def test_bulk_email_dry_run_and_attachment(tmp_path):
    # Create a temporary attachment
    dummy_file = tmp_path / "sample_report.pdf"
    dummy_file.write_bytes(b"%PDF-1.4 dummy pdf binary content")

    recipients = [
        {"email": "alex@example.com", "name": "Alex", "company": "Alpha Inc"},
        {"email": "beth@example.com", "name": "Beth", "company": "Beta Corp"},
        {"email": "invalid_address", "name": "Ghost", "company": "Nowhere"}
    ]

    config = SMTPConfig(username="test@example.com", password="dummy_password")
    task = BulkEmailTask(
        task_id="test-123",
        config=config,
        recipients=recipients,
        subject_template="Special Offer for {{name}}",
        body_template="Hi {{name}} at {{company}}, here is the attached file.",
        is_html=False,
        attachment_paths=[str(dummy_file)],
        delay_seconds=0.0,
        dry_run=True
    )

    # Run the task synchronously
    task.run()

    progress = task.get_progress()
    assert progress["total"] == 3
    assert progress["sent"] == 2  # alex and beth
    assert progress["failed"] == 1 # invalid_address
    assert progress["status"] == "completed"

def test_flask_endpoints(tmp_path):
    client = app.test_client()

    # 1. Test home page
    res = client.get("/")
    assert res.status_code == 200
    assert b"Bulk Email Automator" in res.data

    # 2. Test upload recipients via CSV
    csv_content = b"email,name\njohn@example.com,John\njane@example.com,Jane\n"
    res = client.post(
        "/api/upload-recipients",
        data={"file": (io.BytesIO(csv_content), "test.csv")},
        content_type="multipart/form-data"
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["total_count"] == 2
    assert len(data["recipients"]) == 2

    # 3. Test upload recipients via text paste
    res = client.post(
        "/api/upload-recipients",
        data={"paste_text": "alpha@example.com, beta@example.com; gamma@example.com"}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["total_count"] == 3

    # 4. Test upload attachments
    test_pdf_content = b"%PDF-1.4 test document"
    res = client.post(
        "/api/upload-attachments",
        data={"attachments": [(io.BytesIO(test_pdf_content), "brochure.pdf")]},
        content_type="multipart/form-data"
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert len(data["attachments"]) >= 1

    # 5. Test send bulk in dry-run mode
    payload = {
        "recipients": [
            {"email": "one@example.com", "name": "One"},
            {"email": "two@example.com", "name": "Two"}
        ],
        "subject": "Hello {{name}}",
        "body": "Welcome {{name}}!",
        "is_html": False,
        "delay_seconds": 0.0,
        "dry_run": True,
        "smtp": {
            "host": "smtp.example.com",
            "port": 587,
            "username": "sender@example.com",
            "password": "fakepassword"
        }
    }
    res = client.post("/api/send-bulk", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True

    # Wait for background thread
    time.sleep(0.5)

    # 6. Test send status
    res = client.get("/api/send-status")
    assert res.status_code == 200
    status_data = res.get_json()
    assert status_data["success"] is True
    assert status_data["has_task"] is True

    # 7. Test export report
    res = client.get("/api/export-report")
    assert res.status_code == 200
    assert b"Email,Status,Timestamp" in res.data

    # 8. Test sample CSV download
    res_csv = client.get("/download-sample/csv")
    assert res_csv.status_code == 200
    assert b"email,name,company" in res_csv.data

    # 9. Test sample Excel download
    res_excel = client.get("/download-sample/excel")
    assert res_excel.status_code == 200
    assert len(res_excel.data) > 0
    assert res_excel.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

