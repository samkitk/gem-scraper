"""
SQLite database for tracking scraped GeM tenders.
Prevents duplicates and stores all extracted metadata.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bid_number TEXT UNIQUE NOT NULL,
            document_id TEXT,
            category TEXT,
            department TEXT,
            department_address TEXT,
            items TEXT,
            quantity TEXT,
            start_date TEXT,
            end_date TEXT,
            estimated_value TEXT,
            pdf_path TEXT,
            folder_path TEXT,
            scraped_at TEXT NOT NULL,
            processed INTEGER DEFAULT 0,
            summary TEXT,
            scope_of_work TEXT,
            eligibility TEXT,
            key_dates TEXT,
            budget_range TEXT,
            contact_info TEXT,
            extra_metadata TEXT,
            location TEXT
        );

        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            link_text TEXT,
            is_relevant INTEGER DEFAULT 0,
            link_type TEXT,
            downloaded INTEGER DEFAULT 0,
            local_path TEXT,
            description TEXT,
            FOREIGN KEY (tender_id) REFERENCES tenders(id)
        );

        CREATE TABLE IF NOT EXISTS scrape_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT NOT NULL,
            new_tenders_found INTEGER DEFAULT 0,
            total_tenders_scraped INTEGER DEFAULT 0,
            status TEXT DEFAULT 'completed',
            error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tenders_bid ON tenders(bid_number);
        CREATE INDEX IF NOT EXISTS idx_tenders_processed ON tenders(processed);
        CREATE INDEX IF NOT EXISTS idx_links_tender ON links(tender_id);
    """)
    conn.commit()
    conn.close()


def tender_exists(bid_number: str) -> bool:
    """Check if a tender with this bid number already exists."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM tenders WHERE bid_number = ?", (bid_number,)
    ).fetchone()
    conn.close()
    return row is not None


def insert_tender(tender_data: dict) -> int:
    """Insert a new tender. Returns the row ID. Skips if duplicate."""
    if tender_exists(tender_data["bid_number"]):
        return -1

    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO tenders (
            bid_number, document_id, category, department,
            department_address, items, quantity, start_date,
            end_date, estimated_value, pdf_path, folder_path,
            scraped_at, extra_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tender_data.get("bid_number"),
        tender_data.get("document_id"),
        tender_data.get("category"),
        tender_data.get("department"),
        tender_data.get("department_address"),
        tender_data.get("items"),
        tender_data.get("quantity"),
        tender_data.get("start_date"),
        tender_data.get("end_date"),
        tender_data.get("estimated_value"),
        tender_data.get("pdf_path"),
        tender_data.get("folder_path"),
        datetime.now().isoformat(),
        json.dumps(tender_data.get("extra_metadata", {})),
    ))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def insert_links(tender_id: int, links: list[dict]):
    """Insert extracted links for a tender."""
    conn = get_connection()
    for link in links:
        conn.execute("""
            INSERT INTO links (tender_id, url, link_text, is_relevant, link_type, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            tender_id,
            link.get("url"),
            link.get("link_text"),
            1 if link.get("is_relevant") else 0,
            link.get("link_type"),
            link.get("description"),
        ))
    conn.commit()
    conn.close()


def update_tender_processing(bid_number: str, data: dict):
    """Update a tender with processing results (summary, scope, etc.)."""
    conn = get_connection()
    conn.execute("""
        UPDATE tenders SET
            processed = 1,
            summary = ?,
            scope_of_work = ?,
            eligibility = ?,
            key_dates = ?,
            budget_range = ?,
            contact_info = ?,
            estimated_value = COALESCE(?, estimated_value),
            location = ?
        WHERE bid_number = ?
    """, (
        data.get("summary"),
        data.get("scope_of_work"),
        data.get("eligibility"),
        data.get("key_dates"),
        data.get("budget_range"),
        data.get("contact_info"),
        data.get("estimated_value"),
        data.get("location"),
        bid_number,
    ))
    conn.commit()
    conn.close()


def update_link_downloaded(link_id: int, local_path: str):
    """Mark a link as downloaded."""
    conn = get_connection()
    conn.execute(
        "UPDATE links SET downloaded = 1, local_path = ? WHERE id = ?",
        (local_path, link_id)
    )
    conn.commit()
    conn.close()


def get_unprocessed_tenders() -> list[dict]:
    """Get all tenders that haven't been processed yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tenders WHERE processed = 0"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tender_by_bid(bid_number: str) -> dict | None:
    """Get a tender by bid number."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tenders WHERE bid_number = ?", (bid_number,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_tenders(limit: int = 100) -> list[dict]:
    """Get all tenders, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tenders ORDER BY scraped_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_links_for_tender(tender_id: int, relevant_only: bool = False) -> list[dict]:
    """Get links for a tender."""
    conn = get_connection()
    query = "SELECT * FROM links WHERE tender_id = ?"
    if relevant_only:
        query += " AND is_relevant = 1"
    rows = conn.execute(query, (tender_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_scrape_run(new_count: int, total_count: int, status: str = "completed", error: str = None):
    """Log a scrape run."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO scrape_runs (run_at, new_tenders_found, total_tenders_scraped, status, error)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), new_count, total_count, status, error))
    conn.commit()
    conn.close()


def get_tender_stats() -> dict:
    """Get summary statistics."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0]
    processed = conn.execute("SELECT COUNT(*) FROM tenders WHERE processed = 1").fetchone()[0]
    unprocessed = conn.execute("SELECT COUNT(*) FROM tenders WHERE processed = 0").fetchone()[0]
    total_links = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    relevant_links = conn.execute("SELECT COUNT(*) FROM links WHERE is_relevant = 1").fetchone()[0]
    conn.close()
    return {
        "total_tenders": total,
        "processed": processed,
        "unprocessed": unprocessed,
        "total_links": total_links,
        "relevant_links": relevant_links,
    }


# Initialize DB on import
init_db()
