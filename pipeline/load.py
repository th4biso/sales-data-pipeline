"""Load: write clean sales into a SQLite warehouse, and the rejects to CSV.

Loading is idempotent:
* a file whose contents (SHA-256) were already loaded is skipped, and
* a sale already in the warehouse is never inserted twice,
so the pipeline can be re-run safely after a failure.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .transform import CleanSale, Product, Reject

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_product (
    sku           TEXT PRIMARY KEY,
    product_name  TEXT NOT NULL,
    category      TEXT NOT NULL,
    list_price    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_sales (
    branch          TEXT    NOT NULL,
    transaction_id  TEXT    NOT NULL,
    sold_at         TEXT    NOT NULL,
    sale_date       TEXT    NOT NULL,
    sku             TEXT    NOT NULL REFERENCES dim_product (sku),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      REAL    NOT NULL CHECK (unit_price > 0),
    line_total      REAL    NOT NULL,
    payment_method  TEXT    NOT NULL,
    price_source    TEXT    NOT NULL,
    source_file     TEXT    NOT NULL,
    run_id          TEXT    NOT NULL,
    PRIMARY KEY (branch, transaction_id)
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON fact_sales (sale_date, branch);

CREATE TABLE IF NOT EXISTS ingested_files (
    sha256         TEXT PRIMARY KEY,
    file_name      TEXT    NOT NULL,
    rows_read      INTEGER NOT NULL,
    rows_loaded    INTEGER NOT NULL,
    rows_rejected  INTEGER NOT NULL,
    run_id         TEXT    NOT NULL,
    loaded_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           TEXT PRIMARY KEY,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    files_processed  INTEGER,
    files_skipped    INTEGER,
    rows_read        INTEGER,
    rows_loaded      INTEGER,
    rows_rejected    INTEGER,
    status           TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def already_ingested(conn: sqlite3.Connection, sha256: str) -> bool:
    return conn.execute("SELECT 1 FROM ingested_files WHERE sha256 = ?", (sha256,)).fetchone() is not None


def upsert_products(conn: sqlite3.Connection, catalogue: dict[str, Product]) -> None:
    conn.executemany(
        """INSERT INTO dim_product (sku, product_name, category, list_price) VALUES (?, ?, ?, ?)
           ON CONFLICT (sku) DO UPDATE SET product_name = excluded.product_name,
                                           category = excluded.category,
                                           list_price = excluded.list_price""",
        [(p.sku, p.product_name, p.category, float(p.list_price)) for p in catalogue.values()],
    )


def insert_sales(conn: sqlite3.Connection, sales: list[CleanSale], run_id: str) -> int:
    """Insert sales; ones already in the warehouse are left alone. Returns rows inserted."""
    before = conn.total_changes
    conn.executemany(
        """INSERT INTO fact_sales (branch, transaction_id, sold_at, sale_date, sku, quantity, unit_price,
                                   line_total, payment_method, price_source, source_file, run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (branch, transaction_id) DO NOTHING""",
        [(s.branch, s.transaction_id, s.sold_at.isoformat(sep=" "), s.sold_at.date().isoformat(), s.sku,
          s.quantity, float(s.unit_price), float(s.line_total), s.payment_method, s.price_source,
          s.source_file, run_id) for s in sales],
    )
    return conn.total_changes - before


def record_file(conn: sqlite3.Connection, sha256: str, file_name: str, rows_read: int, rows_loaded: int,
                rows_rejected: int, run_id: str) -> None:
    conn.execute(
        """INSERT INTO ingested_files (sha256, file_name, rows_read, rows_loaded, rows_rejected, run_id, loaded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (sha256) DO UPDATE SET rows_read = excluded.rows_read, rows_loaded = excluded.rows_loaded,
               rows_rejected = excluded.rows_rejected, run_id = excluded.run_id, loaded_at = excluded.loaded_at""",
        (sha256, file_name, rows_read, rows_loaded, rows_rejected, run_id, datetime.now().isoformat(timespec="seconds")),
    )


def start_run(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("INSERT INTO pipeline_runs (run_id, started_at, status) VALUES (?, ?, 'running')",
                 (run_id, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def finish_run(conn: sqlite3.Connection, run_id: str, stats: dict, status: str) -> None:
    conn.execute(
        """UPDATE pipeline_runs SET finished_at = ?, files_processed = ?, files_skipped = ?, rows_read = ?,
               rows_loaded = ?, rows_rejected = ?, status = ? WHERE run_id = ?""",
        (datetime.now().isoformat(timespec="seconds"), stats["files_processed"], stats["files_skipped"],
         stats["rows_read"], stats["rows_loaded"], stats["rows_rejected"], status, run_id),
    )
    conn.commit()


def write_clean_csv(path: Path, sales: list[CleanSale]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["branch", "transaction_id", "sold_at", "sku", "product_name", "category", "quantity",
                         "unit_price", "line_total", "payment_method", "price_source", "source_file"])
        for s in sales:
            writer.writerow([s.branch, s.transaction_id, s.sold_at.isoformat(sep=" "), s.sku, s.product_name,
                             s.category, s.quantity, s.unit_price, s.line_total, s.payment_method,
                             s.price_source, s.source_file])


def write_rejects_csv(path: Path, rejects: list[Reject]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source_file", "row_number", "branch", "transaction_id", "reason", "raw_record"])
        for r in rejects:
            writer.writerow([r.source_file, r.row_number, r.branch, r.transaction_id, r.reason,
                             json.dumps(r.raw, ensure_ascii=False, default=str)])
