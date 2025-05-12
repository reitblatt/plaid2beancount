from decimal import Decimal
from typing import List
from models import PlaidTransaction, PlaidInvestmentTransaction
from beancount.core.data import Transaction, Amount, Posting, Price, Balance, CostSpec
from beancount.parser.printer import EntryPrinter


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
        print(f"Processing transaction: {transaction.type.type} - {transaction.type.subtype} - {transaction.date} - {transaction.amount}")

        # Create the transaction
        if transaction.type.type == "buy":
            if transaction.type.subtype == "buy":
                # Regular buy
                print("Processing buy - buy transaction")
                return Transaction(
                    meta=None,
                    date=transaction.date,
                    flag="*",
                    payee=transaction.name,
                    narration="",
                    tags=set(),
                    links=set(),
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
                )
            elif transaction.type.subtype == "contribution":
                # Contribution
                print("Processing buy - contribution transaction")
                return Transaction(
                    meta=None,
                    date=transaction.date,
                    flag="*",
                    payee=transaction.name,
                    narration="",
                    tags=set(),
                    links=set(),
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
                            account="Assets:Checking",
                            units=Amount(transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                )
        elif transaction.type.type == "cash":
            if transaction.type.subtype == "dividend":
                # Dividend
                print("Processing cash - dividend transaction")
                return Transaction(
                    meta=None,
                    date=transaction.date,
                    flag="*",
                    payee=transaction.name,
                    narration="",
                    tags=set(),
                    links=set(),
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
                )
            elif transaction.type.subtype == "deposit":
                # Deposit
                print("Processing cash - deposit transaction")
                return Transaction(
                    meta=None,
                    date=transaction.date,
                    flag="*",
                    payee=transaction.name,
                    narration="",
                    tags=set(),
                    links=set(),
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
                            account="Assets:Checking",
                            units=Amount(-transaction.amount if transaction.amount > 0 else transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                )
            elif transaction.type.subtype == "withdrawal":
                # Withdrawal
                print("Processing cash - withdrawal transaction")
        return Transaction(
                    meta=None,
            date=transaction.date,            
                    flag="*",
                    payee=transaction.name,
                    narration="",
            tags=set(),
            links=set(),
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
                            account="Assets:Checking",
                            units=Amount(-transaction.amount if transaction.amount > 0 else transaction.amount, transaction.iso_currency_code),
                            cost=None,
                            price=None,
                            flag=None,
                            meta=None,
                        ),
                    ],
                )

        raise ValueError(f"Unknown transaction type: {transaction.type.type} - {transaction.type.subtype}")
