import unittest

from pipeline.transform import (clean_date, clean_payment, clean_price, clean_quantity, clean_row, clean_sku,
                                transform)

PRODUCTS = {
    "EL-1001": {"name": "Wireless Earbuds", "category": "Electronics", "price": 549.00},
    "GR-6001": {"name": "Rooibos Tea (80 bags)", "category": "Groceries", "price": 79.00},
}
SANDTON_DATES = "%Y-%m-%d %H:%M"


def make_row(**changes):
    # A valid row. Each test changes only the value it is testing.
    row ={"file": "test.csv", "row": 2, "branch": "SANDTON", "transaction_id": "SDN-1",
           "date": "2026-09-05 14:41", "sku": "EL-1001", "quantity": "2", "price": "549.00", "payment": "Card"}
    row.update(changes)
    return row


class PriceTests(unittest.TestCase):
    def test_plain_price(self):
        self.assertEqual(clean_price("199.00"), 199.00)
        self.assertEqual(clean_price(229.0), 229.00)

    def test_south_african_price(self):
        self.assertEqual(clean_price("R1 199,00"), 1199.00)

    def test_missing_price_is_rejected(self):
        with self.assertRaises(ValueError):
            clean_price("")

    def test_text_price_is_rejected(self):
        with self.assertRaises(ValueError):
            clean_price("abc")


class QuantityTests(unittest.TestCase):
    def test_valid_quantity(self):
        self.assertEqual(clean_quantity(" 3 "), 3)

    def test_zero_or_negative_is_rejected(self):
        for value in ["0", "-1"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                clean_quantity(value)

    def test_words_are_rejected(self):
        with self.assertRaises(ValueError):
            clean_quantity("two")


class DateTests(unittest.TestCase):
    def test_each_branch_format(self):
        self.assertEqual(clean_date("2026-09-05 14:41", "%Y-%m-%d %H:%M"), "2026-09-05 14:41")
        self.assertEqual(clean_date("05/09/2026 14:41", "%d/%m/%Y %H:%M"), "2026-09-05 14:41")

    def test_impossible_date_is_rejected(self):
        with self.assertRaises(ValueError):
            clean_date("2026-09-31 10:15", SANDTON_DATES)


class StandardiseTests(unittest.TestCase):
    def test_product_codes(self):
        for value in ["EL-1001", " el-1001 ", "EL1001"]:
            with self.subTest(value=value):
                self.assertEqual(clean_sku(value), "EL-1001")

    def test_payment_methods(self):
        self.assertEqual(clean_payment("Credit Card"), "card")
        self.assertEqual(clean_payment("SNAPSCAN"), "mobile")
        self.assertEqual(clean_payment("voucher"), "other")


class RowTests(unittest.TestCase):
    def test_unknown_product_is_rejected(self):
        with self.assertRaises(ValueError):
            clean_row(make_row(sku="EL-9999"), PRODUCTS, SANDTON_DATES)

    def test_price_far_from_list_price_is_rejected(self):
        with self.assertRaises(ValueError):
            clean_row(make_row(price="R12 990,00"), PRODUCTS, SANDTON_DATES)

    def test_duplicates_and_bad_rows_are_separated(self):
        rows = [make_row(), make_row(), make_row(transaction_id="SDN-2", quantity="0"),
                make_row(transaction_id="SDN-3", sku="gr6001", price="79.00")]
        clean, rejected = transform(rows, PRODUCTS, SANDTON_DATES)
        self.assertEqual([sale["transaction_id"] for sale in clean], ["SDN-1", "SDN-3"])
        self.assertEqual(sorted(r["reason"] for r in rejected),
                         ["duplicate transaction", "quantity must be at least 1"])


if __name__ == "__main__":
    unittest.main()
