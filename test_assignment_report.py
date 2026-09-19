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
    assert "Industrial Performance Report" in html or "Weekly Assignment Progress Report" in html
    assert sample["student_name"] in html
    assert "<svg" in html

def test_sajid_curriculum_and_donuts():
    # Sajid profile test
    s = student_directory.lookup_student(student_name="SK SAJID")
    assert s is not None
    assert "skabdulsajid8144@gmail.com" in s["email"]

    cand = {
        "student_id": "BLR20221101313",
        "student_name": "SK SAJID",
        "batch": "BATCH 202211",
        "submissions": []
    }
    cur = assignment_processor.calculate_curriculum(cand)
    assert cur["excel"]["completed"] == 4
    assert cur["excel"]["target"] == 4
    assert cur["excel"]["percent"] == 100.0

    assert cur["sql"]["completed"] == 5
    assert cur["sql"]["target"] == 5
    assert cur["sql"]["percent"] == 100.0

    assert cur["python"]["completed"] == 5
    assert cur["python"]["target"] == 5
    assert cur["python"]["percent"] == 100.0

    assert cur["power_bi"]["target"] == 4
    assert cur["tableau"]["target"] == 4
    assert cur["machine_learning"]["target"] == 1
    assert cur["machine_learning"]["completed"] is True
    assert cur["machine_learning"]["status"] == "COMPLETED"

    # Test pure SVG donut renderer
    svg = assignment_processor.render_svg_donut(50.0, "#10b981", "2/4", "50%")
    assert "<svg" in svg
    assert "viewBox" in svg
    assert "stroke-dashoffset" in svg
    assert "2/4" in svg

def test_assignment_api_endpoints():
    client = app.test_client()

    # 1. Load default
    res = client.post("/api/assignment/load-default")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["total_candidates"] > 0

    # 2. Get candidates and search for Sajid
    res = client.get("/api/assignment/candidates?search=sajid")
    assert res.status_code == 200
    c_data = res.get_json()
    assert c_data["success"] is True
    assert len(c_data["candidates"]) > 0
    sajid_cand = c_data["candidates"][0]
    assert sajid_cand["student_name"] == "SK SAJID"
    assert sajid_cand["email"] == "skabdulsajid8144@gmail.com"

    # 3. Preview HTML report for Sajid
    res_prev = client.get(f"/api/assignment/preview/{sajid_cand['student_id']}")
    assert res_prev.status_code == 200
    assert b"SK SAJID" in res_prev.data
    assert b"<svg" in res_prev.data
    assert b"Core Tools Curriculum Progress" in res_prev.data

    # 4. Mentor Chat API
    chat_payload = {
        "student_id": sajid_cand["student_id"],
        "message": "I have completed Excel, SQL, Python and Machine Learning. Ready for Capstone review."
    }
    res_chat = client.post("/api/assignment/mentor-chat", json=chat_payload)
    assert res_chat.status_code == 200
    chat_data = res_chat.get_json()
    assert chat_data["success"] is True
    assert "Capstone" in chat_data["reply"] or "Machine Learning" in chat_data["reply"]

    # 5. Dry-run send single report
    send_payload = {
        "student_id": sajid_cand["student_id"],
        "email": "skabdulsajid8144@gmail.com",
        "dry_run": True,
        "trainer_notes": "All core tools and ML project completed with distinction!"
    }
    res_send = client.post("/api/assignment/send-one", json=send_payload)
    assert res_send.status_code == 200
    s_data = res_send.get_json()
    assert s_data["success"] is True

