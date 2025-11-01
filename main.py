from datetime import date, datetime, timedelta
from decimal import Decimal
import argparse
import configparser
import os
import time
from typing import Dict, List, Optional, Tuple
import logging
import tempfile
import webbrowser
import threading

import plaid
from plaid.api import plaid_api
from plaid.configuration import Configuration, Environment
from plaid.api_client import ApiClient
from plaid.exceptions import ApiException

try:
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
    from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest
    from plaid.model.investments_transactions_get_request_options import InvestmentsTransactionsGetRequestOptions
    from plaid.model.plaid_error import PlaidError
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_update import LinkTokenCreateRequestUpdate
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode
except ImportError:
    # Newer SDK uses different import paths
    from plaid.models import AccountsGetRequest
    from plaid.models import TransactionsSyncRequest
    from plaid.models import InvestmentsTransactionsGetRequest
    from plaid.models import InvestmentsTransactionsGetRequestOptions
    from plaid.models import PlaidError
    from plaid.models import LinkTokenCreateRequest
    from plaid.models import LinkTokenCreateRequestUpdate
    from plaid.models import ItemPublicTokenExchangeRequest
    from plaid.models import Products
    from plaid.models import CountryCode

from flask import Flask, request, render_template_string, jsonify

from beancount.core import data
from beancount.core.data import Custom, Directive, Open
from beancount.parser import printer
from beancount.parser import parser
from beancount import loader

from plaid_models import PlaidTransaction, PlaidInvestmentTransaction, PlaidSecurity, PlaidInvestmentTransactionType, Account, FinanceCategory, PlaidItem, PlaidCursor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _parse_args_and_load_config():
    defaults = {
        "config_file": "~/.config/plaid2text/config",
    }

    parser = argparse.ArgumentParser(
        prog="Plaid2Beancount",
    )
    parser.set_defaults(**defaults)

    parser.add_argument(
        "--sync-transactions",
        "-s",
        action="store_true",
        help="sync transactions and generate beancount entries",
    )

    parser.add_argument(
        "--recategorize",
        "-r",
        action="store_true",
        help="re-categorize existing transactions based on current categorization rules",
    )

    parser.add_argument(
        "--update-permissions",
        "-u",
        action="store_true",
        help="update Plaid item permissions via web interface",
    )

    parser.add_argument(
        "--show-accounts",
        "-a",
        action="store_true",
        help="show Plaid account information for a selected item",
    )

    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        help="Start date for recategorization (format: YYYY-MM-DD)",
    )

    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        help="End date for recategorization (format: YYYY-MM-DD)",
    )

    parser.add_argument(
        "--config-file",
        metavar="STR",
        help="Path to the config file (default: ~/.config/plaid2text/config)",
    )

    parser.add_argument(
        "--root-file",
        metavar="STR",
        help="Path to the root beancount file",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to retrieve only the first batch of transactions from each account",
    )

    args = parser.parse_args()
    return args




def _get_latest_cursor(entries: List[Directive], account: str, item_id: str) -> Optional[str]:
    """Get the most recent cursor for an account from its Beancount file."""
    cursors = [
        entry for entry in entries
        if isinstance(entry, PlaidCursor) and entry.account == account and entry.item_id == item_id
    ]
    if not cursors:
        return None
    # Sort by date and get the most recent
    return sorted(cursors, key=lambda x: x.date)[-1].cursor


def _load_beancount_accounts(file_path: str) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, Dict[str, str]], Dict[str, str]]:
    """Load account mappings and cursors from beancount file."""
    entries, _, _ = loader.load_file(file_path)
    accounts = [entry for entry in entries if isinstance(entry, Open)]
    
    # Get account mappings
    short_names = {
        account.meta["plaid_account_id"]: account.account
        for account in accounts
        if "plaid_account_id" in account.meta
    }
    
    # Get expense account mappings
    expense_accounts = {}
    for account in accounts:
        if "plaid_category" in account.meta:
            expense_accounts[account.meta["plaid_category"]] = account.account
        if "payees" in account.meta:
            payees = account.meta["payees"].split(",")
            for payee in payees:
                expense_accounts[payee.strip().lower()] = account.account
    
    # Get transaction file mappings with defaults
    transaction_files = {}
    for account in accounts:
        if "transaction_file" in account.meta:
            transaction_files[account.account] = account.meta["transaction_file"]
        elif "plaid_account_id" in account.meta:
            # Generate default path based on account structure
            account_parts = account.account.split(':')
            if account_parts[0] == 'Liabilities' and account_parts[1] == 'Credit-Card':
                # For credit cards, skip the 'Credit-Card' segment
                file_path = f"accounts/{account_parts[2]}/{account_parts[3]}.beancount"
            else:
                # For other accounts, use the first two segments after the type
                file_path = f"accounts/{account_parts[1]}/{account_parts[2]}.beancount"
            transaction_files[account.account] = file_path
    
    # Get item configurations
    items = {}
    for account in accounts:
        if "plaid_item_id" in account.meta and "plaid_access_token" in account.meta:
            item_id = account.meta["plaid_item_id"]
            access_token = account.meta["plaid_access_token"]
            items[item_id] = access_token
    
    # Get cursors for each account
    cursors = {}
    for account in accounts:
        if "plaid_item_id" in account.meta:
            account_cursors = {}
            for entry in entries:
                if isinstance(entry, Custom) and entry.type == "plaid_cursor" and entry.values[0] == account.account:
                    account_cursors[entry.values[2]] = entry.values[1]  # item_id -> cursor
            if account_cursors:
                cursors[account.account] = account_cursors
    
    return short_names, expense_accounts, items, cursors, transaction_files


def _get_or_create_item(item_id: str, name: str, access_token: str, cursor: Optional[str] = None) -> PlaidItem:
    """Create a PlaidItem with the given data."""
    return PlaidItem(
        name=name,
        item_id=item_id,
            access_token=access_token,
        cursor=cursor
    )


def _get_or_create_category(primary: str, detailed: str, description: str, expense_account: Optional[str] = None) -> FinanceCategory:
    """Create a FinanceCategory with the given data."""
    return FinanceCategory(
        primary=primary,
        detailed=detailed,
        description=description,
        expense_account=expense_account
    )


def _update_transactions(client: plaid_api.PlaidApi, root_file: str, debug: bool = False) -> Tuple[List[PlaidTransaction], List[Custom]]:
    """Fetch transactions from Plaid and convert them to PlaidTransaction objects."""
    transactions = []
    cursor_directives = []
    short_names, expense_accounts, items, cursors, transaction_files = _load_beancount_accounts(root_file)
    
    for item_id, access_token in items.items():
        # Get cursor from account file
        cursor = ""
        for account_cursors in cursors.values():
            if item_id in account_cursors:
                cursor = account_cursors[item_id]
                break
        
        # First, get account information
        try:
            accounts_request = AccountsGetRequest(access_token=access_token)
            accounts_response = client.accounts_get(accounts_request)
            accounts = {
                acc["account_id"]: acc["type"]
                for acc in accounts_response["accounts"]
            }
        except ApiException as e:
            if e.status == 400 and "ITEM_LOGIN_REQUIRED" in str(e):
                logger.error(f"Item {item_id} needs reauthorization. Please use Plaid Link to update it.")
            else:
                logger.error(f"Error getting accounts for item {item_id}: {e}")
            continue

        # Find any beancount account name associated with this item (for cursor storage)
        # We need this in case the API returns no transactions
        item_account_name = None
        for account_id in accounts.keys():
            if account_id in short_names:
                item_account_name = short_names[account_id]
                break

        if not item_account_name:
            logger.warning(f"No beancount account found for item {item_id}, skipping")
            continue

        has_more = True
        while has_more:
            try:
                request = TransactionsSyncRequest(
                    access_token=access_token,
                    cursor=cursor,
                    count=500,
                )

                response = client.transactions_sync(request)
                plaid_transactions = response["added"]
                has_more = response["has_more"]
                cursor = response["next_cursor"]

                for t in plaid_transactions:
                    # Log transaction details when fetched from Plaid
                    logger.debug(f"Fetched transaction from Plaid: {t['name']} - {t['amount']} for account {short_names.get(t['account_id'], 'Unknown')}")

                    # Payee rule overrides Plaid category
                    payee = t.get("merchant_name") or t.get("name")
                    payee_lc = payee.lower() if payee else None
                    expense_account = None
                    if payee_lc and payee_lc in expense_accounts:
                        expense_account = expense_accounts[payee_lc]
                    elif t["personal_finance_category"] is not None:
                        cat_data = t["personal_finance_category"]
                        expense_account = expense_accounts.get(cat_data["detailed"])
                    if t["personal_finance_category"] is not None:
                        cat_data = t["personal_finance_category"]
                        category = _get_or_create_category(
                            cat_data["primary"],
                            cat_data["detailed"],
                            "Unknown (Plaid added a new category!)",
                            expense_account
                        )
                    else:
                        category = None

                    # Create account
                    beancount_name = short_names.get(t["account_id"], "Unknown")
                    account = Account(
                        name=t.get("account_name", "Unknown account"),
                        beancount_name=beancount_name,
                        plaid_id=t["account_id"],
                        transaction_file=transaction_files.get(beancount_name),
                        item=_get_or_create_item(item_id, "Unknown", access_token, cursor),
                        type=accounts.get(t["account_id"], "Unknown")
                    )

                    # Log transaction details
                    logger.debug(f"Processing transaction: {t['name']} - {t['amount']} for account {beancount_name}")

                    # Create transaction
                    transaction = PlaidTransaction(
                        date=date.fromisoformat(str(t["date"])) if t.get("date") else None,
                        datetime=datetime.fromisoformat(str(t["datetime"])) if t.get("datetime") else None,
                        authorized_date=date.fromisoformat(str(t["authorized_date"])) if t.get("authorized_date") else None,
                        authorized_datetime=datetime.fromisoformat(str(t["authorized_datetime"])) if t.get("authorized_datetime") else None,
                        name=t["name"],
                        merchant_name=t.get("merchant_name"),
                        website=t.get("website"),
                        amount=Decimal(str(t["amount"])),
                        currency=t.get("iso_currency_code", "USD"),
                        check_number=t.get("check_number"),
                        transaction_id=t["transaction_id"],
                        account=account,
                        personal_finance_category=category,
                        personal_finance_confidence=t.get("personal_finance_category", {}).get("confidence_level", "UNKNOWN"),
                        pending=t["pending"]
                    )
                    transactions.append(transaction)

                # Save cursor after every successful API call, even if no transactions returned
                # This prevents re-requesting the same data and hitting rate limits
                if cursor:
                    # Only create one cursor directive per item_id
                    cursor_directive = Custom(
                        date=date.today(),
                        meta={"plaid_transaction_id": f"cursor_{date.today()}"},
                        type="plaid_cursor",
                        values=[(item_account_name, "string"), (cursor, "string"), (item_id, "string")]
                    )
                    # Remove any existing cursor directives for this item_id
                    cursor_directives = [d for d in cursor_directives if d.values[2][0] != item_id]
                    cursor_directives.append(cursor_directive)
            except ApiException as e:
                logger.error(f"Error fetching transactions for item {item_id}: {e}")
                break
            if debug:
                break  # Only retrieve the first batch of transactions in debug mode
    return transactions, cursor_directives


def _update_investments(client: plaid_api.PlaidApi, root_file: str) -> List[PlaidInvestmentTransaction]:
    """Update investment transactions for all items."""
    # Load accounts and cursors
    short_names, expense_accounts, items, cursors, transaction_files = _load_beancount_accounts(root_file)
    
    investment_transactions = []
    for item_id, access_token in items.items():
        try:
            # Get investment transactions
            request = InvestmentsTransactionsGetRequest(
                access_token=access_token,
                start_date=date.today() - timedelta(weeks=24 * 4), # Plaid API only supports 24 months
                end_date=date.today()
            )
            response = client.investments_transactions_get(request)
            accounts = {a["account_id"]: a for a in response["accounts"]}
            securities = {s["security_id"]: s for s in response["securities"]}
            
            # Process each transaction
            for t in response["investment_transactions"]:
                logger.debug(f"Raw transaction type: {t['type']}, subtype: {t.get('subtype')}")
                logger.debug(f"Raw transaction: {t}")
                # Convert date to string if it's not already
                transaction_date = t["date"]
                if not isinstance(transaction_date, str):
                    transaction_date = transaction_date.isoformat()
                
                # Create account
                beancount_name = short_names.get(t["account_id"], "Unknown")
                account = Account(
                    name=t.get("account_name", "Unknown account"),
                    beancount_name=beancount_name,
                    plaid_id=t["account_id"],
                    transaction_file=transaction_files.get(beancount_name),
                    item=_get_or_create_item(item_id, "Unknown", access_token),
                    type=accounts[t["account_id"]]["type"]
                )
                
                investment_transactions.append(
                    PlaidInvestmentTransaction(
                        date=date.fromisoformat(transaction_date),
                        name=t["name"],
                        quantity=Decimal(str(t["quantity"])) if t.get("quantity") else Decimal("0"),
                        price=Decimal(str(t["price"])) if t.get("price") else Decimal("0"),
                        amount=Decimal(str(t["amount"])) if t.get("amount") else Decimal("0"),
                        security=PlaidSecurity(
                            security_id=t["security_id"],
                            name=securities[t["security_id"]]["name"],
                            ticker_symbol=securities[t["security_id"]].get("ticker_symbol", ""),
                            type=securities[t["security_id"]]["type"],
                            market_identifier_code=securities[t["security_id"]].get("iso_currency_code", ""),
                            is_cash_equivalent=securities[t["security_id"]].get("is_cash_equivalent", False),
                            isin=securities[t["security_id"]].get("isin", ""),
                            cusip=securities[t["security_id"]].get("cusip", "")
                        ) if t.get("security_id") and t["security_id"] in securities else None,
                        fees=Decimal(str(t["fees"])) if t.get("fees") else Decimal("0"),
                        cancel_transaction_id=t.get("cancel_transaction_id", ""),
                        investment_transaction_id=t["investment_transaction_id"],
                        iso_currency_code=t.get("iso_currency_code", "USD"),
                        type=PlaidInvestmentTransactionType(
                            type=t["type"],
                            subtype=t.get("subtype", "")
                        ),
                        account=account
                    )
                )
        except ApiException as e:
            logger.warning(f"Error getting investment transactions for item {item_id}: {e}")
            continue
    
    return investment_transactions


def _write_transactions_to_file(transactions: List[PlaidTransaction], file_path: str):
    """Write transactions to the specified file."""
    with open(file_path, 'a') as f:
        for transaction in transactions:
            # Log when writing transaction to file
            logger.debug(f"Writing transaction to file: {transaction.name} - {transaction.amount} for account {transaction.account.beancount_name}")
            f.write(f"{transaction.date} {transaction.name} {transaction.amount}\n")


def _skip_duplicate_transactions(transactions: List[PlaidTransaction], existing_transactions: List[PlaidTransaction]) -> List[PlaidTransaction]:
    """Skip duplicate transactions based on transaction ID."""
    unique_transactions = []
    for transaction in transactions:
        if transaction.transaction_id not in [t.transaction_id for t in existing_transactions]:
            unique_transactions.append(transaction)
        else:
            logger.debug(f"Skipping duplicate transaction: {transaction.name} - {transaction.amount} for account {transaction.account.beancount_name}")
    return unique_transactions


def _get_plaid_items_from_beancount(root_file: str) -> Dict[str, Tuple[str, str, str]]:
    """Extract Plaid items from beancount file.

    Returns:
        Dict mapping item_id to (account_name, access_token, short_name)
    """
    entries, _, _ = loader.load_file(root_file)
    accounts = [entry for entry in entries if isinstance(entry, Open)]

    items = {}
    for account in accounts:
        if "plaid_item_id" in account.meta and "plaid_access_token" in account.meta:
            item_id = account.meta["plaid_item_id"]
            access_token = account.meta["plaid_access_token"]
            short_name = account.meta.get("short_name", account.account)
            items[item_id] = (account.account, access_token, short_name)

    return items


def _update_access_token_in_beancount(root_file: str, account_name: str, new_access_token: str):
    """Update the access token for an account in the beancount file."""
    with open(root_file, 'r') as f:
        lines = f.readlines()

    new_lines = []
    in_account = False
    account_indent = ""

    for line in lines:
        # Check if this line opens the account we're looking for
        if f"open {account_name}" in line:
            in_account = True
            new_lines.append(line)
            # Determine the indentation used for metadata
            account_indent = "  "
        elif in_account:
            # Check if we're still in the account's metadata section
            if line.strip() and not line.startswith(account_indent) and not line.startswith("  "):
                # We've left the account section
                in_account = False
                new_lines.append(line)
            elif "plaid_access_token:" in line:
                # Replace the access token
                new_lines.append(f'{account_indent}plaid_access_token: "{new_access_token}"\n')
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(root_file, 'w') as f:
        f.writelines(new_lines)

    logger.info(f"Updated access token for {account_name} in {root_file}")


def _start_update_permissions_server(client: plaid_api.PlaidApi, root_file: str, item_id: str,
                                     account_name: str, access_token: str, short_name: str):
    """Start Flask server for updating Plaid item permissions."""

    # HTML template for the update page
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Update Plaid Permissions</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .success { color: green; font-weight: bold; }
        .error { color: red; font-weight: bold; }
        button { padding: 10px 20px; font-size: 16px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Update Plaid Permissions</h1>
    <p>Update permissions for: <strong>{{ short_name }}</strong> ({{ account_name }})</p>
    <div id="status"></div>
    <button id="link-button">Update Permissions</button>

    <script>
        const handler = Plaid.create({
            token: '{{ link_token }}',
            onSuccess: async (public_token, metadata) => {
                document.getElementById('status').innerHTML = 'Updating access token...';
                try {
                    const response = await fetch('/exchange_token', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ public_token: public_token })
                    });
                    const result = await response.json();
                    if (result.success) {
                        document.getElementById('status').className = 'success';
                        document.getElementById('status').innerHTML = 'Successfully updated permissions! You can close this window.';
                        document.getElementById('link-button').style.display = 'none';
                    } else {
                        document.getElementById('status').className = 'error';
                        document.getElementById('status').innerHTML = 'Error: ' + result.error;
                    }
                } catch (error) {
                    document.getElementById('status').className = 'error';
                    document.getElementById('status').innerHTML = 'Error: ' + error;
                }
            },
            onExit: (err, metadata) => {
                if (err != null) {
                    document.getElementById('status').className = 'error';
                    document.getElementById('status').innerHTML = 'Error: ' + err.error_message;
                }
            }
        });

        document.getElementById('link-button').onclick = () => {
            document.getElementById('status').innerHTML = '';
            handler.open();
        };
    </script>
</body>
</html>
    """

    app = Flask(__name__)
    app.logger.setLevel(logging.ERROR)  # Suppress Flask logs

    # Create link token for update mode
    try:
        link_request = LinkTokenCreateRequest(
            user={"client_user_id": "user-id"},
            client_name="Plaid2Beancount",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
            access_token=access_token,
            update=LinkTokenCreateRequestUpdate(
                account_selection_enabled=False
            )
        )
        link_response = client.link_token_create(link_request)
        link_token = link_response["link_token"]
    except Exception as e:
        logger.error(f"Error creating link token: {e}")
        return

    @app.route('/')
    def index():
        return render_template_string(
            HTML_TEMPLATE,
            short_name=short_name,
            account_name=account_name,
            link_token=link_token
        )

    @app.route('/exchange_token', methods=['POST'])
    def exchange_token():
        data = request.get_json()
        public_token = data.get('public_token')

        try:
            # Exchange public token for access token
            exchange_request = ItemPublicTokenExchangeRequest(
                public_token=public_token
            )
            exchange_response = client.item_public_token_exchange(exchange_request)
            new_access_token = exchange_response["access_token"]

            # Update the beancount file
            _update_access_token_in_beancount(root_file, account_name, new_access_token)

            logger.info(f"Successfully updated access token for {short_name}")
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Error exchanging token: {e}")
            return jsonify({"success": False, "error": str(e)})

    # Open browser automatically
    def open_browser():
        time.sleep(1)
        webbrowser.open('http://localhost:5000')

    threading.Thread(target=open_browser, daemon=True).start()

    # Run the server
    logger.info("Starting webserver at http://localhost:5000")
    logger.info("Press Ctrl+C to stop the server after completing the update")
    app.run(port=5000, debug=False)


def _display_account_info(client: plaid_api.PlaidApi, item_id: str, access_token: str, short_name: str):
    """Fetch and display Plaid account information for an item."""
    try:
        # Get account information
        accounts_request = AccountsGetRequest(access_token=access_token)
        accounts_response = client.accounts_get(accounts_request)

        print(f"\n{'='*80}")
        print(f"Account Information for: {short_name}")
        print(f"Item ID: {item_id}")
        print(f"{'='*80}\n")

        if not accounts_response["accounts"]:
            print("No accounts found for this item.")
            return

        for i, account in enumerate(accounts_response["accounts"], 1):
            print(f"Account {i}:")
            print(f"  Name:            {account.get('name', 'N/A')}")
            print(f"  Official Name:   {account.get('official_name', 'N/A')}")
            print(f"  Account ID:      {account.get('account_id', 'N/A')}")
            print(f"  Type:            {account.get('type', 'N/A')}")
            print(f"  Subtype:         {account.get('subtype', 'N/A')}")

            # Display balance information
            balances = account.get('balances', {})
            if balances:
                print(f"  Balances:")
                if balances.get('current') is not None:
                    currency = balances.get('iso_currency_code', 'USD')
                    print(f"    Current:       {balances['current']} {currency}")
                if balances.get('available') is not None:
                    currency = balances.get('iso_currency_code', 'USD')
                    print(f"    Available:     {balances['available']} {currency}")
                if balances.get('limit') is not None:
                    currency = balances.get('iso_currency_code', 'USD')
                    print(f"    Limit:         {balances['limit']} {currency}")

            # Display mask (last 4 digits)
            if account.get('mask'):
                print(f"  Mask:            ****{account['mask']}")

            print()

        # Display item information
        item = accounts_response.get("item", {})
        if item:
            print(f"Item Information:")
            print(f"  Institution ID:  {item.get('institution_id', 'N/A')}")

            # Convert Products objects to strings
            available_products = item.get('available_products', [])
            available_products_str = ', '.join([str(p) for p in available_products]) if available_products else 'None'
            print(f"  Available Products: {available_products_str}")

            billed_products = item.get('billed_products', [])
            billed_products_str = ', '.join([str(p) for p in billed_products]) if billed_products else 'None'
            print(f"  Billed Products:    {billed_products_str}")

            if item.get('update_type'):
                print(f"  Update Type:     {item['update_type']}")
            print()

        print(f"{'='*80}\n")

    except ApiException as e:
        if e.status == 400 and "ITEM_LOGIN_REQUIRED" in str(e):
            logger.error(f"Item {item_id} needs reauthorization. Please use --update-permissions to update it.")
        else:
            logger.error(f"Error getting account information for item {item_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting account information: {e}")


def _recategorize_transactions(root_file: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> int:
    """Re-categorize existing transactions based on current categorization rules."""
    # Load current categorization rules
    short_names, expense_accounts, items, cursors, transaction_files = _load_beancount_accounts(root_file)
    
    # Parse date filters
    start_dt = None
    end_dt = None
    if start_date:
        start_dt = date.fromisoformat(start_date)
    if end_date:
        end_dt = date.fromisoformat(end_date)
    
    recategorized_count = 0
    
    # Process each transaction file
    base_dir = os.path.dirname(os.path.abspath(root_file))
    for file_path in transaction_files.values():
        full_path = os.path.join(base_dir, file_path)
        if not os.path.exists(full_path):
            continue
            
        logger.info(f"Processing file: {full_path}")
        
        # Load the transaction file directly for processing (validation errors are expected)
        entries, errors, options = loader.load_file(full_path)
        if errors:
            logger.debug(f"Validation errors loading {full_path} (expected during processing): {len(errors)} errors")
        
        # Filter transactions by date if specified
        transactions_to_process = []
        for entry in entries:
            if isinstance(entry, data.Transaction):
                if start_dt and entry.date < start_dt:
                    continue
                if end_dt and entry.date > end_dt:
                    continue
                transactions_to_process.append(entry)
        
        # Process each transaction
        modified_entries = []
        for entry in entries:
            if isinstance(entry, data.Transaction) and entry in transactions_to_process:
                # Get the payee name for categorization
                payee = (entry.payee or entry.narration)
                payee_lc = payee.lower() if payee else payee
                
                # Find the expense posting (second posting for most transactions)
                expense_posting = None
                for posting in entry.postings:
                    if posting.account.startswith("Expenses:"):
                        expense_posting = posting
                        break
                
                if not expense_posting:
                    continue
                
                # Check if payee matches any explicit payee rules
                new_expense_account = None
                if payee_lc:
                    logger.debug(f"Checking payee: '{payee_lc}' against expense accounts: {list(expense_accounts.keys())}")
                    # Check for exact match first
                    if payee_lc in expense_accounts:
                        new_expense_account = expense_accounts[payee_lc]
                        logger.debug(f"Found exact match: {payee_lc} -> {new_expense_account}")
                    else:
                        # Check for partial matches (transaction payee should be found within the payee rule)
                        for payee_rule, account in expense_accounts.items():
                            if payee_rule and payee_lc in payee_rule:
                                new_expense_account = account
                                logger.debug(f"Found partial match: '{payee_lc}' in '{payee_rule}' -> {new_expense_account}")
                                break
                
                # If we found a new categorization, update the transaction
                if new_expense_account and new_expense_account != expense_posting.account:
                    logger.debug(f"Recategorizing transaction from {expense_posting.account} to {new_expense_account}")
                    # Create new postings with updated expense account
                    new_postings = []
                    for posting in entry.postings:
                        if posting.account.startswith("Expenses:"):
                            # Update the expense account
                            new_postings.append(
                                data.Posting(
                                    account=new_expense_account,
                                    units=posting.units,
                                    cost=posting.cost,
                                    price=posting.price,
                                    flag=posting.flag,
                                    meta=posting.meta
                                )
                            )
                        else:
                            # Keep other postings unchanged
                            new_postings.append(posting)
                    
                    # Create updated transaction
                    # Copy all metadata fields, including plaid_transaction_id
                    new_meta = dict(entry.meta) if entry.meta else {}
                    if entry.meta and 'plaid_transaction_id' in entry.meta:
                        new_meta['plaid_transaction_id'] = entry.meta['plaid_transaction_id']
                    updated_entry = data.Transaction(
                        meta=new_meta,
                        date=entry.date,
                        flag=entry.flag,
                        payee=entry.payee,
                        narration=entry.narration,
                        tags=entry.tags,
                        links=entry.links,
                        postings=new_postings
                    )
                    logger.debug(f"Modified transaction metadata: {updated_entry.meta}")
                    modified_entries.append(updated_entry)
                    recategorized_count += 1
                else:
                    if new_expense_account:
                        logger.debug(f"Transaction already has correct account: {expense_posting.account}")
                    else:
                        logger.debug(f"No matching payee rule found for: {payee_lc}")
                    modified_entries.append(entry)
            else:
                modified_entries.append(entry)
        
        # Write updated transactions back to file using inline modification
        if recategorized_count > 0:
            # Read the original file content
            with open(full_path, 'r') as f:
                lines = f.readlines()
            
            # Create a mapping of transactions that need to be modified
            transactions_to_modify = {}
            for entry in modified_entries:
                if isinstance(entry, data.Transaction):
                    # Use transaction ID or full metadata to identify the transaction
                    identifier = None
                    meta_identifier = None
                    if entry.meta and 'plaid_transaction_id' in entry.meta:
                        identifier = entry.meta['plaid_transaction_id']
                        logger.debug(f"Using plaid_transaction_id as identifier: {identifier}")
                    # Always create the metadata identifier
                    date_str = entry.date.strftime('%Y-%m-%d')
                    flag_str = entry.flag if entry.flag else ''
                    payee_str = entry.payee if entry.payee else ''
                    narration_str = entry.narration if entry.narration else ''
                    meta_identifier = f"{date_str}_{flag_str}_{payee_str}_{narration_str}"
                    logger.debug(f"Using metadata as identifier: {meta_identifier}")
                    # Add both identifiers if available
                    if identifier:
                        transactions_to_modify[identifier] = entry
                        logger.debug(f"Added transaction to modifications: {identifier}")
                    transactions_to_modify[meta_identifier] = entry
                    logger.debug(f"Added transaction to modifications: {meta_identifier}")
            
            logger.debug(f"Transactions to modify: {list(transactions_to_modify.keys())}")
            
            # Parse the file to find transaction boundaries and modify in place
            new_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                stripped_line = line.strip()
                
                # Check if this line starts a new transaction (starts with a date)
                if stripped_line and len(stripped_line) >= 10 and stripped_line[:10].replace('-', '').isdigit():
                    # Try to identify this transaction
                    transaction_identifier = None
                    transaction_lines = [line]
                    j = i + 1
                    
                    # Collect all lines that belong to this transaction
                    while j < len(lines):
                        next_line = lines[j]
                        next_stripped = next_line.strip()
                        
                        # If next line starts with a date, it's a new transaction
                        if next_stripped and len(next_stripped) >= 10 and next_stripped[:10].replace('-', '').isdigit():
                            break
                        
                        # If next line is empty, it might be the end of the transaction
                        if not next_stripped:
                            # Check if the line after this is a new transaction
                            if j + 1 < len(lines):
                                next_next_stripped = lines[j + 1].strip()
                                if next_next_stripped and len(next_next_stripped) >= 10 and next_next_stripped[:10].replace('-', '').isdigit():
                                    break
                        
                        transaction_lines.append(next_line)
                        j += 1
                    
                    # Try to extract transaction identifier from the transaction lines
                    transaction_text = ''.join(transaction_lines)
                    
                    # Look for plaid_transaction_id in the transaction
                    import re
                    for tx_line in transaction_lines:
                        if 'plaid_transaction_id:' in tx_line:
                            match = re.search(r'plaid_transaction_id:\s*"([^"]+)"', tx_line)
                            if match:
                                transaction_identifier = match.group(1)
                                break
                    
                    # If no transaction ID, try to match by full transaction metadata
                    if not transaction_identifier:
                        # Extract the full transaction metadata from the first line
                        # Format: date flag "payee" "narration"
                        tx_pattern = r'^(\d{4}-\d{2}-\d{2})\s+([*!]?)\s*"([^"]*)"\s*"([^"]*)"'
                        match = re.match(tx_pattern, stripped_line)
                        if match:
                            date_part, flag_part, payee_part, narration_part = match.groups()
                            # Create a unique identifier from the full transaction metadata
                            transaction_identifier = f"{date_part}_{flag_part}_{payee_part}_{narration_part}"
                    
                    # Check if this transaction needs to be modified
                    if transaction_identifier and transaction_identifier in transactions_to_modify:
                        # Replace the transaction with the modified version
                        modified_entry = transactions_to_modify[transaction_identifier]
                        new_lines.append(printer.format_entry(modified_entry) + '\n')
                        logger.debug(f"Modified transaction: {transaction_identifier}")
                    else:
                        # Keep the original transaction
                        new_lines.extend(transaction_lines)
                        if transaction_identifier:
                            logger.debug(f"Transaction not found in modifications: {transaction_identifier}")
                        else:
                            logger.debug(f"Could not identify transaction")
                    
                    # Skip to the end of this transaction
                    i = j
                else:
                    # Keep non-transaction lines as-is
                    new_lines.append(line)
                    i += 1
            
            # Write the modified content back to file
            with open(full_path, 'w') as f:
                f.writelines(new_lines)
            
            logger.info(f"Updated {recategorized_count} transactions in {full_path}")
    
    # Always validate the entire setup by loading the root file (which includes all transaction files)
    logger.info("Validating recategorization by loading root file...")
    root_entries, root_errors, root_options = loader.load_file(root_file)
    if root_errors:
        # Filter out errors that aren't related to recategorization
        recategorization_errors = []
        for error in root_errors:
            # Skip plugin import errors (these are environment issues, not recategorization issues)
            if hasattr(error, 'message') and 'ModuleNotFoundError' in error.message:
                logger.debug(f"Skipping plugin error (not related to recategorization): {error}")
                continue
            # Skip missing account errors for investment accounts (these are expected in some setups)
            if hasattr(error, 'message') and 'Invalid reference to unknown account' in error.message and 'Income:' in error.message:
                logger.debug(f"Skipping missing investment account error (not related to recategorization): {error}")
                continue
            # Include other validation errors
            recategorization_errors.append(error)
        
        if recategorization_errors:
            logger.error(f"Validation errors after recategorization: {recategorization_errors}")
            return -1  # Indicate failure
        else:
            logger.info("Recategorization validation successful - only non-critical errors found")
    else:
        logger.info("Recategorization validation successful - no errors")
    
    return recategorized_count


def main():
    args = _parse_args_and_load_config()

    # Set up debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    # Load config
    config = configparser.ConfigParser()
    config.read(os.path.expanduser(args.config_file))

    # Initialize Plaid client
    configuration = Configuration(
        host=Environment.Production,
        api_key={
            "clientId": config["PLAID"]["client_id"],
            "secret": config["PLAID"]["secret"],
        },
    )
    api_client = ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)

    if args.update_permissions:
        # Extract all Plaid items from beancount file
        items = _get_plaid_items_from_beancount(args.root_file)

        if not items:
            logger.error("No Plaid items found in beancount file.")
            logger.error("Make sure your account Open directives have both 'plaid_item_id' and 'plaid_access_token' metadata.")
            return

        # Display available items
        print("\nAvailable Plaid items:")
        print("-" * 50)
        item_list = list(items.items())
        for i, (item_id, (account_name, _, short_name)) in enumerate(item_list, 1):
            print(f"{i}. {short_name} ({account_name})")
            print(f"   Item ID: {item_id}")

        # Get user selection
        print("-" * 50)
        while True:
            try:
                selection = input("\nSelect an item to update (enter number): ").strip()
                index = int(selection) - 1
                if 0 <= index < len(item_list):
                    break
                else:
                    print(f"Please enter a number between 1 and {len(item_list)}")
            except ValueError:
                print("Please enter a valid number")
            except KeyboardInterrupt:
                print("\nCancelled")
                return

        # Get selected item details
        selected_item_id, (account_name, access_token, short_name) = item_list[index]
        print(f"\nStarting permission update for: {short_name}")

        # Start the webserver
        _start_update_permissions_server(
            client,
            args.root_file,
            selected_item_id,
            account_name,
            access_token,
            short_name
        )
        return

    if args.show_accounts:
        # Extract all Plaid items from beancount file
        items = _get_plaid_items_from_beancount(args.root_file)

        if not items:
            logger.error("No Plaid items found in beancount file.")
            logger.error("Make sure your account Open directives have both 'plaid_item_id' and 'plaid_access_token' metadata.")
            return

        # Display available items
        print("\nAvailable Plaid items:")
        print("-" * 50)
        item_list = list(items.items())
        for i, (item_id, (account_name, _, short_name)) in enumerate(item_list, 1):
            print(f"{i}. {short_name} ({account_name})")
            print(f"   Item ID: {item_id}")

        # Get user selection
        print("-" * 50)
        while True:
            try:
                selection = input("\nSelect an item to view accounts (enter number): ").strip()
                index = int(selection) - 1
                if 0 <= index < len(item_list):
                    break
                else:
                    print(f"Please enter a number between 1 and {len(item_list)}")
            except ValueError:
                print("Please enter a valid number")
            except KeyboardInterrupt:
                print("\nCancelled")
                return

        # Get selected item details and display account info
        selected_item_id, (account_name, access_token, short_name) = item_list[index]
        _display_account_info(client, selected_item_id, access_token, short_name)
        return

    if args.sync_transactions:
        # Fetch transactions
        transactions, cursor_directives = _update_transactions(client, args.root_file, args.debug)        
        investment_transactions = _update_investments(client, args.root_file)
        
        # Generate Beancount entries
        from transactions.beancount_renderer import BeancountRenderer
        renderer = BeancountRenderer(transactions, investment_transactions)
        entries = [renderer._to_beancount(transaction) for transaction in transactions] + [renderer._to_investment_beancount(transaction) for transaction in investment_transactions]
        logger.info(f"Generated {len(entries)} entries")
                
        # Group transactions by account
        account_entries = {}
        for entry in entries:
            # Get the first posting's account to determine which file to write to
            if isinstance(entry, data.Transaction) and entry.postings:
                logger.debug(f"Processing entry: {entry}")
                account = entry.postings[0].account
                # Find the corresponding Account object for this beancount account name
                # First check for exact match, then for substring (i.e. prefer Assets:Investments:Brokerage:Cash over Assets:Investments:Brokerage)
                matching_account = next((t.account for t in transactions + investment_transactions 
                                      if t.account.beancount_name == account), None)
                if not matching_account:
                    matching_account = next((t.account for t in transactions + investment_transactions 
                                      if t.account.beancount_name in account), None)
                if matching_account and matching_account.transaction_file:
                    if matching_account.transaction_file not in account_entries:
                        account_entries[matching_account.transaction_file] = []
                    account_entries[matching_account.transaction_file].append(entry)
                else:
                    logger.warning(f"No matching account found for {entry}")
            else:
                logger.debug(f"Skipping entry: {entry}")
                logger.debug(f"Entry type: {type(entry)}")
                logger.debug(f"Entry postings: {entry.postings}")
        
        # Write transactions to their respective account files
        base_dir = os.path.dirname(os.path.abspath(args.root_file))
        for file_path, account_transactions in account_entries.items():
            logger.info(f"Looking for transactions to write for {file_path}")
            # Ensure the full path exists
            full_path = os.path.join(base_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Find the newest transaction date and collect existing transaction IDs
            newest_date = None
            existing_transaction_ids = set()
            if os.path.exists(full_path):
                entries, errors, options = loader.load_file(full_path)
                if errors:
                    logger.debug(f"Validation errors loading {full_path} (expected when loading individual files): {errors}")
                
                # Find the newest transaction and collect all transaction IDs
                for entry in entries:
                    if isinstance(entry, data.Transaction) and entry.meta and 'plaid_transaction_id' in entry.meta:
                        if newest_date is None or entry.date > newest_date:
                            newest_date = entry.date
                        existing_transaction_ids.add(entry.meta['plaid_transaction_id'])
            
            # Filter transactions to only include those newer than the newest existing transaction
            # and not already in the file
            new_transactions = []
            if newest_date is None:
                new_transactions = account_transactions
            else:
                for transaction in account_transactions:
                    if (transaction.date > newest_date and 
                        transaction.meta.get('plaid_transaction_id') not in existing_transaction_ids):
                        new_transactions.append(transaction)
            
            # Write new transactions to file
            if new_transactions:
                # Sort transactions by date in ascending order
                new_transactions.sort(key=lambda x: x.date)
                with open(full_path, 'a') as f:
                    for transaction in new_transactions:
                        f.write(printer.format_entry(transaction) + '\n')
                logger.info(f"Successfully wrote {len(new_transactions)} transactions to {full_path}")

        # Write cursor directives to file
        cursors_file = os.path.join(base_dir, "plaid_cursors.beancount")
        with open(cursors_file, 'w') as f:
            # Group cursor directives by account
            account_cursors = {}
            for directive in cursor_directives:
                account = directive.values[0][0]
                if account not in account_cursors or directive.date > account_cursors[account].date:
                    account_cursors[account] = directive

            # Store cursors for investment transactions
            for transaction in investment_transactions:
                cursor_directive = Custom(
                    date=date.today(),
                    meta={"plaid_transaction_id": f"cursor_{date.today()}"},
                    type="plaid_cursor",
                    values=[(transaction.account.beancount_name, "string"), (transaction.investment_transaction_id, "string"), (transaction.account.item.item_id, "string")]
                )
                # Update account cursors with investment transaction cursors
                account = transaction.account.beancount_name
                if account not in account_cursors or cursor_directive.date > account_cursors[account].date:
                    account_cursors[account] = cursor_directive

            # Write only the latest cursor for each account
            for directive in account_cursors.values():
                logger.debug(f"Writing cursor directive: {directive}")
                f.write(printer.format_entry(directive) + '\n')

        logger.info(f"Successfully synced {len(account_cursors)} cursors to {cursors_file}")

    if args.recategorize:
        recategorized_count = _recategorize_transactions(args.root_file, args.start_date, args.end_date)
        logger.info(f"Recategorized {recategorized_count} transactions")


if __name__ == "__main__":
    main()
