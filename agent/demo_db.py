"""
Self-contained demo database for running agent/client.py directly.

databases/schema.sql is written for SQL Server and databases/db.py has no
live connection configured -- by design, tests monkeypatch it. This module
builds an equivalent SQLite database in memory purely so the agent has
something real to talk to for the demo. It is NOT the production schema;
once a real SQL Server connection is configured in databases/db.py, the
agent should be pointed at that instead (see agent/client.py).
"""

import os
import sqlite3
import tempfile

SCHEMA = """
CREATE TABLE Users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('technician', 'manager'))
);

CREATE TABLE Categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE Suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE SpareParts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_name TEXT NOT NULL,
    part_number TEXT NOT NULL UNIQUE,
    category_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    price REAL NOT NULL CHECK (price >= 0),
    location TEXT NOT NULL,
    minimum_stock INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'discontinued')),
    FOREIGN KEY (category_id) REFERENCES Categories(id),
    FOREIGN KEY (supplier_id) REFERENCES Suppliers(id)
);

CREATE TABLE AlternativeParts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id INTEGER NOT NULL,
    alternative_part_id INTEGER NOT NULL,
    FOREIGN KEY (part_id) REFERENCES SpareParts(id),
    FOREIGN KEY (alternative_part_id) REFERENCES SpareParts(id)
);

CREATE TABLE InventoryLogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    old_quantity INTEGER NOT NULL,
    new_quantity INTEGER NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY (part_id) REFERENCES SpareParts(id),
    FOREIGN KEY (user_id) REFERENCES Users(id)
);

-- ---------------------------------------------------------
-- AI Agent Memory Tables (mirrors databases/schema.sql's
-- EpisodicMemory / SemanticMemory, translated to SQLite so the
-- demo agent can actually exercise memory writes end to end).
-- ---------------------------------------------------------
CREATE TABLE EpisodicMemory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    promotion_reason TEXT NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE SemanticMemory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    change_reason TEXT,
    expires_at DATETIME,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

SEED = """
INSERT INTO Users (name, email, role) VALUES
    ('Sam Tech', 'sam@autofix.example', 'technician'),
    ('Priya Manager', 'priya@autofix.example', 'manager');

INSERT INTO Categories (name) VALUES ('Brakes'), ('Engine');

INSERT INTO Suppliers (name) VALUES ('NAPA Distribution');

INSERT INTO SpareParts
    (part_name, part_number, category_id, supplier_id, quantity, price, location, minimum_stock, status)
VALUES
    ('Front Brake Pad Set', 'BRK-001', 1, 1, 8, 42.50, 'A1-03', 5, 'active'),
    ('Rear Brake Pad Set',  'BRK-002', 1, 1, 2, 39.00, 'A1-04', 5, 'active'),
    ('Timing Belt',         'ENG-010', 2, 1, 0, 65.00, 'B2-01', 3, 'discontinued');

INSERT INTO AlternativeParts (part_id, alternative_part_id) VALUES (1, 2);
"""


_DB_PATH: str | None = None


def _new_seeded_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".sqlite", prefix="torque_tune_demo_")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executescript(SEED)
    conn.commit()
    conn.close()
    return path


def reset_demo_database() -> None:
    """
    Start a fresh, freshly-seeded demo database for one session.

    Call this once at the start of a run (agent/client.py's main()) --
    NOT on every get_connection() call. A plain ":memory:" database opened
    fresh per call (the previous behavior) silently discards every write
    between tool calls, which meant inventory updates never actually
    stuck and memory writes (episodic/semantic) were invisible to any
    later read in the same "session." This gives the whole demo run one
    consistent, file-backed database that every get_connection() call
    during that run reconnects to, while still giving each fresh run (and
    each test) an isolated, reseeded starting point.
    """
    global _DB_PATH
    old_path = _DB_PATH
    _DB_PATH = _new_seeded_db_path()
    if old_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass


def build_demo_connection() -> sqlite3.Connection:
    """Connection to the current session's persistent demo database,
    seeding one into existence on first use if reset_demo_database()
    was never called explicitly."""
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _new_seeded_db_path()
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
