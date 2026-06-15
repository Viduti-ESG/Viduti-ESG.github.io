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

            -- ── ESG Company Data ───────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS companies (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name        TEXT    UNIQUE NOT NULL,
                cin                 TEXT    DEFAULT '',
                nse_symbol          TEXT    DEFAULT '',
                sector              TEXT    DEFAULT '',
                products            TEXT    DEFAULT '',
                revenue_crore       REAL    DEFAULT 0,
                financial_year      TEXT    DEFAULT '',
                esg_risk_score      REAL    DEFAULT 0,
                risk_tier           TEXT    DEFAULT 'Medium',
                risk_breakdown      TEXT    DEFAULT '{}',
                top_risk_factors    TEXT    DEFAULT '[]',
                financial_exposure  TEXT    DEFAULT '{}',
                supply_chain        TEXT    DEFAULT '{}',
                governance          TEXT    DEFAULT '{}',
                double_materiality  TEXT    DEFAULT '{}',
                esg_targets         TEXT    DEFAULT '[]',
                materials_exposed   TEXT    DEFAULT '[]',
                ai_summary          TEXT    DEFAULT '',
                updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_companies_sector     ON companies(sector);
            CREATE INDEX IF NOT EXISTS idx_companies_risk_tier  ON companies(risk_tier);
            CREATE INDEX IF NOT EXISTS idx_companies_esg_score  ON companies(esg_risk_score);

            -- Stores summary, regulations, factor_matrix, supply_chain_global, etc.
            CREATE TABLE IF NOT EXISTS esg_meta (
                key        TEXT    PRIMARY KEY,
                value      TEXT    NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
