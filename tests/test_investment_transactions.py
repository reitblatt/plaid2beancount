import os
import sys
from decimal import Decimal
from datetime import date
from enum import Enum

# Add the project root to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Import the standalone transaction models (from transaction_models.py in root)
from transaction_models import (
    PlaidInvestmentTransaction,
    PlaidSecurity,
    PlaidInvestmentTransactionType,
    Account,
    PlaidItem
)

# Import from the transactions package
from transactions.beancount_renderer import BeancountRenderer


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


VANGUARD_INSTITUTION_ID = "ins_116527"


def create_test_account(beancount_name="Assets:Vanguard:Brokerage", institution_id=None):
    """Create a test account object."""
    item = PlaidItem(
        name="Vanguard",
        item_id="test_item_id",
        access_token="test_access_token",
        cursor="test_cursor",
        institution_id=institution_id,
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

    # Check that dividend account is Income:Vanguard:Brokerage:VTSAX:Dividends
    assert len(beancount_tx.postings) == 2
    dividend_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert dividend_posting.account == "Income:Vanguard:Brokerage:VTSAX:Dividends"
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

    # Check that dividend account is Income:Vanguard:Brokerage:VTI:Dividends
    assert len(beancount_tx.postings) == 2
    dividend_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert dividend_posting.account == "Income:Vanguard:Brokerage:VTI:Dividends"
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
    account = create_test_account(institution_id=VANGUARD_INSTITUTION_ID)

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
    account = create_test_account(institution_id=VANGUARD_INSTITUTION_ID)

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
    account = create_test_account(institution_id=VANGUARD_INSTITUTION_ID)

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


def test_cash_contribution():
    """Test cash/contribution (e.g. 401k contribution) routes Assets:Transfer to Cash."""
    security = create_test_security("VMFXX")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2026, 4, 2),
        name="Contribution",
        quantity=Decimal("0"),
        price=Decimal("1.0"),
        amount=Decimal("-4011.11"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="contribution_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('cash', 'contribution'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    transfer_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert transfer_posting.account == "Assets:Transfer"
    assert transfer_posting.units.number == Decimal("4011.11")
    assert transfer_posting.units.currency == "USD"

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-4011.11")
    assert cash_posting.units.currency == "USD"


def test_transfer_outgoing():
    """Test transfer/transfer outgoing (e.g. 'Transfer (Outgoing)') routes cash to Assets:Transfer."""
    security = create_test_security("VMFXX")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2026, 4, 2),
        name="Transfer (Outgoing)",
        quantity=Decimal("0"),
        price=Decimal("1.0"),
        amount=Decimal("4011.11"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="transfer_out_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('transfer', 'transfer'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    cash_posting = beancount_tx.postings[0]
    transfer_posting = beancount_tx.postings[1]

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-4011.11")
    assert cash_posting.units.currency == "USD"

    assert transfer_posting.account == "Assets:Transfer"
    assert transfer_posting.units.number == Decimal("4011.11")
    assert transfer_posting.units.currency == "USD"


def test_transfer_incoming():
    """Test transfer/transfer incoming routes Assets:Transfer to cash."""
    security = create_test_security("VMFXX")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2026, 4, 2),
        name="Transfer (Incoming)",
        quantity=Decimal("0"),
        price=Decimal("1.0"),
        amount=Decimal("-2000.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="transfer_in_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('transfer', 'transfer'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    transfer_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert transfer_posting.account == "Assets:Transfer"
    assert transfer_posting.units.number == Decimal("2000.00")
    assert transfer_posting.units.currency == "USD"

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-2000.00")
    assert cash_posting.units.currency == "USD"


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

        expected_account = f"Income:Vanguard:Brokerage:{ticker}:Dividends"
        assert dividend_posting.account == expected_account, \
            f"Expected {expected_account}, got {dividend_posting.account}"


def test_multiple_account_structures():
    """Test that dividend accounts work with different account structures."""
    test_cases = [
        ("Assets:Investments:Vanguard", "Income:Investments:Vanguard:VTSAX:Dividends"),
        ("Assets:Brokerage:Fidelity:401k", "Income:Brokerage:Fidelity:401k:VTSAX:Dividends"),
        ("Assets:Retirement:IRA", "Income:Retirement:IRA:VTSAX:Dividends"),
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


def test_fee_miscellaneous():
    """Test fee/miscellaneous fee is rendered like a buy (cash -> security)."""
    security = create_test_security("AAPL")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 9, 1),
        name="Miscellaneous Fee",
        quantity=Decimal("1"),
        price=Decimal("150.00"),
        amount=Decimal("150.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="fee_misc_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('fee', 'miscellaneous fee'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    cash_posting = beancount_tx.postings[0]
    security_posting = beancount_tx.postings[1]

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-150.00")
    assert cash_posting.units.currency == "USD"

    assert security_posting.account == "Assets:Vanguard:Brokerage:AAPL"
    assert security_posting.units.number == Decimal("1")
    assert security_posting.units.currency == "AAPL"
    assert security_posting.price.number == Decimal("150.00")


def test_sweep_out_fee_interest():
    """Test Vanguard fee/interest is rendered as sweep out (money market -> cash)."""
    security = create_test_security("VMFXX")
    account = create_test_account(institution_id=VANGUARD_INSTITUTION_ID)

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 9, 15),
        name="Interest",
        quantity=Decimal("200.00"),
        price=Decimal("1.0"),
        amount=Decimal("200.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="fee_interest_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('fee', 'interest'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    security_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert security_posting.account == "Assets:Vanguard:Brokerage:VMFXX"
    assert security_posting.units.number == Decimal("200.00")
    assert security_posting.units.currency == "VMFXX"

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-200.00")
    assert cash_posting.units.currency == "USD"


def test_cash_deposit_transfer_in():
    """Test cash/deposit non-sweep renders as external transfer in (positive amount)."""
    security = create_test_security("VMFXX")
    account = create_test_account()

    transaction = PlaidInvestmentTransaction(
        date=date(2024, 10, 1),
        name="Wire Transfer",
        quantity=Decimal("0"),
        price=Decimal("1.0"),
        amount=Decimal("5000.00"),
        security=security,
        fees=Decimal("0"),
        cancel_transaction_id=None,
        investment_transaction_id="deposit_001",
        iso_currency_code="USD",
        type=create_test_transaction_type('cash', 'deposit'),
        account=account
    )

    renderer = BeancountRenderer([], [transaction])
    beancount_tx = renderer._to_investment_beancount(transaction)

    assert len(beancount_tx.postings) == 2
    transfer_posting = beancount_tx.postings[0]
    cash_posting = beancount_tx.postings[1]

    assert transfer_posting.account == "Assets:Transfer"
    assert transfer_posting.units.number == Decimal("5000.00")
    assert transfer_posting.units.currency == "USD"

    assert cash_posting.account == "Assets:Vanguard:Brokerage:Cash"
    assert cash_posting.units.number == Decimal("-5000.00")
    assert cash_posting.units.currency == "USD"


# ---------------------------------------------------------------------------
# Institution classifier unit tests
# ---------------------------------------------------------------------------

from transactions.institutions.base import Institution, InvestmentKind
from transactions.institutions.vanguard import VanguardInstitution
from transactions.institutions.registry import get_institution, INSTITUTION_REGISTRY


def make_tx(type_val, subtype_val, name="", amount=Decimal("100.00")):
    """Minimal transaction stub for classifier tests."""
    class _V:
        def __init__(self, v):
            self.value = v
    class _Type:
        def __init__(self, t, s):
            self.type = _V(t)
            self.subtype = _V(s)
    class _Tx:
        pass
    tx = _Tx()
    tx.type = _Type(type_val, subtype_val)
    tx.name = name
    tx.amount = amount
    return tx


class TestBaseInstitution:
    inst = Institution()

    def test_buy(self):
        assert self.inst.classify(make_tx('buy', 'buy')) == InvestmentKind.BUY

    def test_sell(self):
        assert self.inst.classify(make_tx('sell', 'sell')) == InvestmentKind.SELL

    def test_fee_dividend(self):
        assert self.inst.classify(make_tx('fee', 'dividend')) == InvestmentKind.DIVIDEND

    def test_fee_miscellaneous(self):
        assert self.inst.classify(make_tx('fee', 'miscellaneous fee')) == InvestmentKind.FEE

    def test_cash_dividend(self):
        assert self.inst.classify(make_tx('cash', 'dividend')) == InvestmentKind.DIVIDEND

    def test_cash_deposit(self):
        assert self.inst.classify(make_tx('cash', 'deposit')) == InvestmentKind.TRANSFER_IN

    def test_cash_withdrawal(self):
        assert self.inst.classify(make_tx('cash', 'withdrawal')) == InvestmentKind.TRANSFER_OUT

    def test_cash_contribution(self):
        assert self.inst.classify(make_tx('cash', 'contribution')) == InvestmentKind.TRANSFER_IN

    def test_transfer_outgoing(self):
        assert self.inst.classify(make_tx('transfer', 'transfer', amount=Decimal("100"))) == InvestmentKind.TRANSFER_OUT

    def test_transfer_incoming(self):
        assert self.inst.classify(make_tx('transfer', 'transfer', amount=Decimal("-100"))) == InvestmentKind.TRANSFER_IN

    def test_unknown_raises(self):
        import pytest
        with pytest.raises(ValueError):
            self.inst.classify(make_tx('unknown', 'unknown'))


class TestVanguardInstitution:
    inst = VanguardInstitution()

    def test_cash_deposit_sweep_out(self):
        assert self.inst.classify(make_tx('cash', 'deposit', name='Sweep out')) == InvestmentKind.SWEEP_OUT

    def test_cash_deposit_non_sweep(self):
        assert self.inst.classify(make_tx('cash', 'deposit', name='Wire Transfer')) == InvestmentKind.TRANSFER_IN

    def test_cash_withdrawal_sweep_in(self):
        assert self.inst.classify(make_tx('cash', 'withdrawal', name='Sweep in')) == InvestmentKind.SWEEP_IN

    def test_cash_withdrawal_non_sweep(self):
        assert self.inst.classify(make_tx('cash', 'withdrawal', name='ACH Transfer')) == InvestmentKind.TRANSFER_OUT

    def test_fee_interest_is_sweep_out(self):
        assert self.inst.classify(make_tx('fee', 'interest')) == InvestmentKind.SWEEP_OUT

    def test_transfer_transfer_sweep_in(self):
        assert self.inst.classify(make_tx('transfer', 'transfer', name='Sweep in')) == InvestmentKind.SWEEP_IN

    def test_transfer_transfer_sweep_out(self):
        assert self.inst.classify(make_tx('transfer', 'transfer', name='Sweep out')) == InvestmentKind.SWEEP_OUT

    def test_transfer_transfer_outgoing(self):
        assert self.inst.classify(make_tx('transfer', 'transfer', name='Transfer (Outgoing)', amount=Decimal("100"))) == InvestmentKind.TRANSFER_OUT

    def test_delegates_buy_to_base(self):
        assert self.inst.classify(make_tx('buy', 'buy')) == InvestmentKind.BUY

    def test_delegates_sell_to_base(self):
        assert self.inst.classify(make_tx('sell', 'sell')) == InvestmentKind.SELL


class TestRegistry:
    def test_vanguard_id_returns_vanguard(self):
        assert isinstance(get_institution("ins_116527"), VanguardInstitution)

    def test_unknown_id_returns_base(self):
        assert type(get_institution("ins_unknown")) is Institution

    def test_none_returns_base(self):
        assert type(get_institution(None)) is Institution

    def test_registry_contains_vanguard(self):
        assert "ins_116527" in INSTITUTION_REGISTRY


# ---------------------------------------------------------------------------
# store_institution_id_in_beancount tests
# ---------------------------------------------------------------------------

import tempfile
import textwrap
from beancount_file_utils import store_institution_id_in_beancount


def _write_temp_beancount(content):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.beancount', delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


class TestStoreInstitutionId:
    def test_adds_institution_id(self):
        path = _write_temp_beancount("""\
            2020-01-01 open Assets:Vanguard:Brokerage
              plaid_account_id: "acc123"
              plaid_item_id: "item_xyz"
              plaid_access_token: "access-token"
        """)
        store_institution_id_in_beancount(path, "item_xyz", "ins_116527")
        content = open(path).read()
        assert 'plaid_institution_id: "ins_116527"' in content

    def test_idempotent_when_already_present(self):
        path = _write_temp_beancount("""\
            2020-01-01 open Assets:Vanguard:Brokerage
              plaid_item_id: "item_xyz"
              plaid_institution_id: "ins_116527"
              plaid_access_token: "access-token"
        """)
        store_institution_id_in_beancount(path, "item_xyz", "ins_116527")
        content = open(path).read()
        assert content.count('plaid_institution_id:') == 1

    def test_only_updates_matching_item(self):
        path = _write_temp_beancount("""\
            2020-01-01 open Assets:Vanguard:Brokerage
              plaid_item_id: "item_xyz"
              plaid_access_token: "access-vanguard"

            2020-01-01 open Assets:Chase:Checking
              plaid_item_id: "item_abc"
              plaid_access_token: "access-chase"
        """)
        store_institution_id_in_beancount(path, "item_xyz", "ins_116527")
        content = open(path).read()
        # institution_id appears only once (under item_xyz, not item_abc)
        assert content.count('plaid_institution_id: "ins_116527"') == 1
        assert 'item_abc' in content
        lines = content.splitlines()
        institution_line = next(i for i, l in enumerate(lines) if 'plaid_institution_id' in l)
        # The line before should be the item_xyz plaid_item_id line
        assert 'item_xyz' in lines[institution_line - 1]

    def test_updates_all_accounts_for_item(self):
        path = _write_temp_beancount("""\
            2020-01-01 open Assets:Vanguard:Brokerage
              plaid_item_id: "item_xyz"
              plaid_access_token: "access-a"

            2020-01-01 open Assets:Vanguard:IRA
              plaid_item_id: "item_xyz"
              plaid_access_token: "access-b"
        """)
        store_institution_id_in_beancount(path, "item_xyz", "ins_116527")
        content = open(path).read()
        assert content.count('plaid_institution_id: "ins_116527"') == 2
