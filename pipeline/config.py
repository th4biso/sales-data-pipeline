"""Where things are, and how each branch's export is laid out.

Adding a new branch means adding one entry to SOURCES, not writing new code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CATALOGUE_FILE = PROJECT_ROOT / "data" / "reference" / "products.csv"
OUTPUT_DIR = PROJECT_ROOT / "output"

# A price more than this far from the catalogue price is treated as a keying error.
MAX_PRICE_DEVIATION = 0.5

PAYMENT_ALIASES = {
    "card": "card", "credit card": "card", "debit card": "card", "visa": "card", "mastercard": "card",
    "cash": "cash",
    "eft": "eft", "bank transfer": "eft",
    "snapscan": "mobile", "zapper": "mobile", "payfast": "mobile",
}


@dataclass(frozen=True)
class Source:
    """One branch's export format."""
    name: str
    branch: str
    pattern: str                      # file name glob inside the raw folder
    format: str                       # "csv" or "json_orders"
    delimiter: str = ","
    date_formats: tuple[str, ...] = ()
    columns: dict[str, str] = field(default_factory=dict)   # our field -> their column


SOURCES = [
    Source(
        name="Sandton store POS",
        branch="SANDTON",
        pattern="sandton_sales_*.csv",
        format="csv",
        delimiter=",",
        date_formats=("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"),
        columns={"transaction_id": "transaction_id", "sold_at": "date", "sku": "sku",
                 "quantity": "quantity", "unit_price": "unit_price", "payment_method": "payment_method"},
    ),
    Source(
        name="Durban store POS",
        branch="DURBAN",
        pattern="durban_sales_*.csv",
        format="csv",
        delimiter=";",
        date_formats=("%d/%m/%Y %H:%M", "%d/%m/%Y"),
        columns={"transaction_id": "Txn ID", "sold_at": "Sale Date", "sku": "Product Code",
                 "quantity": "Qty", "unit_price": "Price (ZAR)", "payment_method": "Payment"},
    ),
    Source(
        name="Online store",
        branch="ONLINE",
        pattern="online_orders_*.json",
        format="json_orders",
        date_formats=("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"),
    ),
]
