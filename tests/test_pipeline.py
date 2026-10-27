"""End-to-end tests: run the whole pipeline on a copy of the sample data in a temporary folder."""

import csv
import logging
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import run_pipeline
from pipeline import config


class PipelineTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        shutil.copytree(config.RAW_DIR, self.raw)
        self.output = self.tmp / "output"

    def tearDown(self):
        logging.disable(logging.NOTSET)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_pipeline(self):
        return run_pipeline.run(self.raw, self.output)

    def sales_in_database(self):
        conn = sqlite3.connect(self.output / "warehouse.db")
        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        conn.close()
        return count

    def test_good_rows_are_loaded_and_bad_rows_rejected(self):
        totals = self.run_pipeline()
        self.assertEqual(totals["read"], totals["loaded"] + totals["rejected"])
        self.assertGreater(totals["rejected"], 0)
        self.assertEqual(self.sales_in_database(), totals["loaded"])

    def test_every_rejected_row_has_a_reason(self):
        totals = self.run_pipeline()
        with open(self.output / "rejects.csv", encoding="utf-8") as f:
            rejects = list(csv.DictReader(f))
        self.assertEqual(len(rejects), totals["rejected"])
        self.assertTrue(all(row["reason"] for row in rejects))

    def test_reports_are_created(self):
        self.run_pipeline()
        for name in ["branch_summary.csv", "daily_sales.csv", "top_products.csv", "payment_methods.csv"]:
            with self.subTest(report=name):
                self.assertTrue((self.output / "reports" / name).exists())

    def test_running_twice_adds_no_duplicates(self):
        first = self.run_pipeline()
        second = self.run_pipeline()
        self.assertEqual(second["loaded"], 0)
        self.assertEqual(self.sales_in_database(), first["loaded"])

    def test_a_new_sale_is_picked_up_on_the_next_run(self):
        self.run_pipeline()
        sandton = next(self.raw.glob("sandton_*.csv"))
        with open(sandton, "a", encoding="utf-8", newline="") as f:
            f.write("SDN-99999,2026-09-30 12:00,GR-6001,1,79.00,Cash\n")
        self.assertEqual(self.run_pipeline()["loaded"], 1)


if __name__ == "__main__":
    unittest.main()
