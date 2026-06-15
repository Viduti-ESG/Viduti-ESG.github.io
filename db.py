"""
Green Curve — SQLite database init and helpers.
Creates greencurve.db in the same directory as this file.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "greencurve.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    UNIQUE NOT NULL,
                name          TEXT    NOT NULL,
                org           TEXT    DEFAULT '',
                password_hash TEXT    NOT NULL,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active     INTEGER  DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                company_name TEXT    NOT NULL,
                added_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, company_name)
            );

            CREATE TABLE IF NOT EXISTS watchlist_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                company_name  TEXT    NOT NULL,
                snapshot_data TEXT    NOT NULL,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS watchlist_prefs (
                user_id   INTEGER PRIMARY KEY,
                prefs_json TEXT NOT NULL DEFAULT '{"tier_change":true,"high_risk":true}',
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS cap_progress (
                user_id      INTEGER NOT NULL,
                company_name TEXT    NOT NULL,
                rec_id       TEXT    NOT NULL,
                status       TEXT    DEFAULT 'Not Started',
                assignee     TEXT    DEFAULT '',
                due_date     TEXT    DEFAULT '',
                notes        TEXT    DEFAULT '',
                updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, company_name, rec_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
