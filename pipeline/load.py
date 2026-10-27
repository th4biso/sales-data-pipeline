"""Load: save clean sales into a SQLite database, and rejected rows into a CSV file."""

import csv
import sqlite3

CREATE_SALES_TABLE = """
CREATE TABLE IF NOT EXISTS sales (
    branch          TEXT    NOT NULL,
    transaction_id  TEXT    NOT NULL,
    sold_at         TEXT    NOT NULL,
    sku             TEXT    NOT NULL,
    product_name    TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    quantity        INTEGER NOT NULL,
    unit_price      REAL    NOT NULL,
    line_total      REAL    NOT NULL,
    payment_method  TEXT    NOT NULL,
    source_file     TEXT    NOT NULL,
    PRIMARY KEY (branch, transaction_id)    -- the same sale can never be saved twice
)
"""

# INSERT OR IGNORE: if the sale is already in the database, skip it.
# That is what makes the pipeline safe to run again and again.
INSERT_SALE = """
INSERT OR IGNORE INTO sales (branch, transaction_id, sold_at, sku, product_name, category,
                             quantity, unit_price, line_total, payment_method, source_file)
VALUES (:branch, :transaction_id, :sold_at, :sku, :product_name, :category,
        :quantity, :unit_price, :line_total, :payment_method, :source_file)
"""

REJECT_COLUMNS = ["file", "row", "branch", "transaction_id", "reason", "date", "sku", "quantity", "price", "payment"]


def connect(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_SALES_TABLE)
    return conn


def save_sales(conn, sales):
    """Save the sales and return how many were new."""
    before = conn.total_changes
    with conn:  # one transaction: either every row is saved or none are
        conn.executemany(INSERT_SALE, sales)
    return conn.total_changes - before


def save_rejects(path, rejected):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REJECT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rejected)
