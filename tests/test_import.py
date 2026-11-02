import os
import sys
import tempfile
import shutil
import pytest
from unittest import mock
from datetime import date

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _update_transactions, _load_beancount_accounts, _remove_transactions_from_ledger

class DummyPlaidApi:
    def accounts_get(self, request):
        return {"accounts": [
            {"account_id": "acc1", "type": "depository"},
            {"account_id": "acc2", "type": "credit"},
        ]}
    def transactions_sync(self, request):
        return {
            "added": [
                {
                    "date": "2024-01-01",
                    "name": "STARBUCKS",
                    "amount": 5.00,
                    "account_id": "acc1",
                    "transaction_id": "txn1",
                    "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_RESTAURANTS", "confidence_level": "VERY_HIGH"},
                    "pending": False,
                },
                {
                    "date": "2024-01-02",
                    "name": "GROCERY STORE",
                    "amount": 10.00,
                    "account_id": "acc1",
                    "transaction_id": "txn2",
                    "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_GROCERIES", "confidence_level": "VERY_HIGH"},
                    "pending": False,
                },
            ],
            "has_more": False,
            "next_cursor": "cursor123"
        }

def create_temp_beancount_file():
    content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  plaid_item_id: "item1"
  plaid_access_token: "access_token_123"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Groceries
  plaid_category: "FOOD_AND_DRINK_GROCERIES"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"
'''
    temp_dir = tempfile.mkdtemp()
    root_file = os.path.join(temp_dir, "root.beancount")
    with open(root_file, "w") as f:
        f.write(content)
    os.makedirs(os.path.join(temp_dir, "accounts/checking"))
    return temp_dir, root_file

class DummyPlaidApiInterest:
    def accounts_get(self, request):
        return {"accounts": [
            {"account_id": "acc1", "type": "depository"},
        ]}
    def transactions_sync(self, request):
        return {
            "added": [
                {
                    "date": "2024-01-03",
                    "name": "Interest Payment",
                    "amount": -1.50,  # negative = money coming in
                    "account_id": "acc1",
                    "transaction_id": "txn3",
                    "personal_finance_category": {"primary": "INCOME", "detailed": "INCOME_INTEREST_EARNED", "confidence_level": "VERY_HIGH"},
                    "pending": False,
                },
            ],
            "has_more": False,
            "next_cursor": "cursor456"
        }

def test_interest_income_categorization():
    temp_dir, root_file = create_temp_beancount_file()
    try:
        transactions, _ = _update_transactions(DummyPlaidApiInterest(), root_file, debug=True)
        assert len(transactions) == 1
        # Assets:Checking -> Income:Checking:Interest
        assert transactions[0].personal_finance_category.expense_account == "Income:Checking:Interest"
    finally:
        shutil.rmtree(temp_dir)


def test_import_transactions_and_categorization():
    temp_dir, root_file = create_temp_beancount_file()
    try:
        dummy_client = DummyPlaidApi()
        # Test _load_beancount_accounts first
        short_names, expense_accounts, items, cursors, transaction_files = _load_beancount_accounts(root_file)
        transactions, cursor_directives = _update_transactions(dummy_client, root_file, debug=True)
        # Check that transactions are imported
        assert len(transactions) == 2
        # Check categorization
        assert transactions[0].personal_finance_category.expense_account == "Expenses:Food:Bars"  # payee rule
        assert transactions[1].personal_finance_category.expense_account == "Expenses:Food:Groceries"  # category rule
    finally:
        shutil.rmtree(temp_dir) 

class DummyPlaidApiRules:
    def accounts_get(self, request):
        return {"accounts": [{"account_id": "acc1", "type": "depository"}]}
    def transactions_sync(self, request):
        def txn(tid, name, merchant, detailed):
            return {
                "date": "2024-01-04", "name": name, "merchant_name": merchant, "amount": 20.00,
                "account_id": "acc1", "transaction_id": tid, "pending": False,
                "personal_finance_category": {"primary": detailed.split("_")[0], "detailed": detailed, "confidence_level": "HIGH"},
            }
        return {
            "added": [
                # Payee rule matches the raw name even though Plaid supplied a merchant name
                txn("r1", "404 MEDIA", "X Media", "ENTERTAINMENT_OTHER_ENTERTAINMENT"),
                # Raw name rule takes precedence over a broader merchant rule
                txn("r2", "Costco Gas", "Costco", "TRANSPORTATION_GAS"),
                # Each entry of a comma-separated plaid_category is a separate rule
                txn("r3", "Requested transfer", None, "TRANSFER_OUT_ACCOUNT_TRANSFER"),
            ],
            "has_more": False,
            "next_cursor": "cursor789"
        }


def test_payee_name_and_multi_category_rules():
    temp_dir, root_file = create_temp_beancount_file()
    with open(root_file, "a") as f:
        f.write('''
2024-01-01 open Expenses:Media
  payees: "404 MEDIA"
2024-01-01 open Assets:Transfer:Costco
  payees: "Costco"
2024-01-01 open Expenses:Gas
  payees: "Costco Gas"
2024-01-01 open Assets:Transfer
  plaid_category: "TRANSFER_IN_ACCOUNT_TRANSFER, TRANSFER_OUT_ACCOUNT_TRANSFER"
''')
    try:
        transactions, _ = _update_transactions(DummyPlaidApiRules(), root_file, debug=True)
        accounts = [t.personal_finance_category.expense_account for t in transactions]
        assert accounts == ["Expenses:Media", "Expenses:Gas", "Assets:Transfer"]
    finally:
        shutil.rmtree(temp_dir)


class DummyPlaidApiSync:
    """Serves one sync page and records the cursor it was asked for."""

    def __init__(self, added=(), removed=()):
        self.added = list(added)
        self.removed = list(removed)
        self.cursors_seen = []

    def accounts_get(self, request):
        return {"accounts": [{"account_id": "acc_1", "type": "depository"}], "item": {}}

    def transactions_sync(self, request):
        self.cursors_seen.append(request.cursor)
        return {
            "added": self.added,
            "modified": [],
            "removed": self.removed,
            "has_more": False,
            "next_cursor": "next-cursor",
        }


SYNC_ROOT = """
2020-01-01 open Assets:Bank:Checking
  plaid_account_id: "acc_1"
  plaid_item_id: "item_1"
  plaid_access_token: "token"

2020-01-01 open Expenses:Food

2024-01-01 custom "plaid_cursor" "Assets:Bank:Checking" "stored-cursor" "item_1"
  plaid_transaction_id: "cursor_2024-01-01"
"""


def _sync_transaction(transaction_id, pending):
    return {
        "transaction_id": transaction_id,
        "account_id": "acc_1",
        "date": "2024-02-01",
        "name": "Cafe",
        "amount": 5.0,
        "pending": pending,
        "iso_currency_code": "USD",
        "personal_finance_category": None,
    }


def _write_root(directory, contents=SYNC_ROOT):
    root_file = os.path.join(directory, "root.beancount")
    with open(root_file, "w") as f:
        f.write(contents)
    return root_file


def test_stored_cursor_is_loaded_and_sent_to_plaid():
    with tempfile.TemporaryDirectory() as directory:
        root_file = _write_root(directory)
        cursors = _load_beancount_accounts(root_file)[3]
        assert cursors == {"Assets:Bank:Checking": {"item_1": "stored-cursor"}}

        client = DummyPlaidApiSync()
        _update_transactions(client, root_file)
        assert client.cursors_seen == ["stored-cursor"]


def test_pending_transactions_are_skipped_and_removed_ids_reported():
    with tempfile.TemporaryDirectory() as directory:
        root_file = _write_root(directory)
        client = DummyPlaidApiSync(
            added=[_sync_transaction("pending", True), _sync_transaction("posted", False)],
            removed=[{"transaction_id": "gone"}],
        )
        removed_ids = set()
        transactions, _ = _update_transactions(client, root_file, removed_ids=removed_ids)

    assert [t.transaction_id for t in transactions] == ["posted"]
    assert removed_ids == {"gone"}


def test_remove_transactions_only_deletes_unreviewed():
    ledger = SYNC_ROOT + """
2024-02-01 ! "Unreviewed" "x"
  plaid_transaction_id: "gone-1"
  Assets:Bank:Checking  -5.00 USD
  Expenses:Food          5.00 USD

2024-02-02 * "Reviewed" "x"
  plaid_transaction_id: "gone-2"
  Assets:Bank:Checking  -6.00 USD
  Expenses:Food          6.00 USD

2024-02-03 ! "Kept" "x"
  plaid_transaction_id: "kept"
  Assets:Bank:Checking  -7.00 USD
  Expenses:Food          7.00 USD
"""
    with tempfile.TemporaryDirectory() as directory:
        root_file = _write_root(directory, ledger)
        assert _remove_transactions_from_ledger(root_file, {"gone-1", "gone-2"}) == 1
        with open(root_file) as f:
            contents = f.read()

    assert "Unreviewed" not in contents
    assert "Reviewed" in contents
    assert "Kept" in contents


def test_cursor_stored_under_account_without_item_metadata_is_loaded():
    root = SYNC_ROOT.replace(
        '"Assets:Bank:Checking" "stored-cursor"', '"Assets:Bank:Savings" "stored-cursor"'
    ) + "\n2020-01-01 open Assets:Bank:Savings\n"
    with tempfile.TemporaryDirectory() as directory:
        root_file = _write_root(directory, root)
        client = DummyPlaidApiSync()
        _update_transactions(client, root_file)
    assert client.cursors_seen == ["stored-cursor"]
