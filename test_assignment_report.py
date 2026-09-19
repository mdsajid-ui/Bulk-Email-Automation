import os
import pytest
from app import app
from assignment_processor import assignment_processor
from student_directory import student_directory

TEST_FILE = r"C:\Users\mdsaj\Downloads\Assignment (10).xls"

def test_student_directory():
    # Verify seeded database
    s = student_directory.lookup_student(student_name="PRIYANKA PATTNAIK")
    assert s is not None
    assert "pattnaikpriyanka460@gmail.com" in s["email"]

def test_assignment_processor_parse():
    if not os.path.exists(TEST_FILE):
        pytest.skip("Test file Assignment (10).xls not found.")

    df = assignment_processor.parse_file(TEST_FILE, filename="Assignment (10).xls")
    assert len(df) > 10000
    assert "student_id" in df.columns
    assert "student_name" in df.columns

    candidates = assignment_processor.aggregate_candidates(df)
    assert len(candidates) > 500

    # Pick sample candidate
    sample = candidates[0]
    assert "submissions" in sample
    assert sample["submissions_count"] > 0

    # Generate HTML
    html = assignment_processor.generate_html_report(sample)
    assert "Weekly Assignment Progress Report" in html
    assert sample["student_name"] in html

def test_assignment_api_endpoints():
    client = app.test_client()

    # 1. Load default
    res = client.post("/api/assignment/load-default")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["total_candidates"] > 0

    # 2. Get candidates
    res = client.get("/api/assignment/candidates")
    assert res.status_code == 200
    c_data = res.get_json()
    assert c_data["success"] is True
    assert len(c_data["candidates"]) > 0
    first_cand = c_data["candidates"][0]

    # 3. Preview HTML report
    res_prev = client.get(f"/api/assignment/preview/{first_cand['student_id']}")
    assert res_prev.status_code == 200
    assert b"Weekly Assignment Progress Report" in res_prev.data

    # 4. Dry-run send single report
    send_payload = {
        "student_id": first_cand["student_id"],
        "email": "test.recipient@example.com",
        "dry_run": True,
        "trainer_notes": "Great progress on your Python module!"
    }
    res_send = client.post("/api/assignment/send-one", json=send_payload)
    assert res_send.status_code == 200
    s_data = res_send.get_json()
    assert s_data["success"] is True
