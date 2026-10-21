import unittest
from datetime import date, datetime
from decimal import Decimal

from pipeline.extract import RawRecord
from pipeline.transform import (Product, RejectedRecord, clean_record, normalise_payment, normalise_sku,
                                parse_amount, parse_datetime, parse_quantity, transform)

CATALOGUE = {
    "EL-1001": Product("EL-1001", "Wireless Earbuds", "Electronics", Decimal("549.00")),
    "GR-6001": Product("GR-6001", "Rooibos Tea (80 bags)", "Groceries", Decimal("79.00")),
}
FORMATS = ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M")
TODAY = date(2026, 10, 1)


def record(**overrides) -> RawRecord:
    values = dict(source_file="test.csv", row_number=2, branch="SANDTON", transaction_id="SDN-1",
                  sold_at="2026-09-05 14:41", sku="EL-1001", quantity="2", unit_price="549.00",
                  payment_method="Card", raw={})
    values.update(overrides)
    return RawRecord(**values)


class ParseAmountTests(unittest.TestCase):
    def test_formats(self):
        cases = {"549.00": "549.00", "549": "549.00", "1,234.50": "1234.50", "R1 199,00": "1199.00",
                 "1.234,50": "1234.50", "199,5": "199.50", "ZAR 79": "79.00", "1,234": "1234.00",
                 "R 249,99": "249.99"}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_amount(text), Decimal(expected))

    def test_rejects_bad_values(self):
        for text in ["", "   ", "abc", "0", "-5.00"]:
            with self.subTest(text=text), self.assertRaises(RejectedRecord):
                parse_amount(text)


class ParseQuantityTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_quantity(" 3 "), 3)
        self.assertEqual(parse_quantity("2.0"), 2)

    def test_invalid(self):
        for text in ["", "0", "-1", "two", "1.5"]:
            with self.subTest(text=text), self.assertRaises(RejectedRecord):
                parse_quantity(text)


class ParseDatetimeTests(unittest.TestCase):
    def test_tries_each_format(self):
        self.assertEqual(parse_datetime("2026-09-05 14:41", FORMATS), datetime(2026, 9, 5, 14, 41))
        self.assertEqual(parse_datetime("05/09/2026 14:41", FORMATS), datetime(2026, 9, 5, 14, 41))

    def test_keeps_local_time_from_offset(self):
        parsed = parse_datetime("2026-09-05T14:41:00+02:00", ("%Y-%m-%dT%H:%M:%S%z",))
        self.assertEqual(parsed, datetime(2026, 9, 5, 14, 41))

    def test_impossible_dates_are_rejected(self):
        for text in ["2026-09-31 10:15", "15/13/2026 09:00", "not a date", ""]:
            with self.subTest(text=text), self.assertRaises(RejectedRecord):
                parse_datetime(text, FORMATS)


class NormaliseTests(unittest.TestCase):
    def test_sku(self):
        for text in ["EL-1001", " el-1001 ", "EL1001", "el 1001", "EL_1001"]:
            with self.subTest(text=text):
                self.assertEqual(normalise_sku(text), "EL-1001")

    def test_payment(self):
        self.assertEqual(normalise_payment("Credit Card"), "card")
        self.assertEqual(normalise_payment("  SNAPSCAN "), "mobile")
        self.assertEqual(normalise_payment("voucher"), "other")
        self.assertEqual(normalise_payment(""), "unknown")


class CleanRecordTests(unittest.TestCase):
    def test_clean_record(self):
        sale = clean_record(record(), CATALOGUE, FORMATS, TODAY)
        self.assertEqual(sale.sku, "EL-1001")
        self.assertEqual(sale.line_total, Decimal("1098.00"))
        self.assertEqual(sale.payment_method, "card")
        self.assertEqual(sale.price_source, "export")

    def test_missing_price_uses_catalogue(self):
        sale = clean_record(record(unit_price=""), CATALOGUE, FORMATS, TODAY)
        self.assertEqual(sale.unit_price, Decimal("549.00"))
        self.assertEqual(sale.price_source, "catalogue")

    def test_rejections(self):
        cases = {
            "unknown SKU": record(sku="EL-9999"),
            "missing SKU": record(sku=""),
            "more than 50%": record(unit_price="R12 990,00"),
            "in the future": record(sold_at="2026-12-01 10:00"),
            "missing transaction id": record(transaction_id=""),
        }
        for expected, rec in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(RejectedRecord) as ctx:
                    clean_record(rec, CATALOGUE, FORMATS, TODAY)
                self.assertIn(expected, str(ctx.exception))


class TransformBatchTests(unittest.TestCase):
    def test_duplicates_and_rejects_are_separated(self):
        batch = [record(), record(), record(transaction_id="SDN-2", quantity="0"),
                 record(transaction_id="SDN-3", sku="gr6001", unit_price="79.00")]
        result = transform(batch, CATALOGUE, FORMATS, TODAY)
        self.assertEqual([s.transaction_id for s in result.clean], ["SDN-1", "SDN-3"])
        self.assertEqual(sorted(r.reason for r in result.rejects),
                         ["duplicate transaction id in this file", "quantity must be at least 1"])
        self.assertEqual(result.fixes["SKU standardised"], 1)

    def test_same_id_in_different_branches_is_not_a_duplicate(self):
        batch = [record(), record(branch="DURBAN")]
        self.assertEqual(len(transform(batch, CATALOGUE, FORMATS, TODAY).clean), 2)


if __name__ == "__main__":
    unittest.main()
