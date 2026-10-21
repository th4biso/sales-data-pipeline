"""Create the sample raw exports in data/raw and the product catalogue in data/reference.

Three branches export the same kind of data in three different shapes, the way
real point-of-sale systems do. A share of the rows is deliberately broken
(bad dates, unknown products, impossible quantities, duplicates, odd number
formats) so the pipeline has something to clean.

Usage:
    python scripts/make_sample_data.py
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
REFERENCE = ROOT / "data" / "reference"
rng = random.Random(7)

CATALOGUE = [
    ("EL-1001", "Wireless Earbuds", "Electronics", 549.00),
    ("EL-1002", "USB-C Fast Charger 25W", "Electronics", 199.00),
    ("EL-1005", "Power Bank 20000mAh", "Electronics", 449.00),
    ("HK-2002", "Electric Kettle 1.7L", "Home & Kitchen", 349.00),
    ("HK-2004", "Glass Food Containers (10 pc)", "Home & Kitchen", 299.00),
    ("BP-3001", "Vitamin C Serum 30ml", "Beauty & Personal Care", 229.00),
    ("BP-3002", "Shea Butter Body Lotion", "Beauty & Personal Care", 139.00),
    ("BP-3004", "Hair Clipper Set", "Beauty & Personal Care", 1199.00),
    ("SO-4004", "Insulated Water Bottle 1L", "Sports & Outdoors", 229.00),
    ("OS-5002", "Gel Pens (12 pack)", "Office & Stationery", 89.00),
    ("GR-6001", "Rooibos Tea (80 bags)", "Groceries", 79.00),
    ("GR-6002", "Biltong Snack Pack 250g", "Groceries", 169.00),
    ("GR-6004", "Filter Coffee 1kg", "Groceries", 229.00),
]
SKUS = [c[0] for c in CATALOGUE]
PRICE = {c[0]: c[3] for c in CATALOGUE}
MONTH_START = datetime(2026, 9, 1, 8, 0)


def random_sale_time() -> datetime:
    return MONTH_START + timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 12), minutes=rng.randint(0, 59))


def za_amount(value: float) -> str:
    """'R1 199,00' style, as many South African systems export it."""
    whole, cents = f"{value:.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return "R" + " ".join(groups) + "," + cents


def write_catalogue() -> None:
    REFERENCE.mkdir(parents=True, exist_ok=True)
    with open(REFERENCE / "products.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sku", "product_name", "category", "list_price"])
        for sku, name, category, price in CATALOGUE:
            writer.writerow([sku, name, category, f"{price:.2f}"])


def sandton() -> None:
    """Clean-ish CSV: comma separated, ISO dates, plain numbers."""
    rows = []
    for i in range(1, 181):
        sku = rng.choice(SKUS)
        rows.append([f"SDN-{10000 + i}", random_sale_time().strftime("%Y-%m-%d %H:%M"), sku,
                     str(rng.choices([1, 2, 3], [70, 22, 8])[0]), f"{PRICE[sku]:.2f}",
                     rng.choice(["Card", "card", "CASH", "Cash", "SnapScan", "EFT"])])
    # Problems a real export has.
    rows[5][2] = rows[5][2].lower()                 # lower-case SKU: fixable
    rows[12][2] = " " + rows[12][2] + " "           # stray spaces: fixable
    rows[20][3] = "0"                               # zero quantity: reject
    rows[33][2] = "EL-9999"                         # product not in the catalogue: reject
    rows[47][1] = "2026-09-31 10:15"                # 31 September does not exist: reject
    rows[58][4] = ""                                # missing price: use the catalogue price
    rows[71][3] = "two"                             # not a number: reject
    rows.append(list(rows[90]))                     # exact duplicate row: reject the second
    rows.append(list(rows[91]))
    with open(RAW / "sandton_sales_2026-09.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["transaction_id", "date", "sku", "quantity", "unit_price", "payment_method"])
        writer.writerows(rows)


def durban() -> None:
    """Semicolon CSV with day-first dates and 'R1 199,00' amounts."""
    rows = []
    for i in range(1, 141):
        sku = rng.choice(SKUS)
        rows.append([f"DBN{5000 + i}", random_sale_time().strftime("%d/%m/%Y %H:%M"),
                     sku.replace("-", ""),                           # this system drops the dash
                     str(rng.choices([1, 2, 3, 4], [65, 25, 7, 3])[0]), za_amount(PRICE[sku]),
                     rng.choice(["Credit Card", "Debit card", "Cash", "SNAPSCAN", "Zapper"])])
    rows[8][3] = "-1"                               # negative quantity (a refund keyed wrongly): reject
    rows[19][1] = "15/13/2026 09:00"                # month 13: reject
    rows[27][4] = "R12 990,00"                      # price far above list: reject
    rows[40][2] = ""                                # missing SKU: reject
    rows[55][5] = "voucher"                         # unknown payment method: mapped to "other"
    rows.append(list(rows[60]))                     # duplicate
    with open(RAW / "durban_sales_2026-09.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Txn ID", "Sale Date", "Product Code", "Qty", "Price (ZAR)", "Payment"])
        writer.writerows(rows)


def online() -> None:
    """Nested JSON: one order with several lines."""
    orders = []
    for i in range(1, 91):
        lines = []
        for sku in rng.sample(SKUS, rng.choices([1, 2, 3], [60, 30, 10])[0]):
            lines.append({"sku": sku, "qty": rng.choices([1, 2], [80, 20])[0], "price": PRICE[sku]})
        placed = random_sale_time().strftime("%Y-%m-%dT%H:%M:%S+02:00")
        orders.append({"order_ref": f"WEB-{30000 + i}", "placed_at": placed, "lines": lines,
                       "payment": {"method": rng.choice(["card", "eft", "payfast", "snapscan"])},
                       "customer": {"id": rng.randint(1000, 1400), "province": rng.choice(
                           ["Gauteng", "Western Cape", "KwaZulu-Natal", "Eastern Cape"])}})
    orders[3]["lines"][0]["qty"] = None             # missing quantity: reject that line
    orders[10]["placed_at"] = "not a date"          # every line of this order: reject
    orders[22]["lines"][0]["sku"] = "GR-0000"       # unknown product: reject
    with open(RAW / "online_orders_2026-09.json", "w", encoding="utf-8") as f:
        json.dump({"export_date": "2026-10-01", "store": "online", "orders": orders}, f, indent=2)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    write_catalogue()
    sandton()
    durban()
    online()
    print(f"Sample data written to {RAW.relative_to(ROOT)} and {REFERENCE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
