from datetime import date, datetime, timedelta
from decimal import Decimal
import argparse
import configparser
import os
import time
from typing import Dict, List, Optional, Tuple

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest
from plaid.model.investments_transactions_get_request_options import InvestmentsTransactionsGetRequestOptions
from plaid.model.plaid_error import PlaidError

from beancount.core import data
from beancount.core.data import Custom, Directive, Open
from beancount.parser import printer
from beancount.parser import parser
from beancount import loader

from plaid_models import PlaidTransaction, PlaidInvestmentTransaction, PlaidSecurity, PlaidInvestmentTransactionType, Account, FinanceCategory, PlaidItem, PlaidCursor


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
        "--config-file",
        metavar="STR",
        help="Path to the config file (default: ~/.config/plaid2text/config)",
    )

    parser.add_argument(
        "--root-file",
        metavar="STR",
        help="Path to the root beancount file",
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
    expense_accounts = {
        account.meta["plaid_category"]: account.account
        for account in accounts
        if "plaid_category" in account.meta
    }
    
    # Get transaction file mappings with defaults
    transaction_files = {}
    for account in accounts:
        if "plaid_account_id" in account.meta:
            # Use explicit transaction_file if provided
            if "transaction_file" in account.meta:
                transaction_files[account.account] = account.meta["transaction_file"]
            else:
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
        if "plaid_item_id" in account.meta:
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


def _update_transactions(client: plaid_api.PlaidApi, root_file: str) -> Tuple[List[PlaidTransaction], List[Custom]]:
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
        except plaid.ApiException as e:
            if e.status == 400 and "ITEM_LOGIN_REQUIRED" in str(e):
                print(f"Item {item_id} needs reauthorization. Please use Plaid Link to update it.")
            else:
                print(f"Error getting accounts for item {item_id}: {e}")
            continue

        has_more = True
        while has_more:
            try:
                request = TransactionsSyncRequest(
                    access_token=access_token,
                    cursor=cursor,
                    count=100,
                )

                response = client.transactions_sync(request)
                plaid_transactions = response["added"]
                has_more = response["has_more"]
                cursor = response["next_cursor"]

                for t in plaid_transactions:
                    # Create or get category
                    category = None
                    if t["personal_finance_category"] is not None:
                        cat_data = t["personal_finance_category"]
                        category = _get_or_create_category(
                            cat_data["primary"],
                            cat_data["detailed"],
                            "Unknown (Plaid added a new category!)",
                            expense_accounts.get(cat_data["detailed"])
                        )

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

                # Create cursor directive
                if account and cursor:
                    cursor_directive = Custom(
                        date=date.today(),
                        meta={"plaid_transaction_id": f"cursor_{date.today()}"},
                        type="plaid_cursor",
                        values=[(account.beancount_name, cursor), (item_id, "")]
                    )
                    cursor_directives.append(cursor_directive)

            except plaid.ApiException as e:
                if e.status == 429:  # Rate limit
                    retry_after = int(e.headers.get('Retry-After', 60))
                    print(f"Rate limit hit. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                else:
                    print(f"Error syncing transactions for item {item_id}: {e}")
                    break

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
                start_date=date(2010, 1, 1),
                end_date=date.today()
            )
            response = client.investments_transactions_get(request)
            accounts = {a["account_id"]: a for a in response["accounts"]}
            securities = {s["security_id"]: s for s in response["securities"]}
            
            # Process each transaction
            for t in response["investment_transactions"]:
                print(f"Raw transaction type: {t['type']}, subtype: {t.get('subtype')}")
                print(f"Raw transaction: {t}")
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
        except plaid.ApiException as e:
            print(f"Error getting investment transactions for item {item_id}: {e}")
            continue
    
    return investment_transactions


def main():
    args = _parse_args_and_load_config()

    # Load config
    config = configparser.ConfigParser()
    config.read(os.path.expanduser(args.config_file))
    
    # Initialize Plaid client
    configuration = plaid.Configuration(
        host=plaid.Environment.Production,
        api_key={
            "clientId": config["PLAID"]["client_id"],
            "secret": config["PLAID"]["secret"],
        },
    )
    api_client = plaid.ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)

    if args.sync_transactions:
        # Fetch transactions
        transactions, cursor_directives = _update_transactions(client, args.root_file)
        investment_transactions = _update_investments(client, args.root_file)
        
        # Generate Beancount entries
        from transactions.beancount_renderer import BeancountRenderer
        renderer = BeancountRenderer(transactions, investment_transactions)
        entries = renderer.print()
        
        # Group transactions by account
        account_entries = {}
        for entry in entries:
            # Get the first posting's account to determine which file to write to
            if isinstance(entry, data.Transaction) and entry.postings:
                account = entry.postings[0].account
                # Find the corresponding Account object for this beancount account name
                matching_account = next((t.account for t in transactions + investment_transactions 
                                      if t.account.beancount_name == account), None)
                if matching_account and matching_account.transaction_file:
                    if matching_account.transaction_file not in account_entries:
                        account_entries[matching_account.transaction_file] = []
                    account_entries[matching_account.transaction_file].append(entry)
        
        # Write transactions to their respective account files
        base_dir = os.path.dirname(os.path.abspath(args.root_file))
        for file_path, account_transactions in account_entries.items():
            # Ensure the full path exists
            full_path = os.path.join(base_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            # Write transactions to file
            with open(full_path, 'a') as f:
                for transaction in account_transactions:
                    f.write(printer.format_entry(transaction) + '\n')
            print(f"Successfully wrote {len(account_transactions)} transactions to {full_path}")

        # Write cursor directives to file
        cursors_file = os.path.join(base_dir, "plaid_cursors.beancount")
        with open(cursors_file, 'w') as f:
            for directive in cursor_directives:
                print(f"Writing cursor directive: {directive}")
                f.write(printer.format_entry(directive) + '\n')

        print(f"Successfully synced {len(cursor_directives)} cursors to {cursors_file}")


if __name__ == "__main__":
    main()
