from django.contrib import admin

from .models import *

admin.site.register(FinanceCategory)
admin.site.register(PlaidItem)
admin.site.register(Account)
admin.site.register(PlaidTransaction)
admin.site.register(PlaidSecurity)
admin.site.register(PlaidInvestmentTransaction)
