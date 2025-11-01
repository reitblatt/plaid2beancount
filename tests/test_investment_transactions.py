import os
import sys
from decimal import Decimal
from datetime import date
from enum import Enum

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transactions import (
    PlaidInvestmentTransaction, PlaidSecurity, PlaidInvestmentTransactionType,
    Account, PlaidItem
)
from beancount_renderer import BeancountRenderer


class MockTransactionType(Enum):
    buy = 'buy'
    sell = 'sell'
    fee = 'fee'
    cash = 'cash'
    transfer = 'transfer'


class MockTransactionSubtype(Enum):
    dividend = 'dividend'
    interest = 'interest'
    miscellaneous_fee = 'miscellaneous fee'
    deposit = 'deposit'
    withdrawal = 'withdrawal'
    transfer = 'transfer'


def create_test_security(ticker="VTSAX"):
    """Create a test security object."""
    return PlaidSecurity(
        security_id="test_security_id",
        name="Vanguard Total Stock Market Index Fund",
        ticker_symbol=ticker,
        type="mutual fund",
        market_identifier_code="XNAS",
        is_cash_equivalent=False,
        isin="US9229087690",
        cusip="922908769"
    )


def create_test_account(beancount_name="Assets:Vanguard:Brokerage"):
    """Create a test account object."""
    item = PlaidItem(
        name="Vanguard",
        item_id="test_item_id",
        access_token="test_access_token",
        cursor="test_cursor"
    )
    return Account(
        name="Vanguard Brokerage",
        beancount_name=beancount_name,
        plaid_id="test_plaid_id",
        transaction_file="accounts/vanguard/brokerage.beancount",
        plaid_item=item,
        type=Account.AccountTypes.investment
    )


def create_test_transaction_type(type_value, subtype_value):
    """Create a test transaction type object."""
    class TestType:
        def __init__(self, val):
            self.value = val

    class TestTransactionType:
        def __init__(self, t, s):
            self.type = TestType(t)
            self.subtype = TestType(s)

    return TestTransactionType(type_value, subtype_value)


def test_dividend_fee_type():
    """Test dividend transaction with type=fee, subtype=dividend."""
    security = create_test_security("VTSAX")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 1, 15),
        name="VTSAX Dividend",
        quantity=Decimal("0"),
        price=Decimal("1.0"),
        amount=Decimal("50.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="div_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('fee', 'dividend'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    # Check that dividend account is Income:Vanguard:Brokerage:Dividends:VTSAX
    assert len(beancount_tx.postings) == 2
    dividend_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert dividend_posting.account == "Income:Vanguard:Brokerage:Dividends:VTSAX"
    assert dividend_posting.units.number == Decimal("50.00")
    assert dividend_posting.units.currency == "USD"

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-50.00")
    assert cash_posting.units.currency == "USD"


def test_dividend_cash_type():
    """Test dividend transaction with type=cash, subtype=dividend."""
    security = create_test_security("VTI")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 2, 20),
        name="VTI Dividend",
        quantity=Decimal("0"),
        price=Decimal("1.0"),
        amount=Decimal("125.50"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="div_002",
        iso_currency_code="USD",
        type=create_test_transaction_type('cash', 'dividend'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    # Check that dividend account is Income:Vanguard:Brokerage:Dividends:VTI
    assert len(beancount_tx.postings) == 2
    dividend_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert dividend_posting.account == "Income:Vanguard:Brokerage:Dividends:VTI"
    assert dividend_posting.units.number == Decimal("125.50")
    assert dividend_posting.units.currency == "USD"

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-125.50")
    assert cash_posting.units.currency == "USD"


def test_buy_transaction():
    """Test buy transaction."""
    security = create_test_security("AAPL")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 3, 10),
        name="Buy AAPL",
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        amount=Decimal("1500.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="buy_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('buy', 'buy'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    cash_posting = beancount_tx.postings[0]
    security_posting = beancount_tx.postings[1]

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-1500.00")
    assert cash_posting.units.currency == "USD"

    assert security_posting.account == "Assets:Vanguard:Brokerage:AAPL"
    assert security_posting.units.number == Decimal("10")
    assert security_posting.units.currency == "AAPL"
    assert security_posting.price.number == Decimal("150.00")
    assert security_posting.price.currency == "USD"


def test_sell_transaction():
    """Test sell transaction with capital gains posting."""
    security = create_test_security("GOOGL")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 4, 15),
        name="Sell GOOGL",
        quantity=Decimal("5"),
        price=Decimal("140.00"),
        amount=Decimal("700.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="sell_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('sell', 'sell'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    # Should have 3 postings: security, cash, and capital gains
    assert len(beancount_tx.postings) == 3
    security_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]
    gains_posting = beancount_tx.postings[2]

    assert security_posting.account == "Assets:Vanguard:Brokerage:GOOGL"
    assert security_posting.units.number == Decimal("-5")
    assert security_posting.units.currency == "GOOGL"

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("700.00")
    assert cash_posting.units.currency == "USD"

    assert gains_posting.account == "Income:Vanguard:BrokerageCapital-GainsGOOGL"
    assert gains_posting.units is None


def test_sweep_in():
    """Test sweep in transaction (cash -> money market fund)."""
    security = create_test_security("VMFXX")  # Money market fund
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 5, 1),
        name="Sweep in",
        quantity=Decimal("0"),  # Quantity may be 0
        price=Decimal("1.0"),
        amount=Decimal("1000.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="sweep_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('cash', 'withdrawal'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    cash_posting = beancount_tx.postings[0]
    security_posting = beancount_tx.postings[1]

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-1000.00")

    assert security_posting.account == "Assets:Vanguard:Brokerage:VMFXX"
    # When quantity is 0, use amount as quantity
    assert security_posting.units.number == Decimal("1000.00")
    assert security_posting.units.currency == "VMFXX"


def test_sweep_out():
    """Test sweep out transaction (money market fund -> cash)."""
    security = create_test_security("VMFXX")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 5, 15),
        name="Sweep out",
        quantity=Decimal("500.00"),
        price=Decimal("1.0"),
        amount=Decimal("500.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="sweep_002",
        iso_currency_code="USD",
        type=create_test_transaction_type('cash', 'deposit'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    security_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert security_posting.account == "Assets:Vanguard:Brokerage:VMFXX"
    assert security_posting.units.number == Decimal("500.00")

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-500.00")


def test_transfer_type_sweep():
    """Test sweep using transfer type (newer Vanguard behavior)."""
    security = create_test_security("VMFXX")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 6, 1),
        name="Sweep in",
        quantity=Decimal("0"),
        price=Decimal("1.0"),
        amount=Decimal("750.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="transfer_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('transfer', 'transfer'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    cash_posting = beancount_tx.postings[0]
    security_posting = beancount_tx.postings[1]

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-750.00")

    assert security_posting.account == "Assets:Vanguard:Brokerage:VMFXX"
    assert security_posting.units.number == Decimal("750.00")


def test_multiple_dividend_tickers():
    """Test that dividends from different securities have different accounts."""
    tickers = ["VTSAX", "VTIAX", "VBTLX"]
    transactions = []

    for ticker in tickers:
        security = create_test_security(ticker)
        account = create_test_account()

        transaction = PlaidInvestmentTransaction(
            date=date(2024, 7, 1),
            name=f"{ticker} Dividend",
            quantity=Decimal("0"),
            price=Decimal("1.0"),
            amount=Decimal("100.00"),
            security=security,
            fees=Decimal("0"),
            cancel_transaction_id=None,
            investment_transaction_id=f"div_{ticker}",
            iso_currency_code="USD",
            type=create_test_transaction_type('fee', 'dividend'),
            account=account
        )
        transactions.append(transaction)

    renderer = BeancountRenderer([], transactions)

    for i, ticker in enumerate(tickers):
        beancount_tx = renderer._to_investment_beancount(transactions[i])
        dividend_posting = beancount_tx.postings[0]

        expected_account = f"Income:Vanguard:Brokerage:Dividends:{ticker}"
        assert dividend_posting.account == expected_account, \
            f"Expected {expected_account}, got {dividend_posting.account}"


def test_multiple_account_structures():
    """Test that dividend accounts work with different account structures."""
    test_cases = [
        ("Assets:Investments:Vanguard", "Income:Investments:Vanguard:Dividends:VTSAX"),
        ("Assets:Brokerage:Fidelity:401k", "Income:Brokerage:Fidelity:401k:Dividends:VTSAX"),
        ("Assets:Retirement:IRA", "Income:Retirement:IRA:Dividends:VTSAX"),
    ]

    for account_name, expected_dividend_account in test_cases:
        security = create_test_security("VTSAX")
        account = create_test_account(account_name)

        transaction = PlaidInvestmentTransaction(
            date=date(2024, 8, 1),
            name="Dividend",
            quantity=Decimal("0"),
            price=Decimal("1.0"),
            amount=Decimal("50.00"),
            security=security,
            fees=Decimal("0"),
            cancel_transaction_id=None,
            investment_transaction_id="div_test",
            iso_currency_code="USD",
            type=create_test_transaction_type('fee', 'dividend'),
            account=account
        )

        renderer = BeancountRenderer([], [transaction])
        beancount_tx = renderer._to_investment_beancount(transaction)
        dividend_posting = beancount_tx.postings[0]

        assert dividend_posting.account == expected_dividend_account, \
            f"For account {account_name}, expected {expected_dividend_account}, got {dividend_posting.account}"
