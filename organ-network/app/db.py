"""
SQLite data-access layer (standard-library `sqlite3`).

Tables
    users        accounts (roles: donor, patient, coordinator, admin)
    hospitals    participating hospitals / procurement organizations
    donors       registered organ donors (with a blood group)
    organs       organs pledged by a donor (each has its own status)
    patients     recipients on the waiting list
    allocations  an organ assigned to a patient (the audit trail)

Every function takes an open connection so the service layer owns transactions
and tests can use an in-memory database.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('donor','patient','coordinator','admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS hospitals (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    city TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS donors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    blood_type  TEXT NOT NULL CHECK (blood_type IN ('O','A','B','AB')),
    age         INTEGER,
    hospital_id INTEGER REFERENCES hospitals(id),
    user_id     INTEGER REFERENCES users(id),
    status      TEXT NOT NULL DEFAULT 'registered'
                CHECK (status IN ('registered','available','closed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS organs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id   INTEGER NOT NULL REFERENCES donors(id),
    organ_type TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pledged'
               CHECK (status IN ('pledged','available','allocated','transplanted','discarded')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS patients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    blood_type    TEXT NOT NULL CHECK (blood_type IN ('O','A','B','AB')),
    organ_needed  TEXT NOT NULL,
    urgency       INTEGER NOT NULL DEFAULT 3 CHECK (urgency BETWEEN 1 AND 5),
    hospital_id   INTEGER REFERENCES hospitals(id),
    user_id       INTEGER REFERENCES users(id),
    status        TEXT NOT NULL DEFAULT 'waiting'
                  CHECK (status IN ('waiting','matched','transplanted')),
    registered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS allocations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    organ_id    INTEGER NOT NULL REFERENCES organs(id),
    patient_id  INTEGER NOT NULL REFERENCES patients(id),
    matched_by  INTEGER REFERENCES users(id),
    status      TEXT NOT NULL DEFAULT 'allocated'
                CHECK (status IN ('allocated','transplanted','cancelled')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_organs_status   ON organs(status);
CREATE INDEX IF NOT EXISTS idx_patients_status ON patients(status);
CREATE INDEX IF NOT EXISTS idx_patients_organ  ON patients(organ_needed);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _one(row) -> Optional[dict]:
    return dict(row) if row else None


def _all(rows) -> list[dict]:
    return [dict(r) for r in rows]


# --- users ------------------------------------------------------------------
def create_user(conn, name, email, password_hash, role) -> dict:
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?,?,?,?)",
        (name, email.lower(), password_hash, role),
    )
    conn.commit()
    return get_user_by_id(conn, cur.lastrowid)


def get_user_by_email(conn, email) -> Optional[dict]:
    return _one(conn.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone())


def get_user_by_id(conn, user_id) -> Optional[dict]:
    return _one(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


# --- hospitals --------------------------------------------------------------
def create_hospital(conn, name, city="") -> dict:
    cur = conn.execute("INSERT INTO hospitals (name, city) VALUES (?,?)", (name, city))
    conn.commit()
    return _one(conn.execute("SELECT * FROM hospitals WHERE id=?", (cur.lastrowid,)).fetchone())


def list_hospitals(conn) -> list[dict]:
    return _all(conn.execute("SELECT * FROM hospitals ORDER BY name").fetchall())


# --- donors -----------------------------------------------------------------
def create_donor(conn, *, name, blood_type, age, hospital_id, user_id=None) -> dict:
    cur = conn.execute(
        """INSERT INTO donors (name, blood_type, age, hospital_id, user_id)
           VALUES (?,?,?,?,?)""",
        (name, blood_type, age, hospital_id, user_id),
    )
    conn.commit()
    return get_donor(conn, cur.lastrowid)


def get_donor(conn, donor_id) -> Optional[dict]:
    return _one(conn.execute("SELECT * FROM donors WHERE id=?", (donor_id,)).fetchone())


def list_donors(conn) -> list[dict]:
    return _all(conn.execute("SELECT * FROM donors ORDER BY created_at DESC, id DESC").fetchall())


def set_donor_status(conn, donor_id, status) -> None:
    conn.execute("UPDATE donors SET status=? WHERE id=?", (status, donor_id))
    conn.commit()


# --- organs -----------------------------------------------------------------
def create_organ(conn, donor_id, organ_type, status="pledged") -> dict:
    cur = conn.execute(
        "INSERT INTO organs (donor_id, organ_type, status) VALUES (?,?,?)",
        (donor_id, organ_type, status),
    )
    conn.commit()
    return get_organ(conn, cur.lastrowid)


def get_organ(conn, organ_id) -> Optional[dict]:
    row = conn.execute(
        """SELECT o.*, d.blood_type AS donor_group, d.name AS donor_name
           FROM organs o JOIN donors d ON d.id = o.donor_id
           WHERE o.id=?""",
        (organ_id,),
    ).fetchone()
    return _one(row)


def set_organs_status_for_donor(conn, donor_id, from_status, to_status) -> None:
    conn.execute(
        "UPDATE organs SET status=? WHERE donor_id=? AND status=?",
        (to_status, donor_id, from_status),
    )
    conn.commit()


def set_organ_status(conn, organ_id, status) -> None:
    conn.execute("UPDATE organs SET status=? WHERE id=?", (status, organ_id))
    conn.commit()


def list_available_organs(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT o.*, d.blood_type AS donor_group, d.name AS donor_name
           FROM organs o JOIN donors d ON d.id = o.donor_id
           WHERE o.status='available'
           ORDER BY o.created_at DESC, o.id DESC"""
    ).fetchall()
    return _all(rows)


# --- patients ---------------------------------------------------------------
def create_patient(conn, *, name, blood_type, organ_needed, urgency, hospital_id, user_id=None) -> dict:
    cur = conn.execute(
        """INSERT INTO patients (name, blood_type, organ_needed, urgency, hospital_id, user_id)
           VALUES (?,?,?,?,?,?)""",
        (name, blood_type, organ_needed, urgency, hospital_id, user_id),
    )
    conn.commit()
    return get_patient(conn, cur.lastrowid)


def get_patient(conn, patient_id) -> Optional[dict]:
    return _one(conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone())


def list_patients(conn, *, status=None) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT * FROM patients WHERE status=? ORDER BY urgency DESC, registered_at ASC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM patients ORDER BY urgency DESC, registered_at ASC"
        ).fetchall()
    return _all(rows)


def set_patient_status(conn, patient_id, status) -> None:
    conn.execute("UPDATE patients SET status=? WHERE id=?", (status, patient_id))
    conn.commit()


# --- allocations ------------------------------------------------------------
def create_allocation(conn, organ_id, patient_id, matched_by) -> dict:
    cur = conn.execute(
        "INSERT INTO allocations (organ_id, patient_id, matched_by) VALUES (?,?,?)",
        (organ_id, patient_id, matched_by),
    )
    conn.commit()
    return get_allocation(conn, cur.lastrowid)


def get_allocation(conn, allocation_id) -> Optional[dict]:
    return _one(conn.execute("SELECT * FROM allocations WHERE id=?", (allocation_id,)).fetchone())


def set_allocation_status(conn, allocation_id, status) -> None:
    conn.execute("UPDATE allocations SET status=? WHERE id=?", (status, allocation_id))
    conn.commit()


def list_allocations(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT a.*, o.organ_type, p.name AS patient_name, d.name AS donor_name
           FROM allocations a
           JOIN organs o   ON o.id = a.organ_id
           JOIN donors d   ON d.id = o.donor_id
           JOIN patients p ON p.id = a.patient_id
           ORDER BY a.created_at DESC, a.id DESC"""
    ).fetchall()
    return _all(rows)


# --- stats ------------------------------------------------------------------
def stats(conn) -> dict:
    def scalar(sql, *p):
        return conn.execute(sql, p).fetchone()[0]

    return {
        "donors": scalar("SELECT COUNT(*) FROM donors"),
        "available_organs": scalar("SELECT COUNT(*) FROM organs WHERE status='available'"),
        "waiting_patients": scalar("SELECT COUNT(*) FROM patients WHERE status='waiting'"),
        "allocations": scalar("SELECT COUNT(*) FROM allocations WHERE status='allocated'"),
        "transplants": scalar("SELECT COUNT(*) FROM allocations WHERE status='transplanted'"),
    }
