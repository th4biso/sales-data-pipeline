"""Extract: find each branch's export file and read every row into the same shape.

Nothing is cleaned here. Values are kept exactly as the branch sent them,
so that a rejected row shows what was actually received.
"""

import csv
import json


def find_files(raw_dir, branches):
    """Return (file, branch, settings) for every export file in the raw folder."""
    found = []
    for branch, settings in branches.items():
        for path in sorted(raw_dir.glob(settings["file"])):
            found.append((path, branch, settings))
    return found


def read_file(path, branch, settings):
    """Read one export file into a list of rows. Every row has the same keys."""
    if settings["type"] == "csv":
        return read_csv(path, branch, settings)
    return read_json(path, branch)


def read_csv(path, branch, settings):
    rows = []
    # utf-8-sig removes the hidden character Excel adds at the start of CSV files.
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=settings["delimiter"])
        # Line 1 is the header, so the data starts on line 2.
        for line_no, line in enumerate(reader, start=2):
            row = {name: line.get(column) for name, column in settings["columns"].items()}
            row.update(file=path.name, row=line_no, branch=branch)
            rows.append(row)
    return rows


def read_json(path, branch):
    """One online order can contain several products, so each product becomes its own row."""
    with open(path, encoding="utf-8") as f:
        orders = json.load(f)["orders"]
    rows = []
    for order_no, order in enumerate(orders, start=1):
        for line_no, line in enumerate(order["lines"], start=1):
            rows.append({
                "file": path.name,
                "row": order_no,
                "branch": branch,
                # Order WEB-30001 with two products becomes WEB-30001-1 and WEB-30001-2.
                "transaction_id": f"{order['order_ref']}-{line_no}",
                "date": order["placed_at"],
                "sku": line["sku"],
                "quantity": line["qty"],
                "price": line["price"],
                "payment": order["payment"]["method"],
            })
    return rows
