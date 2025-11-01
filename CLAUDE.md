# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

plaid2beancount is a Python CLI tool that syncs financial transactions from Plaid API to Beancount format. It downloads transactions from connected bank accounts, stores them in SQLite via Peewee ORM, and outputs them as Beancount entries. The project supports both regular transactions and investment transactions.

## Key Commands

### Development Setup
```bash
pip install -r requirements.txt
```

### Running the Main Tool
```bash
python main.py --sync-transactions --root-file path/to/root.beancount
```

### Command-Line Options
- `--sync-transactions, -s`: Sync transactions and generate beancount entries
- `--recategorize, -r`: Re-categorize existing transactions based on current rules
- `--update-permissions, -u`: Update Plaid item permissions via web interface
- `--show-accounts, -a`: Show Plaid account information for a selected item
- `--start-date YYYY-MM-DD`: Start date for recategorization
- `--end-date YYYY-MM-DD`: End date for recategorization
- `--config-file STR`: Path to config file (default: ~/.config/plaid2text/config)
- `--root-file STR`: Path to root beancount file
- `--debug`: Enable debug mode (retrieves only first batch of transactions)

### Running Tests
```bash
pytest
pytest tests/test_import.py
pytest tests/test_recategorize.py
```

## Architecture

### Data Flow
1. **Configuration Loading**: Loads Plaid credentials from config file (`~/.config/plaid2text/config`)
2. **Beancount Metadata Extraction**: Parses root beancount file to extract:
   - Account mappings (plaid_account_id → beancount account name)
   - Expense categorization rules (plaid_category or payee → expense account)
   - Transaction file paths (where to write transactions)
   - Plaid items (item_id + access_token)
   - Cursors (for incremental sync)
3. **Transaction Sync**: Uses Plaid API's `transactions_sync` endpoint with cursors for incremental updates
4. **Investment Sync**: Uses Plaid API's `investments_transactions_get` endpoint for investment accounts
5. **Rendering**: Converts Plaid transactions to Beancount format via `BeancountRenderer`
6. **Writing**: Writes transactions to individual account files, avoiding duplicates

### Core Modules

**main.py** (main:1-1191)
- Entry point and orchestration
- Handles all CLI commands
- Contains transaction syncing logic (`_update_transactions`, `_update_investments`)
- Manages beancount file parsing and writing
- Implements recategorization logic (`_recategorize_transactions`)

**models.py** (models:1-114)
- Data models as Python dataclasses
- `PlaidTransaction`: Regular transactions (date, amount, merchant, category)
- `PlaidInvestmentTransaction`: Investment transactions (buy/sell/dividend)
- `Account`: Bank account metadata
- `PlaidItem`: Plaid item (institution connection)
- `FinanceCategory`: Expense categorization
- `PlaidSecurity`: Investment security (stocks, bonds, etc.)

**plaid_models.py** (plaid_models:1-101)
- Alternative model definitions with beancount integration
- `PlaidCursor`: Custom beancount directive for tracking sync state

**transactions/beancount_renderer.py** (beancount_renderer:1-188)
- `BeancountRenderer`: Converts Plaid transactions to Beancount format
- `_to_beancount()`: Handles regular transactions
- `_to_investment_beancount()`: Complex logic for investment transactions (buy/sell/dividend/transfer/sweep)

**plaid_link_server.py** (plaid_link_server:1-307)
- Flask web server for OAuth-based Plaid Link updates
- Detects items needing reauthorization (ITEM_LOGIN_REQUIRED)
- Updates access tokens in beancount file after reauth

### Beancount File Structure

The tool expects a hierarchical beancount file structure:
- Root file: Contains account Open directives with Plaid metadata
- Account files: Individual transaction files (e.g., `accounts/Chase/Checking.beancount`)
- Cursors file: `plaid_cursors.beancount` stores sync state

### Account Metadata in Beancount Files

Accounts must have these metadata fields:
```beancount
2020-01-01 open Assets:Bank:Checking
  plaid_account_id: "abc123"
  plaid_item_id: "item_xyz"
  plaid_access_token: "access-sandbox-..."
  transaction_file: "accounts/Bank/Checking.beancount"
  short_name: "Chase Checking"
```

### Expense Categorization

Two methods (payee rules override category rules):
1. **Category-based**: Map Plaid's `personal_finance_category.detailed` to expense accounts
2. **Payee-based**: Map merchant/payee names to expense accounts

Add to beancount account metadata:
```beancount
2020-01-01 open Expenses:Groceries
  plaid_category: "FOOD_AND_DRINK_GROCERIES"
  payees: "whole foods, trader joes, safeway"
```

### Cursor Management

Cursors track sync state per account+item. They're stored as custom directives:
```beancount
2024-11-01 custom "plaid_cursor" "Assets:Bank:Checking" "cursor_value_here" "item_id_here"
```

The tool reads cursors to do incremental syncs (avoiding re-downloading all transactions).

### Transaction Deduplication

Uses `plaid_transaction_id` metadata to detect duplicates. Also filters by date (only writes transactions newer than the newest existing transaction in each file).

### Investment Transaction Handling

Investment transactions have complex rendering logic based on `type` and `subtype`:
- **buy**: Cash → Security
- **sell**: Security → Cash (with capital gains posting)
- **dividend**: Income:TICKER:Dividends → Cash (e.g., `Income:Vanguard:Brokerage:NVDA:Dividends`)
- **transfer**: Used for sweep in/out between cash and money market funds
- **fee**: Various fees or dividends (depending on subtype)

Commodities are referenced by ticker symbol. Each account has sub-accounts like `Assets:Investments:Brokerage:Cash` and `Assets:Investments:Brokerage:VTSAX`.

**Note:** Dividend accounts follow the structure `Income:{account_path}:{TICKER}:Dividends` where the ticker comes before "Dividends".

## Development Notes

### Config File Format
```ini
[PLAID]
client_id = your_client_id
secret = your_secret
```

### Debugging
- Use `--debug` flag to limit transaction fetches (one batch only)
- Debug logging available via Python's logging module
- Check `logger.debug()` statements in main.py for transaction flow

### Error Handling
- `ITEM_LOGIN_REQUIRED`: Use `--update-permissions` to reauthorize
- Missing accounts: Ensure beancount file has proper `plaid_account_id` metadata
- Validation errors: The tool loads individual transaction files which may have incomplete references; errors are expected and filtered

### Package Structure
- Entry point: `plaid2beancount` command (configured in pyproject.toml)
- Python 3.10+ required
- Dependencies: plaid-python, beancount, flask

### Investment Transaction Quirks
- Some dividends are recorded with `type=fee, subtype=dividend`
- Sweep transactions may have `quantity=0` (use amount as fallback)
- Vanguard uses different transaction types over time (e.g., `transfer` for sweeps)
- Capital gains posting is automatically added for sell transactions
