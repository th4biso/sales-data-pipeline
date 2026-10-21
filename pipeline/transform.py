"""Transform: clean, standardise and validate raw records.

Each record either becomes a CleanSale or is rejected with a plain-English
reason. Problems that can be fixed safely are fixed (stray spaces, lower-case
SKUs, "R1 199,00" prices, a missing price filled from the catalogue). Anything
that would mean guessing is rejected, so a person can look at it.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from .config import MAX_PRICE_DEVIATION, PAYMENT_ALIASES
from .extract import RawRecord

CENT = Decimal("0.01")


class RejectedRecord(ValueError):
    """Raised when a record cannot be loaded. The message is the reject reason."""


@dataclass(frozen=True)
class Product:
    sku: str
    product_name: str
    category: str
    list_price: Decimal


@dataclass
class CleanSale:
    branch: str
    transaction_id: str
    sold_at: datetime
    sku: str
    product_name: str
    category: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    payment_method: str
    price_source: str          # "export" or "catalogue"
    source_file: str


@dataclass
class Reject:
    source_file: str
    row_number: int
    branch: str
    transaction_id: str
    reason: str
    raw: dict


@dataclass
class TransformResult:
    clean: list[CleanSale] = field(default_factory=list)
    rejects: list[Reject] = field(default_factory=list)
    fixes: Counter = field(default_factory=Counter)

    @property
    def reject_reasons(self) -> Counter:
        return Counter(r.reason for r in self.rejects)


# ---------------------------------------------------------------------------
#  Field parsers. Each one returns a clean value or raises RejectedRecord.
# ---------------------------------------------------------------------------

def parse_amount(text: str) -> Decimal:
    """'549.00', '1,234.50', 'R1 199,00', '1.234,50' and 'ZAR 79' all parse."""
    value = (text or "").strip().upper().replace("ZAR", "").replace("R", "")
    value = re.sub(r"[\s ]", "", value)
    if not value:
        raise RejectedRecord("missing price")
    if "," in value and "." in value:
        # Whichever separator comes last is the decimal point.
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        # "199,00" is a decimal comma; "1,234" is a thousands separator.
        value = value.replace(",", ".") if re.search(r",\d{1,2}$", value) else value.replace(",", "")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise RejectedRecord(f"price is not a number: {text!r}") from None
    if amount <= 0:
        raise RejectedRecord("price must be greater than zero")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_quantity(text: str) -> int:
    value = (text or "").strip()
    if not value:
        raise RejectedRecord("missing quantity")
    if not re.fullmatch(r"-?\d+(\.0+)?", value):
        raise RejectedRecord(f"quantity is not a whole number: {text!r}")
    quantity = int(float(value))
    if quantity <= 0:
        raise RejectedRecord("quantity must be at least 1")
    return quantity


def parse_datetime(text: str, formats: tuple[str, ...]) -> datetime:
    value = (text or "").strip()
    if not value:
        raise RejectedRecord("missing sale date")
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        # Keep the local (South African) wall-clock time the sale happened at.
        return parsed.replace(tzinfo=None)
    raise RejectedRecord(f"invalid sale date: {text!r}")


def normalise_sku(text: str) -> str:
    """' el-1001 ', 'EL1001' and 'el 1001' all become 'EL-1001'."""
    value = re.sub(r"[\s_]", "", (text or "")).upper()
    match = re.fullmatch(r"([A-Z]{2})-?(\d{4})", value)
    return f"{match.group(1)}-{match.group(2)}" if match else value


def normalise_payment(text: str) -> str:
    key = " ".join((text or "").lower().split())
    if not key:
        return "unknown"
    return PAYMENT_ALIASES.get(key, "other")


# ---------------------------------------------------------------------------
#  Record and batch transforms
# ---------------------------------------------------------------------------

def clean_record(record: RawRecord, catalogue: dict[str, Product], date_formats: tuple[str, ...],
                 today: date, fixes: Counter | None = None) -> CleanSale:
    fixes = fixes if fixes is not None else Counter()

    transaction_id = record.transaction_id.strip().upper()
    if not transaction_id or transaction_id.startswith("-"):
        raise RejectedRecord("missing transaction id")

    sold_at = parse_datetime(record.sold_at, date_formats)
    if sold_at.date() > today:
        raise RejectedRecord("sale date is in the future")

    if not record.sku.strip():
        raise RejectedRecord("missing SKU")
    sku = normalise_sku(record.sku)
    if sku not in catalogue:
        raise RejectedRecord(f"unknown SKU: {sku}")
    if sku != record.sku:
        fixes["SKU standardised"] += 1
    product = catalogue[sku]

    quantity = parse_quantity(record.quantity)

    if record.unit_price.strip():
        unit_price = parse_amount(record.unit_price)
        price_source = "export"
        deviation = abs(unit_price - product.list_price) / product.list_price
        if deviation > Decimal(str(MAX_PRICE_DEVIATION)):
            raise RejectedRecord(
                f"price {unit_price} is more than {MAX_PRICE_DEVIATION:.0%} away from list price {product.list_price}")
    else:
        unit_price = product.list_price
        price_source = "catalogue"
        fixes["missing price filled from catalogue"] += 1

    payment = normalise_payment(record.payment_method)
    if payment == "other":
        fixes["unrecognised payment method mapped to 'other'"] += 1

    return CleanSale(
        branch=record.branch,
        transaction_id=transaction_id,
        sold_at=sold_at,
        sku=sku,
        product_name=product.product_name,
        category=product.category,
        quantity=quantity,
        unit_price=unit_price,
        line_total=(unit_price * quantity).quantize(CENT, rounding=ROUND_HALF_UP),
        payment_method=payment,
        price_source=price_source,
        source_file=record.source_file,
    )


def transform(records, catalogue: dict[str, Product], date_formats: tuple[str, ...],
              today: date | None = None) -> TransformResult:
    """Clean a batch of records. The first occurrence of a transaction id wins;
    later copies in the same batch are rejected as duplicates."""
    today = today or date.today()
    result = TransformResult()
    seen: set[tuple[str, str]] = set()
    for record in records:
        try:
            sale = clean_record(record, catalogue, date_formats, today, result.fixes)
        except RejectedRecord as problem:
            result.rejects.append(Reject(record.source_file, record.row_number, record.branch,
                                         record.transaction_id, str(problem), record.raw))
            continue
        key = (sale.branch, sale.transaction_id)
        if key in seen:
            result.rejects.append(Reject(record.source_file, record.row_number, record.branch,
                                         record.transaction_id, "duplicate transaction id in this file",
                                         record.raw))
            continue
        seen.add(key)
        result.clean.append(sale)
    return result


def load_catalogue(path: Path) -> dict[str, Product]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {
            row["sku"].strip().upper(): Product(
                sku=row["sku"].strip().upper(),
                product_name=row["product_name"].strip(),
                category=row["category"].strip(),
                list_price=Decimal(row["list_price"]).quantize(CENT),
            )
            for row in csv.DictReader(f)
        }
