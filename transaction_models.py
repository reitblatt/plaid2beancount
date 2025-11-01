from enum import Enum
import datetime
from decimal import Decimal
import abc

class FinanceCategory:
    
    def __init__(self, primary: str, detailed: str, description: str) -> None:
        self.primary = primary
        self.detailed = detailed
        self.description = description
            
    def __str__(self):        
        return self.detailed

class PlaidItem:
    
    def __init__(self, name: str, item_id: str, access_token: str, cursor: str) -> None:
        self.name = name
        self.item_id = item_id
        self.access_token = access_token
        self.cursor = cursor            
    
    def __str__(self):
        if self.name is not None:
            return self.name
        else:
            return self.item_id              

class Account:
    class AccountTypes(Enum):
        depository = 'Depository'
        credit = 'Credit'
        loan = 'Loan'
        investment = 'Investment'
        other = 'Other'
    
    def __init__(self, name: str, beancount_name: str, plaid_id: str, transaction_file: str, plaid_item: PlaidItem, type: AccountTypes) -> None:
        self.name = name
        self.beancount_name = beancount_name
        self.plaid_id = plaid_id
        self.transaction_file = transaction_file
        self.item = plaid_item
        self.type = type
        self.last_updated = None    
    
    def __str__(self):
        if self.name is not None:
            return self.name
        else:
            return self.plaid_id

class PlaidTransaction:
    class ConfidenceLevels(Enum):
        VERY_HIGH = 'Very High'
        HIGH = 'High'
        MEDIUM = 'Medium'
        LOW = 'Low'
        UNKNOWN = 'Unknown'
        
    def __init__(self, date: datetime.date, time: datetime.datetime, 
                 name: str, merchant_name: str, website: str, amount: Decimal, currency: str, 
                 check_number: str, transaction_id: str, account: Account, 
                 personal_finance_category: FinanceCategory, personal_finance_confidence: ConfidenceLevels, pending: bool) -> None:
        self.date = date
        self.time = None
        self.authorized_date = None
        self.authorized_datetime = None
        self.name = name
        self.merchant_name = merchant_name
        self.website = website
        self.amount = amount
        self.currency = currency
        self.check_number = check_number
        self.transaction_id = transaction_id
        self.account = account
        self.personal_finance_category = personal_finance_category
        self.personal_finance_confidence = personal_finance_confidence
        self.pending = pending    
    
    def __str__(self) -> str:
        return f'{self.name} - {self.merchant_name} - {self.date} - {self.amount}'
    
class PlaidSecurity:
    
    def __init__(self, security_id: str, name: str, ticker_symbol: str, type: str, market_identifier_code: str, is_cash_equivalent: bool, isin: str, cusip: str) -> None:
        self.security_id = security_id
        self.name = name
        self.ticker_symbol = ticker_symbol
        self.type = type
        self.market_identifier_code = market_identifier_code
        self.is_cash_equivalent = is_cash_equivalent
        self.isin = isin
        self.cusip = cusip            
    
    def __str__(self) -> str:
        return self.name
        
class PlaidInvestmentTransactionType:
    
    def __init__(self, type: str, subtype: str) -> None:
        self.type = type
        self.subtype = subtype            
        
    def __str__(self) -> str:
        return f'{self.type} - {self.subtype}'
    
class PlaidInvestmentTransaction:
    
    def __init__(self, date: datetime.date, name: str, quantity: Decimal, price: Decimal, amount: Decimal, security: PlaidSecurity, fees: Decimal, cancel_transaction_id: str, investment_transaction_id: str, iso_currency_code: str, type: PlaidInvestmentTransactionType, account: Account) -> None:
        self.date = date
        self.name = name
        self.quantity = quantity
        self.price = price
        self.amount = amount
        self.security = security
        self.fees = fees
        self.cancel_transaction_id = cancel_transaction_id
        self.investment_transaction_id = investment_transaction_id
        self.iso_currency_code = iso_currency_code
        self.type = type
        self.account = account

    def __str__(self) -> str:
        return f'{self.name} - {self.type} - {self.date} - {self.amount}'