import csv
import json


def find_files(raw_dir, branches):
    found = []
    for branch, settings in branches.items():
        for path in sorted(raw_dir.glob(settings["file"])):
            found.append((path, branch, settings))
    return found


def read_file(path, branch, settings):
    if settings["type"] == "csv":
        return read_csv(path, branch, settings)
    return read_json(path, branch)


def read_csv(path, branch, settings):
    rows = []
    # utf-8-sig removes the hidden character Excel adds to the start of CSV files.
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=settings["delimiter"])
        for line_no, line in enumerate(reader, start=2):  # line 1 is the header
            row = {name: line.get(column) for name, column in settings["columns"].items()}
            row.update(file=path.name, row=line_no, branch=branch)
            rows.append(row)
    return rows


def read_json(path, branch):
    with open(path, encoding="utf-8") as f:
        orders = json.load(f)["orders"]
    rows = []
    # One order can have several products, so each product becomes its own row.
    for order_no, order in enumerate(orders, start=1):
        for line_no, line in enumerate(order["lines"], start=1):
            rows.append({
                "file": path.name,
                "row": order_no,
                "branch": branch,
                "transaction_id": f"{order['order_ref']}-{line_no}",
                "date": order["placed_at"],
                "sku": line["sku"],
                "quantity": line["qty"],
                "price": line["price"],
                "payment": order["payment"]["method"],
            })
    return rows
