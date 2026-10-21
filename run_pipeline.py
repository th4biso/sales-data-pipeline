"""Run the sales data pipeline.

    python run_pipeline.py                 # process every new file in data/raw
    python run_pipeline.py --dry-run       # clean and report, but write nothing to the warehouse
    python run_pipeline.py --force         # reprocess files even if they were loaded before
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pipeline import config, extract, load, report, transform

log = logging.getLogger("pipeline")


def setup_logging(log_dir: Path, verbose: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    to_file = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [console, to_file]
    root.setLevel(logging.DEBUG)


def run(raw_dir: Path, output_dir: Path, db_path: Path, force: bool = False, dry_run: bool = False) -> dict:
    # Timestamp for readability, plus a short random part so two runs in the same second differ.
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    catalogue = transform.load_catalogue(config.CATALOGUE_FILE)
    files = extract.discover_files(raw_dir, config.SOURCES)
    log.info("Run %s: %d file(s) found in %s", run_id, len(files), raw_dir)

    stats = {"run_id": run_id, "files_processed": 0, "files_skipped": 0, "rows_read": 0, "rows_loaded": 0,
             "rows_rejected": 0, "rows_already_loaded": 0, "reject_reasons": Counter(), "fixes": Counter()}
    all_clean, all_rejects = [], []

    conn = load.connect(db_path)
    try:
        if not dry_run:
            load.start_run(conn, run_id)
            load.upsert_products(conn, catalogue)
            conn.commit()

        for path, source in files:
            digest = extract.file_sha256(path)
            if not force and load.already_ingested(conn, digest):
                log.info("Skipping %s: already loaded (same contents)", path.name)
                stats["files_skipped"] += 1
                continue
            try:
                records = list(extract.read_file(path, source))
            except (ValueError, OSError) as problem:
                log.error("Could not read %s: %s", path.name, problem)
                continue

            result = transform.transform(records, catalogue, source.date_formats)
            loaded = 0
            if not dry_run:
                # One transaction per file: a file is either fully loaded or not at all.
                with conn:
                    loaded = load.insert_sales(conn, result.clean, run_id)
                    load.record_file(conn, digest, path.name, len(records), loaded, len(result.rejects), run_id)

            stats["files_processed"] += 1
            stats["rows_read"] += len(records)
            stats["rows_loaded"] += loaded
            stats["rows_rejected"] += len(result.rejects)
            stats["rows_already_loaded"] += 0 if dry_run else len(result.clean) - loaded
            stats["reject_reasons"].update(result.reject_reasons)
            stats["fixes"].update(result.fixes)
            all_clean += result.clean
            all_rejects += result.rejects
            log.info("%-32s read %4d  clean %4d  loaded %4d  rejected %3d",
                     path.name, len(records), len(result.clean), loaded, len(result.rejects))
            for reject in result.rejects:
                log.debug("  rejected %s row %s: %s", reject.source_file, reject.row_number, reject.reason)

        if all_clean:
            load.write_clean_csv(output_dir / "clean" / f"clean_{run_id}.csv", all_clean)
        if all_rejects:
            load.write_rejects_csv(output_dir / "rejects" / f"rejects_{run_id}.csv", all_rejects)

        if dry_run:
            log.info("Dry run: nothing was written to the warehouse")
        else:
            load.finish_run(conn, run_id, stats, "success")
            summary = report.build_reports(conn, output_dir / "reports", stats)
            log.info("Reports written to %s", summary.parent)
    except Exception:
        if not dry_run:
            load.finish_run(conn, run_id, stats, "failed")
        raise
    finally:
        conn.close()

    log.info("Done: %d loaded, %d rejected, %d skipped file(s)",
             stats["rows_loaded"], stats["rows_rejected"], stats["files_skipped"])
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract, clean and load branch sales exports.")
    parser.add_argument("--raw-dir", type=Path, default=config.RAW_DIR, help="folder with the raw exports")
    parser.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR, help="where outputs are written")
    parser.add_argument("--db", type=Path, default=None, help="warehouse file (default: <output-dir>/warehouse.db)")
    parser.add_argument("--force", action="store_true", help="reprocess files that were already loaded")
    parser.add_argument("--dry-run", action="store_true", help="clean and report without loading")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every rejected row")
    args = parser.parse_args(argv)

    setup_logging(args.output_dir / "logs", args.verbose)
    run(args.raw_dir, args.output_dir, args.db or args.output_dir / "warehouse.db", args.force, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
