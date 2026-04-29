from decimal import Decimal
from typing import List
import sys
import os
# Import from parent directory's transaction_models.py module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from transaction_models import PlaidTransaction, PlaidInvestmentTransaction
from beancount.core.data import Transaction, Amount, Posting, Price, Balance, CostSpec
from beancount.parser.printer import EntryPrinter
import logging

from transactions.institutions.base import InvestmentKind
from transactions.institutions.registry import get_institution

logger = logging.getLogger(__name__)

_TWO_PLACES = Decimal('0.01')

def _usd(value: Decimal) -> Decimal:
    """Ensure a USD total amount has at least 2 decimal places."""
    if value.as_tuple().exponent > -2:
        return value.quantize(_TWO_PLACES)
    return value


class BeancountRenderer:
    def __init__(self, transactions: List[PlaidTransaction], investment_transactions: List[PlaidInvestmentTransaction]):
        self.transactions = transactions
        self.investment_transactions = investment_transactions
        self._printer = EntryPrinter()

    def print(self) -> List[str]:
        """Convert transactions to Beancount format and print them."""
        beancount_transactions = []
        for transaction in self.transactions:
            beancount_transactions.append(self._to_beancount(transaction))
        for transaction in self.investment_transactions:
            beancount_transactions.append(self._to_investment_beancount(transaction))
        return [self._printer(transaction) for transaction in beancount_transactions]

    def _to_beancount(self, transaction: PlaidTransaction) -> Transaction:
        if transaction.personal_finance_category and transaction.personal_finance_category.expense_account:
            expense_account = transaction.personal_finance_category.expense_account
        else:
            expense_account = "Expenses:Unknown"

        if transaction.account and transaction.account.beancount_name:
            account = transaction.account.beancount_name
        else:
            account = "Unknown"

        return Transaction(
            meta={
                "plaid_transaction_id": transaction.transaction_id,
                "plaid_category_detailed": transaction.personal_finance_category.detailed if transaction.personal_finance_category else None
            },
            date=transaction.date,
            payee=transaction.merchant_name or transaction.name,
            narration=transaction.name,
            flag="!",
            tags=set(),
            links=set(),
            postings=[
                Posting(
                    account, Amount(_usd(-transaction.amount), transaction.currency), None, None, None, None
                ),
                Posting(
                    expense_account,
                    Amount(_usd(transaction.amount), transaction.currency),
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )

    def _to_investment_beancount(self, transaction: PlaidInvestmentTransaction) -> Transaction:
        """Convert a PlaidInvestmentTransaction to a Beancount Transaction."""
        if transaction.account.beancount_name is not None:
            account = transaction.account.beancount_name
        else:
            account = "Unknown"

        ticker = transaction.security.ticker_symbol

        institution = get_institution(transaction.account.item.institution_id)
        kind = institution.classify(transaction)

        gains_account = None

        if kind in (InvestmentKind.BUY, InvestmentKind.FEE, InvestmentKind.SWEEP_IN):
            # Cash leaves the account and buys a security (or sweeps into money market).
            source_posting = Posting(
                account + ":Cash", Amount(_usd(-transaction.amount), "USD"), None, None, None, None
            )
            quantity = transaction.quantity or transaction.amount
            price = transaction.price or Decimal('1.0')
            sink_posting = Posting(
                account + ":" + ticker, Amount(quantity, ticker), None, Amount(price, "USD"), None, None
            )

        elif kind == InvestmentKind.SELL:
            source_posting = Posting(
                account + ":" + ticker, Amount(-transaction.quantity, ticker), None, Amount(transaction.price, "USD"), None, None
            )
            sink_posting = Posting(
                account + ":Cash", Amount(_usd(transaction.amount), "USD"), None, None, None, None
            )
            gains_account = account.replace("Assets", "Income") + "Capital-Gains" + ticker

        elif kind == InvestmentKind.DIVIDEND:
            source_posting = Posting(
                account.replace("Assets", "Income") + ":" + ticker + ":Dividends",
                Amount(_usd(transaction.amount), "USD"), None, None, None, None
            )
            sink_posting = Posting(
                account + ":Cash", Amount(_usd(-transaction.amount), "USD"), None, None, None, None
            )

        elif kind == InvestmentKind.SWEEP_OUT:
            # Money market fund converts back to cash.
            source_posting = Posting(
                account + ":" + ticker, Amount(transaction.amount, ticker), None, Amount(transaction.price, "USD"), None, None
            )
            sink_posting = Posting(
                account + ":Cash", Amount(_usd(-transaction.amount), "USD"), None, None, None, None
            )

        elif kind == InvestmentKind.TRANSFER_IN:
            # External cash arriving. Plaid uses positive amounts for cash/deposit and
            # negative amounts for contributions and transfer/transfer incoming, so
            # normalise with abs() so the beancount entry always reads the same way.
            abs_amount = abs(transaction.amount)
            source_posting = Posting(
                "Assets:Transfer", Amount(_usd(abs_amount), "USD"), None, None, None, None
            )
            sink_posting = Posting(
                account + ":Cash", Amount(_usd(-abs_amount), "USD"), None, None, None, None
            )

        elif kind == InvestmentKind.TRANSFER_OUT:
            abs_amount = abs(transaction.amount)
            source_posting = Posting(
                account + ":Cash", Amount(_usd(-abs_amount), "USD"), None, None, None, None
            )
            sink_posting = Posting(
                "Assets:Transfer", Amount(_usd(abs_amount), "USD"), None, None, None, None
            )

        else:
            raise ValueError(f"Unhandled InvestmentKind: {kind}")

        postings = [source_posting, sink_posting]
        if gains_account is not None:
            postings.append(Posting(gains_account, None, None, None, None, None))

        return Transaction(
            meta={"plaid_transaction_id": transaction.investment_transaction_id},
            date=transaction.date,
            payee=ticker,
            narration=transaction.name,
            flag="!",
            tags=set(),
            links=set(),
            postings=postings,
        )
