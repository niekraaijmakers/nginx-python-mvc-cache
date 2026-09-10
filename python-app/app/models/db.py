"""
The real database. A tiny SQLite file - deliberately a *different* piece
of infrastructure than Redis, so "the database" and "the cache" are never
the same system (unlike the earlier version of this demo, which stored
items directly in a Redis list).

Nothing in here knows about caching. It's a plain persistence layer.
"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/data/app.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


@contextmanager
def _connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_item(item):
    with _connection() as conn:
        conn.execute(
            "INSERT INTO items (id, name, created_at) VALUES (?, ?, ?)",
            (item["id"], item["name"], item["createdAt"]),
        )


def fetch_all_items():
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at FROM items ORDER BY created_at"
        ).fetchall()
    return [{"id": r[0], "name": r[1], "createdAt": r[2]} for r in rows]
