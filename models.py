from peewee import *

db = SqliteDatabase("plaid.db")


class FinanceCategory(Model):
    primary = CharField()
    detailed = CharField(unique=True)
    description = CharField()
    expense_account = CharField(null=True, default=None)

    class Meta:
        database = db


class PlaidItem(Model):
    name = CharField(null=True, default=None)
    item_id = CharField(unique=True)
    access_token = CharField()
    cursor = CharField(null=True, default=None)

    class Meta:
        database = db


class Account(Model):
    name = CharField(null=True, default=None)
    beancount_name = CharField(null=True, default=None)
    plaid_id = CharField(unique=True)
    item = ForeignKeyField(PlaidItem, backref="accounts")
    type = CharField(choices=["depository", "credit", "loan", "investment", "other"])

    class Meta:
        database = db


class PlaidTransaction(Model):
    date = DateField()
    datetime = DateTimeField(null=True, default=None)
    authorized_date = DateField(null=True, default=None)
    authorized_datetime = DateTimeField(null=True, default=None)
    name = CharField()
    merchant_name = CharField(null=True, default=None)
    website = CharField(null=True, default=None)
    amount = DecimalField()
    unit = CharField(default="USD")
    check_number = CharField(null=True, default=None)
    transaction_id = CharField(unique=True)
    account = ForeignKeyField(Account)
    personal_finance_category = ForeignKeyField(
        FinanceCategory, null=True, default=None
    )
    personal_finance_confidence = CharField(
        choices=["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "UNKNOWN"], default="UNKNOWN"
    )
    pending = BooleanField()

    class Meta:
        database = db


class PlaidSecurity(Model):
    id = CharField(unique=True)
    name = CharField()
    ticker_symbol = CharField(null=True, default=None)
    type = CharField()
    market_identifier_code = CharField(null=True, default=None)
    is_cash_equivalent = BooleanField()
    isin = CharField(null=True, default=None)
    cusip = CharField(null=True, default=None)


class PlaidInvestmentTransaction(Model):
    date = DateField()
    name = CharField()
    price = DecimalField()
    amount = DecimalField()
    security = ForeignKeyField(PlaidSecurity)
    fees = DecimalField(null=True, default=None)
    cancel_transaction_id = CharField(null=True, default=None)
    investment_transaction_id = CharField(unique=True)
    iso_currency_code = CharField(null=True, default="USD")
    type = CharField()
    subtype = CharField()


db.connect()
db.create_tables([FinanceCategory, PlaidItem, Account, PlaidTransaction])
