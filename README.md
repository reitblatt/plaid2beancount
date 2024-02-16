# Plaid to Beancount Converter

This is a simple Python application that downloads transactions from Plaid, stores them in a SQLite database using Peewee ORM, and outputs them in Beancount format.

## Requirements

- Python 3.6 or higher
- Plaid API credentials
- SQLite
- Peewee ORM
- Beancount

## Installation

1. Clone this repository.
2. Install the required Python packages using pip:

```bash
pip install plaid-python sqlite3 peewee beancount
```

## Usage
Set your Plaid API credentials in the script:
PLAID_CLIENT_ID = 'your_plaid_client_id'
PLAID_SECRET = 'your_plaid_secret'
PLAID_PUBLIC_KEY = 'your_plaid_public_key'
PLAID_ENV = 'sandbox'  # or 'development' or 'production'

Because I started this project as a migration for plaid2text, 
Configure account matching in your beancount file.

### Run the script:
`python main.py`

By default, the script will download transactions from the Plaid API, store them in a SQLite database, and print them in Beancount format.

### Options
The script accepts the following command-line arguments:

* --sync-all-transactions: Download all transactions from the Plaid API and store them in the SQLite database.
* --output-transactions: Print all transactions in Beancount format.
* --from-date: Only include transactions from this date onwards.
* --to-date: Only include transactions up to this date.
* --root-file: Beancount root file, used to lookup metadata for account matching

## License
This project is licensed under the MIT License.

```

Please replace 'your_plaid_client_id', 'your_plaid_secret', and 'your_plaid_public_key' with your actual Plaid API credentials. Also, adjust the PLAID_ENV as per your environment.