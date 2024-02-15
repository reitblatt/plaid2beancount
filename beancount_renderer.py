from models import PlaidTransaction
from beancount.core.data import Transaction, Amount, Posting, Price, Balance
from beancount.parser.printer import EntryPrinter

class BeancountRenderer:
        
    def __init__(self, transactions: PlaidTransaction):
        self.transactions = [self._to_beancount(transaction) for transaction in transactions]                        
        self._printer = EntryPrinter()
        
    def print(self) -> [str]:
        return [self._printer(transaction) for transaction in self.transactions]
    
    def _to_beancount(self, transaction) -> Transaction:
        if transaction.personal_finance_category.expense_account is not None:
            expense_account = transaction.personal_finance_category.expense_account
        else:
            expense_account = 'Expenses:Unknown'        
            
        if transaction.account.beancount_name is not None:
            account = transaction.account.beancount_name
        else:
            account = 'Unknown'        
        
        return Transaction(
            meta={'plaid_transaction_id': transaction.transaction_id},
            date=transaction.date,
            payee=transaction.merchant_name,
            narration=transaction.name,            
            flag='',
            tags=set(),
            links=set(),
            postings=[
                Posting(account, Amount(-transaction.amount, 'USD'), None, None, None, None),
                Posting(expense_account, Amount(transaction.amount, 'USD'), None, None, None, None),
            ],
        )