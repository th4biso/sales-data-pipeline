"""Extract: find the raw export files and read them into a common shape.

Nothing is validated here. Every row comes out as a RawRecord with the
original text values, so that the transform step can say exactly which
value was wrong.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .config import Source

log = logging.getLogger(__name__)


@dataclass
class RawRecord:
    source_file: str
    row_number: int
    branch: str
    transaction_id: str
    sold_at: str
    sku: str
    quantity: str
    unit_price: str
    payment_method: str
    raw: dict


def discover_files(raw_dir: Path, sources: list[Source]) -> list[tuple[Path, Source]]:
    """Every file in raw_dir that matches a known source, oldest name first."""
    found = []
    for source in sources:
        for path in sorted(raw_dir.glob(source.pattern)):
            found.append((path, source))
    known = {path for path, _ in found}
    for path in sorted(raw_dir.iterdir()):
        if path.is_file() and path not in known and not path.name.startswith("."):
            log.warning("Skipping %s: it does not match any configured source", path.name)
    return found


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_file(path: Path, source: Source) -> Iterator[RawRecord]:
    if source.format == "csv":
        yield from _read_csv(path, source)
    elif source.format == "json_orders":
        yield from _read_json_orders(path, source)
    else:
        raise ValueError(f"Unknown source format: {source.format}")


def _text(value) -> str:
    return "" if value is None else str(value)


def _read_csv(path: Path, source: Source) -> Iterator[RawRecord]:
    # utf-8-sig strips the byte-order mark Excel adds to CSVs it saves.
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=source.delimiter)
        missing = [col for col in source.columns.values() if col not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name} is missing expected columns: {', '.join(missing)}")
        cols = source.columns
        # Row 1 is the header, so data starts on line 2 of the file.
        for line_no, row in enumerate(reader, start=2):
            yield RawRecord(
                source_file=path.name,
                row_number=line_no,
                branch=source.branch,
                transaction_id=_text(row.get(cols["transaction_id"])),
                sold_at=_text(row.get(cols["sold_at"])),
                sku=_text(row.get(cols["sku"])),
                quantity=_text(row.get(cols["quantity"])),
                unit_price=_text(row.get(cols["unit_price"])),
                payment_method=_text(row.get(cols["payment_method"])),
                raw=dict(row),
            )


def _read_json_orders(path: Path, source: Source) -> Iterator[RawRecord]:
    """Flatten {"orders": [{..., "lines": [...]}]} into one record per order line."""
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    orders = payload.get("orders")
    if not isinstance(orders, list):
        raise ValueError(f"{path.name} has no 'orders' list")
    for order_no, order in enumerate(orders, start=1):
        lines = order.get("lines") or []
        for line_no, line in enumerate(lines, start=1):
            yield RawRecord(
                source_file=path.name,
                row_number=order_no,
                branch=source.branch,
                # One order has several lines, so each line gets its own id.
                transaction_id=f"{_text(order.get('order_ref'))}-{line_no}",
                sold_at=_text(order.get("placed_at")),
                sku=_text(line.get("sku")),
                quantity=_text(line.get("qty")),
                unit_price=_text(line.get("price")),
                payment_method=_text((order.get("payment") or {}).get("method")),
                raw={"order_ref": order.get("order_ref"), "line": line_no, **line},
            )
