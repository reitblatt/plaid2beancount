from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime
from enum import Enum
from typing import Optional
from beancount.core.data import Meta, Custom
from beancount.core.amount import Amount
from beancount.core.number import Decimal
from beancount.core import data

class PlaidCursor(Custom):
    """A custom directive to store the Plaid cursor for an account."""
    def __init__(self, date: date, meta: Meta, account: str, cursor: str, item_id: str):
        super().__init__(date, meta, "plaid_cursor", [account, cursor, item_id])
        self.account = account
        self.cursor = cursor
        self.item_id = item_id

    @classmethod
    def parse(cls, date: date, meta: Meta, values: list) -> 'PlaidCursor':
        """Parse a plaid_cursor directive from values."""
        if len(values) != 3:
            raise ValueError("plaid_cursor directive requires exactly 3 values: account, cursor, item_id")
        account, cursor, item_id = values
        return cls(date, meta, account, cursor, item_id)

    def __str__(self) -> str:
        return f'plaid_cursor {self.account} {self.cursor} {self.item_id}'

@dataclass
class PlaidItem:
    name: str
    item_id: str
    access_token: str
    cursor: Optional[str] = None

@dataclass
class Account:
    name: str
    beancount_name: str
    plaid_id: str
    transaction_file: str
    item: PlaidItem
    type: str  # 'depository', 'credit', 'loan', 'investment', 'other'

@dataclass
class FinanceCategory:
    primary: str
    detailed: str
    description: str
    expense_account: Optional[str] = None

@dataclass
class PlaidTransaction:
    date: date
    datetime: Optional[datetime] = None
    authorized_date: Optional[date] = None
    authorized_datetime: Optional[datetime] = None
    name: str = ""
    merchant_name: Optional[str] = None
    website: Optional[str] = None
    amount: Decimal = Decimal('0')
    currency: str = "USD"
    check_number: Optional[str] = None
    transaction_id: str = ""
    account: Optional[Account] = None
    personal_finance_category: Optional[FinanceCategory] = None
    personal_finance_confidence: str = "UNKNOWN"
    pending: bool = False

@dataclass
class PlaidSecurity:
    security_id: str
    name: str
    ticker_symbol: str
    type: str
    market_identifier_code: str
    is_cash_equivalent: bool
    isin: Optional[str] = None
    cusip: Optional[str] = None

@dataclass
class PlaidInvestmentTransactionType:
    type: str
    subtype: str

@dataclass
class PlaidInvestmentTransaction:
    date: date
    name: str
    quantity: Decimal
    price: Decimal
    amount: Decimal
    security: PlaidSecurity
    fees: Optional[Decimal] = None
    cancel_transaction_id: Optional[str] = None
    investment_transaction_id: str = ""
    iso_currency_code: str = "USD"
    type: Optional[PlaidInvestmentTransactionType] = None
    account: Optional[Account] = None
