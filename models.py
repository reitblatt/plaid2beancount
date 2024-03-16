from peewee import *

db = SqliteDatabase('plaid.db')

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
    item = ForeignKeyField(PlaidItem, backref='accounts') 
    
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
    unit = CharField(default='USD')
    check_number = CharField(null=True, default=None)
    transaction_id = CharField(unique=True)    
    account = ForeignKeyField(Account)
    personal_finance_category = ForeignKeyField(FinanceCategory,null=True, default=None)
    personal_finance_confidence = CharField(choices=['VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'], default='UNKNOWN')
    pending = BooleanField()

    class Meta:
        database = db            
        
        
db.connect()
db.create_tables([FinanceCategory, PlaidItem, Account, PlaidTransaction])