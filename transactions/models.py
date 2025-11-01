from django.db import models

class FinanceCategory(models.Model):
    primary = models.CharField(max_length=255)
    detailed = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=255)
    expense_account = models.CharField(max_length=255, null=True, default=None)
    
    def __str__(self):        
        return self.detailed

class PlaidItem(models.Model):
    name = models.CharField(max_length=255, null=True, default=None)
    item_id = models.CharField(max_length=255, unique=True)
    access_token = models.CharField(max_length=255)
    cursor = models.CharField(max_length=255, null=True, default=None)
    
    def __str__(self):
        if self.name is not None:
            return self.name
        else:
            return self.item_id

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('depository', 'Depository'),
        ('credit', 'Credit'),
        ('loan', 'Loan'),
        ('investment', 'Investment'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=255, null=True, default=None)
    beancount_name = models.CharField(max_length=255, null=True, default=None)
    plaid_id = models.CharField(max_length=255, unique=True)
    transaction_file = models.CharField(max_length=255, null=True, default=None)
    item = models.ForeignKey(PlaidItem, on_delete=models.CASCADE, related_name='accounts')
    type = models.CharField(max_length=255, choices=ACCOUNT_TYPES)
    last_updated = models.DateTimeField(null=True, default=None)
    
    def __str__(self):
        if self.name is not None:
            return self.name
        else:
            return self.plaid_id

class PlaidTransaction(models.Model):
    CONFIDENCE_CHOICES = [
        ('VERY_HIGH', 'Very High'),
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
        ('UNKNOWN', 'Unknown'),
    ]

    date = models.DateField()
    datetime = models.DateTimeField(null=True, default=None)
    authorized_date = models.DateField(null=True, default=None)
    authorized_datetime = models.DateTimeField(null=True, default=None)
    name = models.CharField(max_length=255)
    merchant_name = models.CharField(max_length=255, null=True, default=None)
    website = models.CharField(max_length=255, null=True, default=None)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    check_number = models.CharField(max_length=255, null=True, default=None)
    transaction_id = models.CharField(max_length=255, unique=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    personal_finance_category = models.ForeignKey(FinanceCategory, on_delete=models.SET_NULL, null=True, default=None)
    personal_finance_confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default='UNKNOWN')
    pending = models.BooleanField()
    
    def __str__(self) -> str:
        return f'{self.name} - {self.merchant_name} - {self.date} - {self.amount}'
    
class PlaidSecurity(models.Model):
    security_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    ticker_symbol = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(max_length=255)
    market_identifier_code = models.CharField(max_length=255, null=True, blank=True)
    is_cash_equivalent = models.BooleanField()
    isin = models.CharField(max_length=255, null=True, blank=True)
    cusip = models.CharField(max_length=255, null=True, blank=True)
    
    def __str__(self) -> str:
        return self.name
        
class PlaidInvestmentTransactionType(models.Model):
    type = models.CharField(max_length=255)
    subtype = models.CharField(max_length=255)
    
    class Meta:
        unique_together = ['type', 'subtype']
        
    def __str__(self) -> str:
        return f'{self.type} - {self.subtype}'
    
class PlaidInvestmentTransaction(models.Model):    
    
    date = models.DateField()
    name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    security = models.ForeignKey(PlaidSecurity, on_delete=models.CASCADE)
    fees = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cancel_transaction_id = models.CharField(max_length=255, null=True, blank=True)
    investment_transaction_id = models.CharField(max_length=255, unique=True)
    iso_currency_code = models.CharField(max_length=255, null=True, blank=True, default='USD')    
    type = models.ForeignKey(PlaidInvestmentTransactionType, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f'{self.name} - {self.type} - {self.date} - {self.amount}'