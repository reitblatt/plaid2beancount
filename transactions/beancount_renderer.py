from decimal import Decimal
from typing import List
from .models import PlaidTransaction, PlaidInvestmentTransaction
from beancount.core.data import Transaction, Amount, Posting, Price, Balance
from beancount.parser.printer import EntryPrinter


class BeancountRenderer:
    def __init__(self, transactions: List[PlaidTransaction], investment_transactions: List[PlaidInvestmentTransaction]):
        self.transactions = [
            self._to_beancount(transaction) for transaction in transactions
        ]        
        self.investment_transactions = [
            self._to_investment_beancount(investment_transaction) for investment_transaction in investment_transactions
        ]
        self._printer = EntryPrinter()

    def print(self) -> List[str]:
        return [self._printer(transaction) for transaction in self.transactions]

    def _to_beancount(self, transaction: PlaidTransaction) -> Transaction:
        if transaction.personal_finance_category.expense_account is not None:
            expense_account = transaction.personal_finance_category.expense_account
        else:
            expense_account = (
                "Unknown: " + transaction.personal_finance_category.detailed
            )

        if transaction.account.beancount_name is not None:
            account = transaction.account.beancount_name
        else:
            account = "Unknown"

        return Transaction(
            meta={"plaid_transaction_id": transaction.transaction_id},
            date=transaction.date,
            payee=transaction.merchant_name,
            narration=transaction.name,
            flag="!",
            tags=set(),
            links=set(),
            postings=[
                Posting(
                    account, Amount(-transaction.amount, "USD"), None, None, None, None
                ),
                Posting(
                    expense_account,
                    Amount(transaction.amount, "USD"),
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )
        
    def _to_investment_beancount(self, transaction: PlaidInvestmentTransaction) -> Transaction:                        
        if transaction.account.beancount_name is not None:
            account = transaction.account.beancount_name
        else:
            account = "Unknown"
            
        ticker = transaction.security.ticker_symbol
        
        gains_account = None
        source_posting = None
        sink_posting = None
            
        # buy or sweep in
        if transaction.type.type == 'buy' or (transaction.type.type == 'fee' and transaction.type.subtype == 'miscellaneous fee'):            
            source_posting = Posting(
                account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None
            )
            # For some reason, dividends are not being recorded as a quantity
            quantity = transaction.quantity or transaction.amount
            price = transaction.price or Decimal('1.0')
                                                
            sink_posting = Posting(
                account + ":" + ticker, Amount(quantity, ticker), None, Amount(price, "USD"), None, None
            )
        elif transaction.type.type == 'sell':            
            source_posting = Posting(
                account + ":" + ticker, Amount(-transaction.quantity, ticker), None, Amount(transaction.price, "USD"), None, None
            )
            sink_posting = Posting(
                account + ":" + "Cash", Amount(transaction.amount, "USD"), None, None, None, None
            )            
            gains_account = account.replace("Assets", "Income") + "Capital-Gains" + ticker
            
        elif transaction.type.type == 'fee':
            if transaction.type.subtype == 'dividend':
                source_posting = Posting(
                    account.replace("Assets", "Income") + ":Dividends:" + ticker, Amount(transaction.amount, "USD"), None, None, None, None
                )
                sink_posting = Posting(
                    account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None    
                )
        
            # This is really a sweep out
            elif transaction.type.subtype == 'interest':
                source_posting = Posting(
                    account + ":" + ticker, Amount(transaction.amount, ticker), None, Amount(transaction.price, "USD"), None, None
                )
                sink_posting = Posting(
                    account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None    
                )                            
        elif transaction.type.type == 'cash':
            if transaction.type.subtype == 'deposit':
                source_posting = Posting(
                    "Assets:Transfer", Amount(transaction.amount, "USD"), None, None, None, None
                )
                sink_posting = Posting(
                    account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None
                )
            elif transaction.type.subtype == 'withdrawal':
                source_posting = Posting(
                    account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None
                )
                sink_posting = Posting(
                    "Assets:Transfer", Amount(transaction.amount, "USD"), None, None, None, None
                )
            elif transaction.type.subtype == 'dividend':
                source_posting = Posting(
                    account.replace("Assets", "Income") + ":Dividends:" + ticker, Amount(transaction.amount, "USD"), None, None, None, None
                )
                sink_posting = Posting(
                    account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None
                )
        elif transaction.type.type == 'transfer':
            # At some point Vanguard started using the transfer type for sweep in/out...
            if transaction.type.subtype == 'transfer':
                if transaction.name == 'Sweep in':
                    source_posting = Posting(
                        account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None
                    )
                    # For some reason, this is not being recorded as a quantity
                    quantity = transaction.quantity or transaction.amount
                    price = transaction.price or Decimal('1.0')
                                                        
                    sink_posting = Posting(
                        account + ":" + ticker, Amount(quantity, ticker), None, Amount(price, "USD"), None, None
                    )
                elif transaction.name == 'Sweep out':
                    source_posting = Posting(
                        account + ":" + ticker, Amount(transaction.amount, ticker), None, Amount(transaction.price, "USD"), None, None
                    )
                    sink_posting = Posting(
                        account + ":" + "Cash", Amount(-transaction.amount, "USD"), None, None, None, None    
                    )                   
                    
        if source_posting is None or sink_posting is None:
            print(transaction)
            raise ValueError(f"Unknown transaction type: {transaction.type.type} - {transaction.type.subtype}")
        postings = [source_posting, sink_posting]
        if gains_account is not None:
            postings.append(Posting(
                gains_account, None, None, None, None, None
            ))
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
