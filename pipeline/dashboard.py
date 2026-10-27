import html
from datetime import datetime

from . import report, transform

STYLE = """
body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f4f6f9; color: #1f2933; }
header { background: #1f3864; color: white; padding: 24px 32px; }
header p { margin: 4px 0 0; opacity: 0.85; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
section { background: white; border-radius: 8px; padding: 20px 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
h2 { margin-top: 0; color: #1f3864; }
.part { font-size: 13px; font-weight: bold; letter-spacing: 1px; color: #2e74b5; text-transform: uppercase; }
.flow { font-size: 15px; color: #52606d; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; }
.card { flex: 1; min-width: 150px; background: #f4f6f9; border-radius: 8px; padding: 12px 16px; }
.card b { display: block; font-size: 28px; }
.good b { color: #2f855a; } .bad b { color: #c53030; }
pre { background: #1f2933; color: #e4e7eb; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 13px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin: 8px 0 16px; }
th, td { border: 1px solid #d9e2ec; padding: 6px 8px; text-align: left; }
th { background: #eef2f7; }
.before td { background: #fafafa; color: #52606d; }
.changed { background: #fff3c4 !important; font-weight: bold; }
.rejected td { background: #fde8e8; color: #9b2c2c; }
.bar { background: #2e74b5; height: 14px; border-radius: 3px; }
.note { color: #52606d; font-size: 14px; }
a { color: #2e74b5; }
.scroll { overflow-x: auto; }
"""

PREVIEW_LINES = {"csv": 8, "json": 22}

# Raw field -> clean field, shown side by side in the before/after table
COMPARE = [("transaction_id", "transaction_id", "Transaction"), ("date", "sold_at", "Date"),
           ("sku", "sku", "Product"), ("quantity", "quantity", "Qty"),
           ("price", "unit_price", "Price"), ("payment", "payment_method", "Payment")]


def esc(value):
    return html.escape("" if value is None else str(value))


def table(headers, rows):
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class='scroll'><table><tr>{head}</tr>{body}</table></div>"


def bars(rows, label_col, value_col):
    biggest = max(row[value_col] for row in rows)
    lines = []
    for row in rows:
        width = row[value_col] / biggest * 100
        lines.append([row[label_col], row[value_col], f'<div class="bar" style="width:{width:.0f}%"></div>'])
    body = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td style='width:55%'>{c}</td></tr>" for a, b, c in lines)
    return f"<table>{body}</table>"


def query(conn, report_name):
    result = conn.execute(report.REPORTS[report_name])
    columns = [column[0] for column in result.description]
    return columns, result.fetchall()


def raw_section(files):
    parts = []
    for path, branch, settings, rows in files:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        shown = "\n".join(lines[:PREVIEW_LINES[settings["type"]]])
        parts.append(f"<h3>{esc(branch)}: {esc(path.name)}</h3>"
                     f"<p class='note'>{len(rows)} rows. The start of the file, exactly as the branch sent it:</p>"
                     f"<pre>{esc(shown)}</pre>")
    return "".join(parts)


def before_after_section(files, rejected, products):
    header = "<tr><th></th>" + "".join(f"<th>{name}</th>" for _, _, name in COMPARE) + "</tr>"
    body = ""
    for path, branch, settings, rows in files:
        first_reject = next((r for r in rejected if r["file"] == path.name), None)
        examples = rows[:3] + ([first_reject] if first_reject else [])
        for row in examples:
            body += f"<tr class='before'><td>{esc(branch)} row {row['row']}<br>Before</td>"
            body += "".join(f"<td>{esc(row[raw])}</td>" for raw, _, _ in COMPARE) + "</tr>"
            try:
                if "reason" in row:
                    raise ValueError(row["reason"])
                sale = transform.clean_row(row, products, settings["date_format"])
            except ValueError as problem:
                body += f"<tr class='rejected'><td>After</td><td colspan='{len(COMPARE)}'>Rejected: {esc(problem)}</td></tr>"
                continue
            cells = ""
            for raw, clean, _ in COMPARE:
                after = f"{sale[clean]:.2f}" if clean == "unit_price" else sale[clean]
                changed = transform.text(row[raw]) != str(after)
                cells += f"<td class='{'changed' if changed else ''}'>{esc(after)}</td>"
            body += f"<tr><td>After</td>{cells}</tr>"
    return f"<div class='scroll'><table>{header}{body}</table></div>"


def write_dashboard(path, conn, files, rejected, products, totals):
    branch_cols, branch_rows = query(conn, "branch_summary.csv")
    product_cols, product_rows = query(conn, "top_products.csv")
    _, payment_rows = query(conn, "payment_methods.csv")
    sales = conn.execute("SELECT branch, transaction_id, sold_at, product_name, quantity, unit_price, "
                         "line_total, payment_method FROM sales ORDER BY branch, sold_at").fetchall()
    sale_headers = ["Branch", "Transaction", "Sold at", "Product", "Qty", "Price", "Total", "Payment"]
    saved = len(sales)

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sales Data Pipeline</title>
<style>{STYLE}</style>
</head>
<body>
<header>
  <h1>Sales Data Pipeline</h1>
  <p>Last run: {datetime.now():%d %B %Y at %H:%M} · Raw data → Extract → Transform → Load → Reports</p>
</header>
<main>

<section>
  <div class="part">Step 1 · Input</div>
  <h2>Raw data: what the branches sent</h2>
  <p class="flow">Three branches, three different formats, with mistakes in them.</p>
  {raw_section(files)}
</section>

<section>
  <div class="part">Step 2 · Transform</div>
  <h2>Before and after cleaning</h2>
  <p class="flow">The first rows of each file, and one rejected row. <span class="changed">Yellow</span> cells were standardised; red rows were rejected with a reason.</p>
  {before_after_section(files, rejected, products)}
</section>

<section>
  <div class="part">Step 3 · Output</div>
  <h2>Results</h2>
  <div class="cards">
    <div class="card"><b>{totals["read"]}</b>rows read</div>
    <div class="card good"><b>{saved}</b>sales in the database</div>
    <div class="card bad"><b>{len(rejected)}</b>rows rejected</div>
    <div class="card"><b>{len(files)}</b>branch files</div>
  </div>
  <h3>Revenue by branch</h3>
  {table(branch_cols, branch_rows)}
  {bars([dict(zip(branch_cols, r)) for r in branch_rows], "branch", "revenue")}
  <h3>Top 5 products</h3>
  {table(product_cols, product_rows)}
  <h3>Payment methods</h3>
  {bars([{"method": m, "sales": n} for m, n in payment_rows], "method", "sales")}
</section>

<section>
  <div class="part">Step 3 · Output</div>
  <h2>Rejected rows ({len(rejected)})</h2>
  <p class="flow">Kept out of the database, each with the reason, so someone can fix them.</p>
  {table(["File", "Row", "Reason", "Transaction", "Date", "Product", "Qty", "Price"],
         [[r["file"], r["row"], r["reason"], r["transaction_id"], r["date"], r["sku"], r["quantity"], r["price"]]
          for r in rejected])}
</section>

<section>
  <div class="part">Step 3 · Output</div>
  <h2>Clean data in the database ({saved} sales)</h2>
  {table(sale_headers, sales[:10])}
  <details><summary>Show all {saved} sales</summary>{table(sale_headers, sales)}</details>
  <p class="note">Download: <a href="warehouse.db">warehouse.db</a> · <a href="rejects.csv">rejects.csv</a> ·
  <a href="reports/branch_summary.csv">branch_summary.csv</a> · <a href="reports/daily_sales.csv">daily_sales.csv</a> ·
  <a href="reports/top_products.csv">top_products.csv</a> · <a href="reports/payment_methods.csv">payment_methods.csv</a></p>
</section>

</main>
</body>
</html>
"""
    path.write_text(page, encoding="utf-8")
