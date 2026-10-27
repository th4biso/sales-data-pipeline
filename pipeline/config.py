from pathlib import Path

RAW_DIR = Path("data/raw")
PRODUCTS_FILE = Path("data/reference/products.csv")
OUTPUT_DIR = Path("output")

# Each branch sends the same information in a different format.
BRANCHES = {
    "SANDTON": {
        "file": "sandton_sales_*.csv",
        "type": "csv",
        "delimiter": ",",
        "date_format": "%Y-%m-%d %H:%M",          # 2026-09-12 17:03
        "columns": {"transaction_id": "transaction_id", "date": "date", "sku": "sku",
                    "quantity": "quantity", "price": "unit_price", "payment": "payment_method"},
    },
    "DURBAN": {
        "file": "durban_sales_*.csv",
        "type": "csv",
        "delimiter": ";",
        "date_format": "%d/%m/%Y %H:%M",          # 14/09/2026 18:03
        "columns": {"transaction_id": "Txn ID", "date": "Sale Date", "sku": "Product Code",
                    "quantity": "Qty", "price": "Price (ZAR)", "payment": "Payment"},
    },
    "ONLINE": {
        "file": "online_orders_*.json",
        "type": "json",
        "date_format": "%Y-%m-%dT%H:%M:%S%z",     # 2026-09-08T10:21:00+02:00
    },
}

# Every way the branches write a payment method must use one standard name in the final output.
PAYMENT_METHODS = {
    "card": "card", "credit card": "card", "debit card": "card", "visa": "card", "mastercard": "card",
    "cash": "cash",
    "eft": "eft", "bank transfer": "eft",
    "snapscan": "mobile", "zapper": "mobile", "payfast": "mobile",
}
