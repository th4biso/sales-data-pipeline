"""End-to-end tests: run the whole pipeline against the sample data in a temp folder."""

import logging
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import run_pipeline
from pipeline import config


class PipelineEndToEndTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        shutil.copytree(config.RAW_DIR, self.raw)
        self.out = self.tmp / "output"
        self.db = self.out / "warehouse.db"

    def tearDown(self):
        logging.disable(logging.NOTSET)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_pipeline(self, **kwargs):
        return run_pipeline.run(self.raw, self.out, self.db, **kwargs)

    def count(self, sql):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql).fetchone()[0]

    def test_first_run_loads_clean_rows_and_rejects_bad_ones(self):
        stats = self.run_pipeline()
        self.assertEqual(stats["files_processed"], 3)
        self.assertEqual(stats["rows_read"], stats["rows_loaded"] + stats["rows_rejected"])
        self.assertGreater(stats["rows_rejected"], 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM fact_sales"), stats["rows_loaded"])
        self.assertEqual(len(list((self.out / "rejects").glob("rejects_*.csv"))), 1)
        self.assertTrue((self.out / "reports" / "daily_sales.csv").exists())

    def test_rerun_skips_files_already_loaded(self):
        first = self.run_pipeline()
        second = self.run_pipeline()
        self.assertEqual(second["files_skipped"], 3)
        self.assertEqual(second["rows_loaded"], 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM fact_sales"), first["rows_loaded"])

    def test_forced_rerun_never_duplicates_sales(self):
        first = self.run_pipeline()
        forced = self.run_pipeline(force=True)
        self.assertEqual(forced["rows_loaded"], 0)
        self.assertEqual(forced["rows_already_loaded"], first["rows_loaded"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM fact_sales"), first["rows_loaded"])

    def test_dry_run_writes_nothing_to_the_warehouse(self):
        self.run_pipeline(dry_run=True)
        self.assertEqual(self.count("SELECT COUNT(*) FROM fact_sales"), 0)
        self.assertEqual(self.count("SELECT COUNT(*) FROM ingested_files"), 0)

    def test_a_changed_file_is_picked_up_again(self):
        self.run_pipeline()
        sandton = next(self.raw.glob("sandton_*.csv"))
        with open(sandton, "a", encoding="utf-8", newline="") as f:
            f.write("SDN-99999,2026-09-30 12:00,GR-6001,1,79.00,Cash\n")
        stats = self.run_pipeline()
        self.assertEqual(stats["files_processed"], 1)
        self.assertEqual(stats["rows_loaded"], 1)


if __name__ == "__main__":
    unittest.main()
