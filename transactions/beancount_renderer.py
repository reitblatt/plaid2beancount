from decimal import Decimal
from typing import List
from models import PlaidTransaction, PlaidInvestmentTransaction
from beancount.core.data import Transaction, Amount, Posting, Price, Balance, CostSpec
from beancount.parser.printer import EntryPrinter
import logging

logger = logging.getLogger(__name__)


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
                    account, Amount(-transaction.amount, transaction.currency), None, None, None, None
                ),
                Posting(
                    expense_account,
                    Amount(transaction.amount, transaction.currency),
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )
        
    def _to_investment_beancount(self, transaction: PlaidInvestmentTransaction) -> Transaction:                        
        """Convert a PlaidInvestmentTransaction to a Beancount Transaction."""
        # Get the account name
        account = transaction.account.beancount_name
        logger.debug(f"Processing transaction: {transaction.type.type} - {transaction.type.subtype} - {transaction.date} - {transaction.amount} - {transaction.security.ticker_symbol}")
        meta = {"plaid_transaction_id": transaction.investment_transaction_id}
        transaction_common_info = {
            'meta': meta,
            'date': transaction.date,
            'payee': transaction.security.ticker_symbol,
            'flag': "!",
            'narration': transaction.name,
            'tags': set(),
            'links': set(),
        }
        
        # Create the transaction
        transaction_type = transaction.type.type.value
        transaction_subtype = transaction.type.subtype.value
        if transaction_type == "buy":
            if transaction_subtype == "buy":
                # Regular buy
                logger.debug("Processing buy - buy transaction")
                return Transaction(                                        
                    postings=[
                        Posting(
                            account=account,
                            units=Amount(transaction.quantity, transaction.security.ticker_symbol if transaction.security.ticker_symbol else transaction.security.name),
                            cost=CostSpec(transaction.price, None, None, None, None, None),
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                        Posting(
                            account=account + ":Cash",
                            units=Amount(-transaction.amount if transaction.amount > 0 else transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                    **transaction_common_info
                )
            elif transaction_subtype == "contribution":
                # Contribution
                logger.debug("Processing buy - contribution transaction")
                return Transaction(                                                          
                    postings=[
                        Posting(
                            account=account + ":Cash",
                            units=Amount(-transaction.amount if transaction.amount > 0 else transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                        Posting(
                            account="Assets:Transfer",
                            units=Amount(transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                    **transaction_common_info
                )
        elif transaction_type == "cash":
            if transaction_subtype == "dividend":
                # Dividend
                logger.debug("Processing cash - dividend transaction")
                return Transaction(                                                        
                    postings=[
                        Posting(
                            account=account + ":Cash",
                            units=Amount(transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                        Posting(
                            account="Income:Dividends",
                            units=Amount(-transaction.amount if transaction.amount > 0 else transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                    **transaction_common_info
                )
            elif transaction_subtype == "deposit":
                # Deposit
                logger.debug("Processing cash - deposit transaction")
                return Transaction(                                        
                    postings=[
                        Posting(
                            account=account + ":Cash",
                            units=Amount(transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                        Posting(
                            account="Assets:Transfer",
                            units=Amount(-transaction.amount if transaction.amount > 0 else transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                    **transaction_common_info
                )
            elif transaction_subtype == "withdrawal":
                # Withdrawal
                logger.debug("Processing cash - withdrawal transaction")
                return Transaction(
                    postings=[
                        Posting(
                            account=account + ":Cash",
                            units=Amount(-transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                        Posting(
                            account="Assets:Transfer",
                            units=Amount(transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                    **transaction_common_info
                )
        else:
            logger.error(f"Unknown transaction type: {transaction.type.type} - {transaction.type.subtype}")
            raise ValueError(f"Unknown transaction type: {transaction.type.type} - {transaction.type.subtype}")

        
