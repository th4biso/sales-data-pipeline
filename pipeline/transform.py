"""Transform: clean and check every row.

Good rows are standardised (product codes, prices, dates, payment methods).
Bad rows are rejected with a plain-English reason, so someone can fix them.
"""

import csv
from datetime import datetime

from .config import PAYMENT_METHODS


def load_products(path):
    """Read the product list into {sku: {"name", "category", "price"}}."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["sku"]: {"name": row["product_name"], "category": row["category"],
                             "price": float(row["list_price"])}
                for row in csv.DictReader(f)}


def text(value):
    """Turn any value (text, number or missing) into trimmed text."""
    return "" if value is None else str(value).strip()


# Each clean_... function returns a clean value, or raises ValueError with the reason.

def clean_price(value):
    """'199.00', 'R1 199,00' and 229.0 all become a number."""
    price = text(value).upper().replace("R", "").replace(" ", "").replace(",", ".")
    if not price:
        raise ValueError("missing price")
    try:
        return round(float(price), 2)
    except ValueError:
        raise ValueError(f"price is not a number: {value}")


def clean_quantity(value):
    if not text(value):
        raise ValueError("missing quantity")
    try:
        quantity = int(text(value))
    except ValueError:
        raise ValueError(f"quantity is not a whole number: {value}")
    if quantity < 1:
        raise ValueError("quantity must be at least 1")
    return quantity


def clean_date(value, date_format):
    """Read the date in the branch's own format and return it as 2026-09-14 18:03."""
    try:
        return datetime.strptime(text(value), date_format).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(f"invalid date: {value}")


def clean_sku(value):
    """'el-1001', ' EL-1001 ' and 'EL1001' all become 'EL-1001'."""
    sku = text(value).upper().replace(" ", "")
    if len(sku) == 6 and "-" not in sku:
        sku = sku[:2] + "-" + sku[2:]
    return sku


def clean_payment(value):
    """'Credit Card' -> 'card', 'SNAPSCAN' -> 'mobile'. Anything unknown -> 'other'."""
    return PAYMENT_METHODS.get(text(value).lower(), "other")


def clean_row(row, products, date_format):
    """Check one row. Returns the clean sale, or raises ValueError with the reason."""
    transaction_id = text(row["transaction_id"]).upper()
    if not transaction_id:
        raise ValueError("missing transaction id")

    sold_at = clean_date(row["date"], date_format)

    sku = clean_sku(row["sku"])
    if not sku:
        raise ValueError("missing product code")
    if sku not in products:
        raise ValueError(f"unknown product: {sku}")
    product = products[sku]

    quantity = clean_quantity(row["quantity"])
    price = clean_price(row["price"])
    # A price far from the catalogue price is probably a typing mistake.
    if price > product["price"] * 2 or price < product["price"] / 2:
        raise ValueError(f"price {price} is far from the list price {product['price']}")

    return {
        "branch": row["branch"],
        "transaction_id": transaction_id,
        "sold_at": sold_at,
        "sku": sku,
        "product_name": product["name"],
        "category": product["category"],
        "quantity": quantity,
        "unit_price": price,
        "line_total": round(price * quantity, 2),
        "payment_method": clean_payment(row["payment"]),
        "source_file": row["file"],
    }


def transform(rows, products, date_format):
    """Clean every row of one file. Returns (clean sales, rejected rows)."""
    clean, rejected = [], []
    seen = set()
    for row in rows:
        try:
            sale = clean_row(row, products, date_format)
        except ValueError as problem:
            rejected.append({**row, "reason": str(problem)})
            continue
        # The same transaction twice in one file: keep the first, reject the copy.
        if sale["transaction_id"] in seen:
            rejected.append({**row, "reason": "duplicate transaction"})
            continue
        seen.add(sale["transaction_id"])
        clean.append(sale)
    return clean, rejected
