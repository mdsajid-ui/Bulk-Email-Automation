import os
import sqlite3
import pandas as pd
from typing import Optional, Dict, Any, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "students_master.db")

os.makedirs(DATA_DIR, exist_ok=True)

class StudentDirectory:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._seed_initial_data_if_empty()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    student_id TEXT PRIMARY KEY,
                    student_name TEXT,
                    email TEXT,
                    phone TEXT,
                    batch TEXT,
                    course TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stu_name ON students(student_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stu_email ON students(email)")

            # Tracking report delivery status per weekly report
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assignment_delivery_status (
                    student_id TEXT PRIMARY KEY,
                    student_name TEXT,
                    email TEXT,
                    batch TEXT,
                    status TEXT, -- 'sent', 'failed', 'pending'
                    last_sent_at TIMESTAMP,
                    last_error TEXT,
                    submission_count INTEGER DEFAULT 0
                )
            """)

    def _seed_initial_data_if_empty(self):
        """Seed master database with students from known DV Analytics datasets if empty."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM students")
            count = cur.fetchone()[0]
            if count > 0:
                return

        students_dict = {}

        # 1. From Collection-Recovery-Dashboard/google_sheet_data.csv
        gs_path = r"C:\Users\mdsaj\.gemini\antigravity\scratch\Collection-Recovery-Dashboard\google_sheet_data.csv"
        if os.path.exists(gs_path):
            try:
                df_gs = pd.read_csv(gs_path, dtype=str).fillna("")
                for _, r in df_gs.iterrows():
                    sid = r.get("STU_ID", "").strip()
                    name = r.get("STU_NAME", "").strip()
                    email = r.get("EMAIL ID", "").strip()
                    phone = r.get("MOBILE-1", "").strip()
                    batch = r.get("BATCH", "").strip()
                    course = r.get("COURSE", "").strip()
                    if sid and (name or email):
                        students_dict[sid] = {
                            "student_id": sid,
                            "student_name": name,
                            "email": email,
                            "phone": phone,
                            "batch": batch,
                            "course": course
                        }
            except Exception as e:
                print(f"Error seeding from google_sheet_data: {e}")

        # 2. From Daily-Collection-report Master Data (6,390 students)
        dc_path = r"C:\Users\mdsaj\.gemini\antigravity\scratch\Daily-Collection-report\DAILY COLLECTION 060222023 DV ANALYTICS (1) (2).xlsx"
        if os.path.exists(dc_path):
            try:
                df_dc = pd.read_excel(dc_path, sheet_name="Master Data", dtype=str).fillna("")
                for idx, r in df_dc.iterrows():
                    name = r.get("STU_NAME", "").strip()
                    email = r.get("EMAIL ID", "").strip()
                    phone = r.get("MOBILE-1", "").strip()
                    batch = r.get("BATCH", "").strip()
                    course = r.get("COURSE", "").strip()
                    
                    # Generate a clean surrogate ID if no ID provided in Daily Collection
                    clean_name_key = name.lower()
                    existing_id = None
                    for sid, s in students_dict.items():
                        if s["student_name"].lower() == clean_name_key and email:
                            existing_id = sid
                            break

                    sid = existing_id or f"GEN_{idx+1}"
                    if name or email:
                        students_dict[sid] = {
                            "student_id": sid,
                            "student_name": name,
                            "email": email,
                            "phone": phone,
                            "batch": batch,
                            "course": course
                        }
            except Exception as e:
                print(f"Error seeding from Daily Collection: {e}")

        # Insert seeded students in batch
        with self._get_connection() as conn:
            cur = conn.cursor()
            rows_to_insert = [
                (s["student_id"], s["student_name"], s["email"], s["phone"], s["batch"], s["course"])
                for s in students_dict.values()
            ]
            cur.executemany("""
                INSERT OR REPLACE INTO students (student_id, student_name, email, phone, batch, course)
                VALUES (?, ?, ?, ?, ?, ?)
            """, rows_to_insert)

    def lookup_student(self, student_id: str = "", student_name: str = "") -> Optional[Dict[str, Any]]:
        sid = (student_id or "").strip()
        sname = (student_name or "").strip()

        with self._get_connection() as conn:
            cur = conn.cursor()
            # 1. Exact ID match
            if sid:
                cur.execute("SELECT * FROM students WHERE UPPER(student_id) = UPPER(?) AND email != ''", (sid,))
                row = cur.fetchone()
                if row:
                    return dict(row)

            # 2. Exact Name match
            if sname:
                cur.execute("SELECT * FROM students WHERE UPPER(student_name) = UPPER(?) AND email != ''", (sname,))
                row = cur.fetchone()
                if row:
                    return dict(row)

            # 3. Normalized Name match (ignoring double spaces)
            if sname:
                norm_name = " ".join(sname.split()).upper()
                cur.execute("SELECT * FROM students WHERE REPLACE(UPPER(student_name), '  ', ' ') = ? AND email != ''", (norm_name,))
                row = cur.fetchone()
                if row:
                    return dict(row)

            # 4. Partial Name match
            if sname and len(sname) >= 4:
                cur.execute("SELECT * FROM students WHERE UPPER(student_name) LIKE ? AND email != '' LIMIT 1", (f"%{sname.upper()}%",))
                row = cur.fetchone()
                if row:
                    return dict(row)

        return None

    def update_email(self, student_id: str, email: str, student_name: str = "", batch: str = ""):
        sid = student_id.strip()
        mail = email.strip()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO students (student_id, student_name, email, batch)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(student_id) DO UPDATE SET
                    email = excluded.email,
                    student_name = COALESCE(NULLIF(excluded.student_name, ''), students.student_name),
                    batch = COALESCE(NULLIF(excluded.batch, ''), students.batch),
                    updated_at = CURRENT_TIMESTAMP
            """, (sid, student_name.strip(), mail, batch.strip()))

    def update_delivery_status(self, student_id: str, student_name: str, email: str, batch: str, status: str, error: str = "", submission_count: int = 0):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO assignment_delivery_status (student_id, student_name, email, batch, status, last_sent_at, last_error, submission_count)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(student_id) DO UPDATE SET
                    status = excluded.status,
                    last_sent_at = excluded.last_sent_at,
                    last_error = excluded.last_error,
                    submission_count = excluded.submission_count
            """, (student_id, student_name, email, batch, status, error, submission_count))

    def get_delivery_statuses(self) -> Dict[str, Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM assignment_delivery_status")
            return {r["student_id"]: dict(r) for r in cur.fetchall()}

student_directory = StudentDirectory()
