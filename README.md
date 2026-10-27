# Automated Sales Data Pipeline

![tests](https://github.com/th4biso/sales-data-pipeline/actions/workflows/tests.yml/badge.svg)

A Python ETL pipeline that collects sales exports from three branches of a retailer, cleans and standardises them, and loads them into a SQLite database. GitHub Actions runs the tests and the pipeline automatically on every push.

**Tech:** Python · SQLite · GitHub Actions · `unittest` (standard library only, nothing to install)

## The problem

Each branch exports the same sales information in a different format:

| Branch | Format | Example |
|---|---|---|
| Sandton | Comma CSV, dates like `2026-09-12 17:03` | `SDN-10002,2026-09-12 17:03,EL-1002,2,199.00,card` |
| Durban | **Semicolon** CSV, day-first dates, prices like `R1 199,00`, product codes without a dash | `DBN5002;14/09/2026 18:03;BP3004;3;R1 199,00;Debit card` |
| Online | **JSON**, one order with several products | `{"order_ref": "WEB-30001", "lines": [...]}` |

The files also contain mistakes: impossible dates, unknown products, quantities of `0`, `-1` or `two`, missing values, a wrongly typed price and duplicate rows.

## How it works

```
data/raw  ->  Extract  ->  Transform  ->  Load (SQLite)  ->  Reports
                              |
                              +-> rejected rows + reason -> output/rejects.csv
```

| Step | File | What it does |
|---|---|---|
| Settings | `pipeline/config.py` | Each branch's file name, separator, date format and column names |
| Extract | `pipeline/extract.py` | Finds the files and reads every row into the same shape |
| Transform | `pipeline/transform.py` | Cleans and checks every row; bad rows are rejected with a reason |
| Load | `pipeline/load.py` | Saves clean sales to SQLite and rejected rows to a CSV |
| Report | `pipeline/report.py` | SQL reports: revenue by branch, daily sales, top products, payment methods |
| Run | `run_pipeline.py` | Runs all the steps in order and logs what happened |

### Cleaning rules

| Problem | What happens |
|---|---|
| `el-1001`, ` EL-1001 `, `EL1001` | Standardised to `EL-1001` |
| `R1 199,00` | Standardised to `1199.00` |
| Different date formats | Standardised to `2026-09-14 18:03` |
| `Credit Card`, `SNAPSCAN`, `voucher` | Standardised to `card`, `mobile`, `other` |
| Impossible date, unknown or missing product | Rejected |
| Quantity `0`, `-1`, `two` or missing | Rejected |
| Missing price, or a price far from the list price | Rejected |
| The same transaction twice in a file | The copy is rejected |

### Safe to re-run

Every sale has a unique key (branch + transaction ID), and new sales are saved with `INSERT OR IGNORE`. Running the pipeline again never creates duplicates: it only adds sales that are new.

## Running it

```bash
python run_pipeline.py                            # run the pipeline
python -m unittest discover -s tests -t . -v      # run the 19 tests
python scripts/make_sample_data.py                # recreate the sample data
```

Output:

```
output/
  warehouse.db          SQLite database (table: sales)
  rejects.csv           every rejected row with the reason
  reports/              branch_summary, daily_sales, top_products, payment_methods (CSV)
  pipeline.log          log of every run
```

## Example run

```
Found 3 file(s) in data\raw
sandton_sales_2026-09.csv    read 182  clean 175  new 175  rejected  7
durban_sales_2026-09.csv     read 141  clean 136  new 136  rejected  5
online_orders_2026-09.json   read 131  clean 127  new 127  rejected  4
Done: 438 new sales saved, 16 rows rejected (see output/rejects.csv)
```

Running it again straight away saves `0` new sales, because they are already in the database.

## Tests and CI

19 tests with Python's `unittest`, run by GitHub Actions on every push and pull request (`.github/workflows/tests.yml`):

- **14 unit tests** for the cleaning rules: prices, quantities, dates, product codes, payment methods, rejects and duplicates.
- **5 end-to-end tests** that run the whole pipeline in a temporary folder: good rows are loaded, every reject has a reason, the reports are created, a second run adds no duplicates, and a new sale is picked up.

## Next steps

- Schedule it to run daily (a scheduled GitHub Actions workflow or cron).
- Package it in Docker.
- Load into PostgreSQL instead of SQLite.
