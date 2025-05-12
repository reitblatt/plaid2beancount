from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

@dataclass
class FinanceCategory:
    primary: str
    detailed: str
    description: str
    expense_account: Optional[str] = None
    
    def __str__(self):        
        return self.detailed

@dataclass
class PlaidItem:
    name: Optional[str]
    item_id: str
    access_token: str
    cursor: Optional[str] = None
    
    def __str__(self):
        if self.name is not None:
            return self.name
        else:
            return self.item_id

@dataclass
class Account:
    name: Optional[str]
    beancount_name: Optional[str]
    plaid_id: str
    transaction_file: Optional[str]
    item: PlaidItem
    type: str
    last_updated: Optional[datetime] = None
    
    def __str__(self):
        if self.name is not None:
            return self.name
        else:
            return self.plaid_id

@dataclass
class PlaidSecurity:
    security_id: str
    name: str
    ticker_symbol: Optional[str]
    type: str
    market_identifier_code: Optional[str]
    is_cash_equivalent: bool
    isin: Optional[str]
    cusip: Optional[str]
    
    def __str__(self) -> str:
        return self.name
        
@dataclass
class PlaidInvestmentTransactionType:
    type: str
    subtype: Optional[str]
    
    def __str__(self) -> str:
        return f'{self.type} - {self.subtype}'
    
@dataclass
class PlaidInvestmentTransaction:    
    date: date
    name: str
    quantity: Decimal
    price: Decimal
    amount: Decimal
    security: Optional[PlaidSecurity]
    fees: Optional[Decimal]
    cancel_transaction_id: Optional[str]
    investment_transaction_id: str
    iso_currency_code: str
    type: PlaidInvestmentTransactionType
    account: Account

    def __str__(self) -> str:
        return f'{self.name} - {self.type} - {self.date} - {self.amount}'

@dataclass
class PlaidTransaction:
    date: date
    datetime: Optional[datetime]
    authorized_date: Optional[date]
    authorized_datetime: Optional[datetime]
    name: str
    merchant_name: Optional[str]
    website: Optional[str]
    amount: Decimal
    currency: str
    check_number: Optional[str]
    transaction_id: str
    account: Account
    personal_finance_category: Optional[FinanceCategory]
    personal_finance_confidence: str
    pending: bool
    
    def __str__(self) -> str:
        return f'{self.name} - {self.merchant_name} - {self.date} - {self.amount}'

@dataclass
class PlaidCursor:
    date: date
    account: str
    item_id: str
    cursor: str
    
    def __str__(self):
        return f'{self.account} - {self.date} - {self.cursor}' 