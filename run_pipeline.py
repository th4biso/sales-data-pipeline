"""Run the whole pipeline: extract -> transform -> load -> report.

    python run_pipeline.py
"""

import logging
import sys

from pipeline import config, extract, load, report, transform

log = logging.getLogger("pipeline")


def run(raw_dir=config.RAW_DIR, output_dir=config.OUTPUT_DIR):
    products = transform.load_products(config.PRODUCTS_FILE)
    files = extract.find_files(raw_dir, config.BRANCHES)
    log.info("Found %d file(s) in %s", len(files), raw_dir)

    totals = {"read": 0, "loaded": 0, "rejected": 0}
    all_rejected = []
    conn = load.connect(output_dir / "warehouse.db")
    try:
        for path, branch, settings in files:
            rows = extract.read_file(path, branch, settings)
            clean, rejected = transform.transform(rows, products, settings["date_format"])
            new = load.save_sales(conn, clean)
            log.info("%-28s read %3d  clean %3d  new %3d  rejected %2d",
                     path.name, len(rows), len(clean), new, len(rejected))
            totals["read"] += len(rows)
            totals["loaded"] += new
            totals["rejected"] += len(rejected)
            all_rejected += rejected

        load.save_rejects(output_dir / "rejects.csv", all_rejected)
        report.write_reports(conn, output_dir / "reports")
    finally:
        conn.close()

    log.info("Done: %d new sales saved, %d rows rejected (see output/rejects.csv)",
             totals["loaded"], totals["rejected"])
    return totals


def main():
    # Log to the screen and to output/pipeline.log
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(config.OUTPUT_DIR / "pipeline.log", encoding="utf-8")],
    )
    run()


if __name__ == "__main__":
    main()
