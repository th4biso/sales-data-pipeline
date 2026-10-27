import html
from datetime import datetime

from . import transform

TITLES = {"SANDTON": "Sandton sales sent in", "DURBAN": "Durban sales sent in", "ONLINE": "Online orders sent in"}

# raw field, clean field, column name
COLUMNS = [("transaction_id", "transaction_id", "Transaction"), ("date", "sold_at", "Date"),
           ("sku", "sku", "Product"), ("quantity", "quantity", "Qty"),
           ("price", "unit_price", "Price"), ("payment", "payment_method", "Payment")]


def esc(value):
    return html.escape("" if value is None else str(value))


def write_dashboard(path, conn, files, rejected, products, totals):
    page = ["<html><head><meta charset='utf-8'><title>Sales pipeline</title></head><body>"]
    page.append(f"<p>Last run: {datetime.now()}</p>")

    page.append("<h2>Step 1: Raw data</h2>")
    for file, branch, settings, rows in files:
        lines = file.read_text(encoding="utf-8-sig").splitlines()
        show = 8 if settings["type"] == "csv" else 22
        page.append(f"<h3>{TITLES[branch]} ({len(rows)} rows)</h3>")
        page.append("<pre>" + esc("\n".join(lines[:show])) + "\n...</pre>")

    page.append("<h2>Step 2: Transform</h2>")
    page.append("<p>Before and after cleaning. Yellow = changed. Red = rejected.</p>")
    page.append("<table border='1' cellpadding='4'>")
    page.append("<tr><th></th>" + "".join(f"<th>{name}</th>" for _, _, name in COLUMNS) + "</tr>")
    for file, branch, settings, rows in files:
        first_reject = next((r for r in rejected if r["file"] == file.name), None)
        examples = rows[:3] + ([first_reject] if first_reject else [])
        for row in examples:
            page.append(f"<tr><td>{branch} row {row['row']} before</td>"
                        + "".join(f"<td>{esc(row[raw])}</td>" for raw, _, _ in COLUMNS) + "</tr>")
            if "reason" in row:
                page.append(f"<tr><td>after</td><td colspan='6' style='color:red'>REJECTED - {esc(row['reason'])}</td></tr>")
                continue
            sale = transform.clean_row(row, products, settings["date_format"])
            cells = ""
            for raw, clean, _ in COLUMNS:
                after = f"{sale[clean]:.2f}" if clean == "unit_price" else sale[clean]
                if transform.text(row[raw]) != str(after):
                    cells += f"<td style='background:yellow'>{esc(after)}</td>"
                else:
                    cells += f"<td>{esc(after)}</td>"
            page.append(f"<tr><td>after</td>{cells}</tr>")
    page.append("</table>")

    saved = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    page.append("<h2>Step 3: Output</h2>")
    page.append(f"<p>Rows read - {totals['read']}<br>Sales in the database - {saved}<br>Rows rejected - {len(rejected)}</p>")

    page.append("<h3>Revenue by branch</h3><p>")
    for branch, revenue in conn.execute("SELECT branch, ROUND(SUM(line_total), 2) FROM sales GROUP BY branch ORDER BY 2 DESC"):
        page.append(f"{branch} - R{revenue}<br>")
    page.append("</p>")


    page.append("<h3>Payment methods</h3><p>")
    for method, count in conn.execute("SELECT payment_method, COUNT(*) FROM sales GROUP BY payment_method ORDER BY 2 DESC"):
        page.append(f"{method} - {count}<br>")
    page.append("</p>")

    page.append("<h3>Rejected rows</h3><p>")
    for r in rejected:
        page.append(f"{esc(r['file'])} row {r['row']} - {esc(r['reason'])}<br>")
    page.append("</p>")

    path.write_text("\n".join(page), encoding="utf-8")
