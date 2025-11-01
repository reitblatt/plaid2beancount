# Plaid to Beancount Converter

A Python CLI tool that syncs financial transactions from the Plaid API to Beancount format. Downloads transactions from connected bank accounts and investment accounts, and outputs them as properly formatted Beancount entries with automatic expense categorization.

## Features

- **Incremental Sync**: Uses Plaid's cursor-based sync to efficiently fetch only new transactions
- **Investment Support**: Handles investment transactions (buy, sell, dividends, sweeps, transfers)
- **Smart Categorization**: Maps transactions to expense accounts using:
  - Plaid's personal finance categories
  - Custom payee-based rules
- **Multi-Account**: Organizes transactions into separate files per account
- **Recategorization**: Re-categorize existing transactions when rules change
- **Permission Management**: Web-based interface to update Plaid connection permissions

## Requirements

- Python 3.10 or higher
- Plaid API credentials (client_id and secret)
- Beancount 2.3.0+

## Installation

1. Clone this repository:

```bash
git clone <repository-url>
cd plaid2beancount
```

2. Create and activate a virtual environment:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a configuration file at `~/.config/plaid2text/config`:

```ini
[PLAID]
client_id = your_plaid_client_id
secret = your_plaid_secret
```

## Setup

### 1. Configure Your Beancount Root File

Your root beancount file must include account metadata for Plaid integration:

```beancount
2020-01-01 open Assets:Bank:Checking
  plaid_account_id: "abc123"
  plaid_item_id: "item_xyz"
  plaid_access_token: "access-production-..."
  transaction_file: "accounts/Bank/Checking.beancount"
  short_name: "Chase Checking"

2020-01-01 open Expenses:Groceries
  plaid_category: "FOOD_AND_DRINK_GROCERIES"
  payees: "whole foods, trader joes, safeway"
```

**Required metadata per account:**
- `plaid_account_id`: Plaid's account identifier
- `plaid_item_id`: Plaid's item (institution) identifier
- `plaid_access_token`: Access token from Plaid Link
- `transaction_file`: Relative path where transactions should be written
- `short_name`: Human-readable account name

**Expense categorization (optional):**
- `plaid_category`: Maps Plaid's category to this expense account
- `payees`: Comma-separated list of merchant names (payee rules override category rules)

### 2. Include the Cursors File

Add this to your root beancount file:

```beancount
include "plaid_cursors.beancount"
```

The tool automatically manages sync cursors in this file to enable incremental updates.

## Usage

**Note:** Make sure to activate your virtual environment before running any commands:
```bash
source venv/bin/activate  # macOS/Linux
```

### Sync Transactions

Download new transactions from Plaid and write them to your beancount files:

```bash
python main.py --sync-transactions --root-file path/to/root.beancount
```

This will:
1. Fetch new transactions using saved cursors (incremental sync)
2. Categorize transactions based on your rules
3. Write transactions to individual account files
4. Update cursors for next sync

### Recategorize Existing Transactions

Update expense categories for existing transactions when your rules change:

```bash
python main.py --recategorize --root-file path/to/root.beancount
```

Optional date filters:

```bash
python main.py --recategorize \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --root-file path/to/root.beancount
```

### Update Plaid Permissions

If Plaid connections expire (ITEM_LOGIN_REQUIRED error), reauthorize via web interface:

```bash
python main.py --update-permissions --root-file path/to/root.beancount
```

This opens a browser where you can select the expired item and re-authenticate with your bank.

### Show Account Information

View account details from Plaid:

```bash
python main.py --show-accounts --root-file path/to/root.beancount
```

Displays account numbers, types, balances, and institution information.

## Command-Line Options

```
--sync-transactions, -s       Sync transactions and generate beancount entries
--recategorize, -r            Re-categorize existing transactions based on current rules
--update-permissions, -u      Update Plaid item permissions via web interface
--show-accounts, -a           Show Plaid account information for a selected item
--start-date YYYY-MM-DD       Start date for recategorization
--end-date YYYY-MM-DD         End date for recategorization
--config-file PATH            Path to config file (default: ~/.config/plaid2text/config)
--root-file PATH              Path to root beancount file (required)
--debug                       Debug mode: fetch only first batch of transactions
```

## File Structure

```
root.beancount              # Root file with account definitions
plaid_cursors.beancount     # Auto-generated cursor tracking
accounts/
  Bank/
    Checking.beancount      # Individual account transactions
    Savings.beancount
  CreditCard/
    Chase.beancount
  Investments/
    Brokerage.beancount
```

## How It Works

### Transaction Sync Flow

1. **Load Configuration**: Reads Plaid credentials and beancount metadata
2. **Fetch Accounts**: Gets account info from Plaid to validate connections
3. **Incremental Sync**: Uses cursors to fetch only new transactions since last sync
4. **Categorization**: Applies payee rules (priority) or category mappings
5. **Render**: Converts Plaid transactions to Beancount format
6. **Write**: Appends new transactions to account files (deduplicates by transaction ID)
7. **Update Cursors**: Saves new cursors for next sync

### Expense Categorization

Transactions are categorized using two methods (in priority order):

1. **Payee-based rules**: Exact or partial match on merchant/payee name (case-insensitive)
2. **Category-based rules**: Maps Plaid's `personal_finance_category.detailed` field

Example:
```beancount
; Payee rule (highest priority)
2020-01-01 open Expenses:Coffee
  payees: "starbucks, peet's coffee"

; Category rule (fallback)
2020-01-01 open Expenses:Groceries
  plaid_category: "FOOD_AND_DRINK_GROCERIES"
```

### Investment Transactions

The tool handles complex investment transaction types:

- **Buy**: Cash → Security (with cost basis)
- **Sell**: Security → Cash (with capital gains posting)
- **Dividend**: Income:Dividends → Cash
- **Sweep In/Out**: Movement between cash and money market funds
- **Transfer**: External transfers

Investment accounts use sub-accounts:
- `Assets:Investments:Brokerage:Cash`
- `Assets:Investments:Brokerage:VTSAX`
- `Assets:Investments:Brokerage:AAPL`

## Troubleshooting

### Rate Limiting

If you see `TRANSACTIONS_SYNC_LIMIT` errors:
- Wait a few minutes before retrying
- The tool now properly saves cursors to avoid redundant API calls
- Use `--debug` flag to limit fetches during testing

### ITEM_LOGIN_REQUIRED

Your Plaid connection expired. Run:
```bash
python main.py --update-permissions --root-file path/to/root.beancount
```

### Duplicate Transactions

The tool automatically deduplicates using `plaid_transaction_id` metadata. If you see duplicates:
1. Check that transaction files include the metadata line
2. Verify cursors are being saved in `plaid_cursors.beancount`

### Missing Expense Accounts

Transactions without matching categorization rules go to `Expenses:Unknown`. Add rules to your root beancount file:

```beancount
2020-01-01 open Expenses:Unknown
```

## Development

### Virtual Environment

Always activate the virtual environment before running commands:

```bash
# Activate
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Deactivate when done
deactivate
```

### Running Tests

```bash
pytest
pytest tests/test_import.py
pytest tests/test_recategorize.py
```

### Debug Mode

Enable debug logging:

```bash
python main.py --sync-transactions --root-file path/to/root.beancount --debug
```

This:
- Enables verbose logging
- Fetches only the first batch of transactions (avoids hitting rate limits during testing)

### Installing Development Dependencies

If you need additional development tools (linting, type checking):

```bash
pip install -e ".[dev]"
```

This installs the optional dev dependencies defined in `pyproject.toml`.

## License

This project is licensed under the MIT License.
