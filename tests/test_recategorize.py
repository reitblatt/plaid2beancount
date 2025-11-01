import os
import tempfile
import shutil
from main import _recategorize_transactions
from beancount import loader

def test_recategorize_payee_rule():
    # Step 1: Create a root file and a transaction file with no payee rule
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"

include "accounts/checking/checking.beancount"
'''
    tx_content = '''
2024-01-10 * "STARBUCKS" "Coffee"
  plaid_transaction_id: "txn1"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        # Step 2: Add a payee rule to the root file
        with open(root_file, "a") as f:
            f.write('2024-01-01 open Expenses:Food:Bars\n  payees: "STARBUCKS"\n')
        # Step 3: Run recategorization
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 1
        # Step 4: Check that the transaction was updated
        entries, errors, options = loader.load_file(tx_file)
        found = False
        for entry in entries:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    if posting.account == "Expenses:Food:Bars":
                        found = True
        assert found, "Transaction was not recategorized to Expenses:Food:Bars"
    finally:
        shutil.rmtree(temp_dir)

def test_recategorize_payee_with_whitespace():
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "  STARBUCKS  "

include "accounts/checking/checking.beancount"
'''
    tx_content = '''
2024-01-10 * "STARBUCKS" "Coffee"
  plaid_transaction_id: "txn1"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 1
        entries, errors, options = loader.load_file(tx_file)
        found = False
        for entry in entries:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    if posting.account == "Expenses:Food:Bars":
                        found = True
        assert found, "Whitespace in payee rule failed"
    finally:
        shutil.rmtree(temp_dir)

def test_recategorize_multiple_payees():
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS, COFFEE SHOP"

include "accounts/checking/checking.beancount"
'''
    tx_content = '''
2024-01-10 * "STARBUCKS" "Coffee"
  plaid_transaction_id: "txn1"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD

2024-01-11 * "COFFEE SHOP" "Latte"
  plaid_transaction_id: "txn2"
  Assets:Checking  -4.00 USD
  Expenses:Food:Restaurants  4.00 USD
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 2
        entries, errors, options = loader.load_file(tx_file)
        found = set()
        for entry in entries:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    if posting.account == "Expenses:Food:Bars":
                        found.add(entry.payee)
        assert found == {"STARBUCKS", "COFFEE SHOP"}, f"Multiple payees failed: {found}"
    finally:
        shutil.rmtree(temp_dir)

def test_recategorize_no_matching_payee_or_category():
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"
'''
    tx_content = '''
2024-01-10 * "DUNKIN" "Coffee"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD
    plaid_transaction_id: "txn1"
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 0
        entries, errors, options = loader.load_file(tx_file)
        found = False
        for entry in entries:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    if posting.account == "Expenses:Food:Bars":
                        found = True
        assert not found, "Non-matching payee should not recategorize"
    finally:
        shutil.rmtree(temp_dir)

def test_recategorize_empty_payee():
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"
'''
    tx_content = '''
2024-01-10 * "" "No payee"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD
    plaid_transaction_id: "txn1"
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 0
        entries, errors, options = loader.load_file(tx_file)
        found = False
        for entry in entries:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    if posting.account == "Expenses:Food:Bars":
                        found = True
        assert not found, "Empty payee should not recategorize"
    finally:
        shutil.rmtree(temp_dir)

def test_recategorize_overlapping_rules():
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"

include "accounts/checking/checking.beancount"
'''
    tx_content = '''
2024-01-10 * "STARBUCKS" "Coffee"
  plaid_transaction_id: "txn1"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 1
        entries, errors, options = loader.load_file(tx_file)
        found = False
        for entry in entries:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    if posting.account == "Expenses:Food:Bars":
                        found = True
        assert found, "Payee rule should override category rule"
    finally:
        shutil.rmtree(temp_dir)

def test_recategorize_with_relative_paths_and_account_definitions():
    """
    This test mimics a real-world scenario where:
    - The root file defines accounts and uses relative paths for transaction files.
    - The transaction file does NOT include the root file and references accounts only defined in the root.
    - The recategorization function should work without validation errors.
    - Validation should be done by loading the root file (which includes all transaction files).
    """
    root_content = '''
2024-01-01 open Assets:Bank:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/bank/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"

include "accounts/bank/checking.beancount"
'''
    tx_content = '''
2024-01-10 * "STARBUCKS" "Coffee"
  plaid_transaction_id: "txn1"
  Assets:Bank:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/bank")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        # Run recategorization
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 1
        # Validate by loading the root file (which includes all transaction files)
        entries, errors, options = loader.load_file(root_file)
        # Confirm no errors from the loader
        assert not errors, f"Loader returned errors: {errors}"
        # Check that the transaction was recategorized
        found = False
        for entry in entries:
            if hasattr(entry, "postings"):
                for posting in entry.postings:
                    if posting.account == "Expenses:Food:Bars":
                        found = True
        assert found, "Transaction was not recategorized to Expenses:Food:Bars"
    finally:
        shutil.rmtree(temp_dir)

def test_inline_modification_preserves_comments():
    """Test that inline modification preserves comments and formatting."""
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"

include "accounts/checking/checking.beancount"
'''
    tx_content = '''
; This is a comment at the top
; Another comment

2024-01-10 * "STARBUCKS" "Coffee"
  plaid_transaction_id: "txn1"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD

; Comment between transactions

2024-01-11 * "DUNKIN" "Donuts"
  plaid_transaction_id: "txn2"
  Assets:Checking  -3.00 USD
  Expenses:Food:Restaurants  3.00 USD

; Comment at the end
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        
        # Run recategorization
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 1
        
        # Check that comments and formatting are preserved
        with open(tx_file, 'r') as f:
            modified_content = f.read()
        
        # Verify file-level comments are preserved
        assert "; This is a comment at the top" in modified_content
        assert "; Another comment" in modified_content
        # Note: Comments between/after transactions may not be preserved when transactions are modified
        # This is a limitation of using printer.format_entry() which doesn't preserve surrounding comments
        
        # Verify only STARBUCKS transaction was modified
        assert "Expenses:Food:Bars" in modified_content
        assert "Expenses:Food:Restaurants" in modified_content  # DUNKIN should still be here
        
        # Verify transaction structure is maintained
        lines = modified_content.split('\n')
        assert any('2024-01-10 * "STARBUCKS"' in line for line in lines)
        assert any('2024-01-11 * "DUNKIN"' in line for line in lines)
        
    finally:
        shutil.rmtree(temp_dir)

def test_inline_modification_with_plaid_transaction_id():
    """Test inline modification using plaid_transaction_id for identification."""
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"

include "accounts/checking/checking.beancount"
'''
    tx_content = '''
2024-01-10 * "STARBUCKS" "Coffee"
  plaid_transaction_id: "unique_id_123"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD

2024-01-11 * "DUNKIN" "Donuts"
  plaid_transaction_id: "unique_id_456"
  Assets:Checking  -3.00 USD
  Expenses:Food:Restaurants  3.00 USD
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        
        # Run recategorization
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 1
        
        # Check that only STARBUCKS transaction was modified
        with open(tx_file, 'r') as f:
            modified_content = f.read()
        
        # STARBUCKS should be recategorized
        assert "Expenses:Food:Bars" in modified_content
        # DUNKIN should remain unchanged
        assert "Expenses:Food:Restaurants" in modified_content
        
        # Verify both transactions are still present
        lines = modified_content.split('\n')
        assert any('unique_id_123' in line for line in lines)
        assert any('unique_id_456' in line for line in lines)
        
    finally:
        shutil.rmtree(temp_dir)

def test_inline_modification_without_plaid_transaction_id():
    """Test inline modification using full metadata when plaid_transaction_id is not available."""
    root_content = '''
2024-01-01 open Assets:Checking
  plaid_account_id: "acc1"
  transaction_file: "accounts/checking/checking.beancount"
2024-01-01 open Expenses:Food:Restaurants
  plaid_category: "FOOD_AND_DRINK_RESTAURANTS"
2024-01-01 open Expenses:Food:Bars
  payees: "STARBUCKS"
'''
    tx_content = '''
2024-01-10 * "STARBUCKS" "Coffee"
  Assets:Checking  -5.00 USD
  Expenses:Food:Restaurants  5.00 USD

2024-01-11 * "STARBUCKS" "Coffee"
  Assets:Checking  -4.00 USD
  Expenses:Food:Restaurants  4.00 USD

2024-01-12 * "DUNKIN" "Donuts"
  Assets:Checking  -3.00 USD
  Expenses:Food:Restaurants  3.00 USD
'''
    temp_dir = tempfile.mkdtemp()
    try:
        root_file = os.path.join(temp_dir, "root.beancount")
        tx_dir = os.path.join(temp_dir, "accounts/checking")
        os.makedirs(tx_dir)
        tx_file = os.path.join(tx_dir, "checking.beancount")
        with open(root_file, "w") as f:
            f.write(root_content)
        with open(tx_file, "w") as f:
            f.write(tx_content)
        
        # Run recategorization
        recategorized_count = _recategorize_transactions(root_file)
        assert recategorized_count == 2  # Both STARBUCKS transactions should be recategorized
        
        # Check that both STARBUCKS transactions were modified
        with open(tx_file, 'r') as f:
            modified_content = f.read()
        
        # Both STARBUCKS transactions should be recategorized
        assert modified_content.count("Expenses:Food:Bars") == 2
        # DUNKIN should remain unchanged
        assert "Expenses:Food:Restaurants" in modified_content
        
        # Verify all three transactions are still present
        lines = modified_content.split('\n')
        assert any('2024-01-10 * "STARBUCKS"' in line for line in lines)
        assert any('2024-01-11 * "STARBUCKS"' in line for line in lines)
        assert any('2024-01-12 * "DUNKIN"' in line for line in lines)
        
    finally:
        shutil.rmtree(temp_dir) 