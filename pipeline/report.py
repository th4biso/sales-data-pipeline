"""Reports built from the warehouse after each run."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

DAILY_SALES = """
SELECT sale_date, branch,
       COUNT(DISTINCT transaction_id) AS transactions,
       SUM(quantity)                  AS units,
       ROUND(SUM(line_total), 2)      AS revenue
FROM fact_sales
GROUP BY sale_date, branch
ORDER BY sale_date, branch
"""

BRANCH_SUMMARY = """
SELECT branch,
       COUNT(*)                                   AS sale_lines,
       SUM(quantity)                              AS units,
       ROUND(SUM(line_total), 2)                  AS revenue,
       ROUND(SUM(line_total) / COUNT(DISTINCT sale_date), 2) AS avg_daily_revenue,
       ROUND(100.0 * SUM(line_total) / (SELECT SUM(line_total) FROM fact_sales), 1) AS share_pct
FROM fact_sales
GROUP BY branch
ORDER BY revenue DESC
"""

TOP_PRODUCTS = """
SELECT p.sku, p.product_name, p.category,
       SUM(s.quantity)             AS units,
       ROUND(SUM(s.line_total), 2) AS revenue
FROM fact_sales s
JOIN dim_product p ON p.sku = s.sku
GROUP BY p.sku, p.product_name, p.category
ORDER BY revenue DESC
LIMIT 5
"""

PAYMENT_MIX = """
SELECT payment_method,
       COUNT(*)                                                         AS sale_lines,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM fact_sales), 1)   AS share_pct
FROM fact_sales
GROUP BY payment_method
ORDER BY sale_lines DESC
"""


def _query(conn: sqlite3.Connection, sql: str) -> tuple[list[str], list[tuple]]:
    cursor = conn.execute(sql)
    return [d[0] for d in cursor.description], cursor.fetchall()


def _write_csv(path: Path, columns: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)


def _markdown_table(columns: list[str], rows: list[tuple]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def build_reports(conn: sqlite3.Connection, report_dir: Path, run_summary: dict) -> Path:
    """Write the CSV reports and a markdown run summary. Returns the summary path."""
    _write_csv(report_dir / "daily_sales.csv", *_query(conn, DAILY_SALES))
    branch_cols, branch_rows = _query(conn, BRANCH_SUMMARY)
    _write_csv(report_dir / "branch_summary.csv", branch_cols, branch_rows)
    top_cols, top_rows = _query(conn, TOP_PRODUCTS)
    pay_cols, pay_rows = _query(conn, PAYMENT_MIX)

    s = run_summary
    parts = [
        f"# Pipeline run {s['run_id']}",
        "",
        f"- Files processed: **{s['files_processed']}**, skipped as already loaded: **{s['files_skipped']}**",
        f"- Rows read: **{s['rows_read']}**, loaded: **{s['rows_loaded']}**, rejected: **{s['rows_rejected']}**"
        + (f", already in the warehouse: **{s['rows_already_loaded']}**" if s.get("rows_already_loaded") else ""),
        "",
    ]
    if s["reject_reasons"]:
        parts += ["## Why rows were rejected", "",
                  _markdown_table(["reason", "rows"], sorted(s["reject_reasons"].items(), key=lambda kv: -kv[1])), ""]
    if s["fixes"]:
        parts += ["## What was fixed automatically", "",
                  _markdown_table(["fix", "rows"], sorted(s["fixes"].items(), key=lambda kv: -kv[1])), ""]
    parts += ["## Revenue by branch (all data in the warehouse)", "", _markdown_table(branch_cols, branch_rows), "",
              "## Top five products", "", _markdown_table(top_cols, top_rows), "",
              "## Payment mix", "", _markdown_table(pay_cols, pay_rows), ""]

    summary_path = report_dir / f"run_summary_{s['run_id']}.md"
    summary_path.write_text("\n".join(parts), encoding="utf-8")
    return summary_path
