"""Reports: SQL queries on the database, each saved as a CSV file."""

import csv

REPORTS = {
    "branch_summary.csv": """
        SELECT branch, COUNT(*) AS sales, SUM(quantity) AS units, ROUND(SUM(line_total), 2) AS revenue
        FROM sales
        GROUP BY branch
        ORDER BY revenue DESC""",
    "daily_sales.csv": """
        SELECT date(sold_at) AS day, branch, COUNT(*) AS sales, ROUND(SUM(line_total), 2) AS revenue
        FROM sales
        GROUP BY day, branch
        ORDER BY day, branch""",
    "top_products.csv": """
        SELECT product_name, SUM(quantity) AS units, ROUND(SUM(line_total), 2) AS revenue
        FROM sales
        GROUP BY product_name
        ORDER BY revenue DESC
        LIMIT 5""",
    "payment_methods.csv": """
        SELECT payment_method, COUNT(*) AS sales
        FROM sales
        GROUP BY payment_method
        ORDER BY sales DESC""",
}


def write_reports(conn, report_dir):
    report_dir.mkdir(parents=True, exist_ok=True)
    for file_name, sql in REPORTS.items():
        result = conn.execute(sql)
        with open(report_dir / file_name, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([column[0] for column in result.description])  # header row
            writer.writerows(result.fetchall())
