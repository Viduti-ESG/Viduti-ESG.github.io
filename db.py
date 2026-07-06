"""
Green Curve — SQLite database init and helpers.
Creates greencurve.db in the same directory as this file.
"""

import os
import sqlite3
import threading
from pathlib import Path

_db_env = os.environ.get("GC_DB_PATH", "")
DB_PATH = Path(_db_env) if _db_env else Path(__file__).parent / "greencurve.db"

_local = threading.local()


def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_conn() -> sqlite3.Connection:
    """Return the thread-local SQLite connection, opening it if needed."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _open_conn()
        _local.conn = conn
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
                role          TEXT    DEFAULT 'user',
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
                anomaly_flags       TEXT    DEFAULT '[]',
                bottleneck_solutions TEXT   DEFAULT '[]',
                sector_benchmark    TEXT    DEFAULT '{}',
                safety_metrics      TEXT    DEFAULT '{}',
                energy_mix          TEXT    DEFAULT '{}',
                waste_profile       TEXT    DEFAULT '{}',
                governance_signals  TEXT    DEFAULT '{}',
                ghg_intensity       REAL,
                updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_companies_sector     ON companies(sector);
            CREATE INDEX IF NOT EXISTS idx_companies_risk_tier  ON companies(risk_tier);
            CREATE INDEX IF NOT EXISTS idx_companies_esg_score  ON companies(esg_risk_score);
            -- cin is the primary lookup key for /api/esg/company/{cin} and /api/esg/by-cin;
            -- without this index each lookup is a full table scan of all companies.
            CREATE INDEX IF NOT EXISTS idx_companies_cin         ON companies(cin);

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id      INTEGER PRIMARY KEY,
                company_name TEXT    DEFAULT '',
                cin          TEXT    DEFAULT '',
                nse_symbol   TEXT    DEFAULT '',
                sector       TEXT    DEFAULT '',
                profile_json TEXT    DEFAULT '{}',
                updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS password_resets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                token      TEXT    UNIQUE NOT NULL,
                expires_at DATETIME NOT NULL,
                used       INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            -- Stores summary, regulations, factor_matrix, supply_chain_global, etc.
            CREATE TABLE IF NOT EXISTS esg_meta (
                key        TEXT    PRIMARY KEY,
                value      TEXT    NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # ── Lightweight migrations ───────────────────────────────────────────
        # CREATE TABLE IF NOT EXISTS cannot add columns to a table that already
        # exists, so columns introduced in later versions must be backfilled
        # here or pre-existing production DBs will be missing them. (The missing
        # `role` column caused get_current_user to 500 on every authed request.)
        ucols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")

        # XBRL content-upgrade columns (bottlenecks / benchmarks / hard S&E metrics).
        # Added to pre-existing prod DBs via ALTER; new DBs get them from CREATE above.
        ccols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
        for col, typ in [
            ("bottleneck_solutions", "TEXT DEFAULT '[]'"),
            ("sector_benchmark",     "TEXT DEFAULT '{}'"),
            ("safety_metrics",       "TEXT DEFAULT '{}'"),
            ("energy_mix",           "TEXT DEFAULT '{}'"),
            ("waste_profile",        "TEXT DEFAULT '{}'"),
            ("governance_signals",   "TEXT DEFAULT '{}'"),
            ("ghg_intensity",        "REAL"),
        ]:
            if col not in ccols:
                conn.execute(f"ALTER TABLE companies ADD COLUMN {col} {typ}")
