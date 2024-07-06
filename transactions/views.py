from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import configparser
from beancount import loader, core
import plaid
from plaid.api import plaid_api
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest
from plaid.model.investments_transactions_get_request_options import (
    InvestmentsTransactionsGetRequestOptions,
)
import datetime
from datetime import date, timedelta

from .models import PlaidItem, Account, FinanceCategory, PlaidTransaction, PlaidInvestmentTransaction, PlaidSecurity, PlaidInvestmentTransactionType
from .forms import TransactionFilterForm
from .beancount_renderer import BeancountRenderer

def starting_page(request):
    return render(request, 'starting_page.html')

def _load_beancount_accounts(file_path):
    entries, _, _= loader.load_file(file_path)
    # We want to pull out just the accounts and metadat
    accounts = [entry for entry in entries if isinstance(entry, core.data.Open)]

    short_names = {
        account.meta["short_name"]: account.account
        for account in accounts
        if "short_name" in account.meta
    }
    expense_accounts = {
        account.meta["plaid_category"]: account.account
        for account in accounts
        if "plaid_category" in account.meta
    }
    # convert accounts to a dict from plaid_id to account
    return short_names, expense_accounts

def _load_config_file():
    # Specify the path to the TOML file
    file_path = "/Users/reitblatt/.config/plaid2text/config"

    # Read the contents of the TOML file
    config = configparser.ConfigParser()
    config.read(file_path)
    
    return config
    
@csrf_exempt
def load_configuration(request):
    if request.method == 'POST':
        config = _load_config_file()
        
        root_file = config["BEANCOUNT"]["root_file"]

        del config["BEANCOUNT"]

        # Load the beancount file
        bc_accounts, expense_accounts = _load_beancount_accounts(root_file)

        # update expense accounts with the new accounts
        for category in FinanceCategory.objects.all():
            if category.detailed in expense_accounts:
                category.expense_account = expense_accounts[category.detailed]
            else:
                category.expense_account = None

            category.save()        

        # Remove the Plaid configuration from the TOML file
        del config["PLAID"]

        for account_name in config.sections():
            access_token = config[account_name]["access_token"]
            item_id = config[account_name]["item_id"]
            account_id = config[account_name]["account"]

            # First, check if the parent item (institution) exists
            item, created = PlaidItem.objects.get_or_create(
                item_id=item_id,
                defaults={
                    "access_token": access_token,
                },
            )

            if created:
                item.save()

            if account_name in bc_accounts:
                beancount_account = bc_accounts[account_name]
            else:
                beancount_account = None
            account, created = Account.objects.get_or_create(
                plaid_id=account_id,
                defaults={
                    "name": account_name,
                    "item": item,
                    "beancount_name": beancount_account,
                },
            )
            if created:
                account.save()
            else:
                # update the account name if it's changed
                if account.beancount_name != beancount_account:
                    account.beancount_name = beancount_account
                    account.save()
        accounts = Account.objects.all()
        return render(request, 'accounts.html', {'accounts': accounts})        

def _update_transactions(client: plaid_api.PlaidApi):
    new_transactions = []
    updated_accounts = set()
    for item in PlaidItem.objects.all():
        access_token = item.access_token
        cursor = item.cursor
        if cursor is None:
            cursor = ""
        has_more = True

        while has_more:
            request = TransactionsSyncRequest(
                access_token=access_token,
                cursor=cursor,
                count=100,
            )

            response = client.transactions_sync(request)
            transactions = response["added"]
            has_more = response["has_more"]
            # Update cursor to the next cursor
            cursor = response["next_cursor"]

            for transaction in transactions:
                print(transaction)
                if transaction["pending"]:
                    print('skipping pending transaction')
                    
                if transaction["personal_finance_category"] is not None:
                    category, created = FinanceCategory.objects.get_or_create(
                        detailed=transaction["personal_finance_category"]["detailed"],
                        defaults={
                            "primary": transaction["personal_finance_category"][
                                "primary"
                            ],
                            "description": "Unknown (Plaid added a new category!)",
                        },
                    )
                    if created:
                        # Uh oh! Plaid added a new category...
                        category.save()

                    confidence = transaction["personal_finance_category"][
                        "confidence_level"
                    ]

                account, created = Account.objects.get_or_create(
                    plaid_id=transaction["account_id"],
                    defaults={
                        "name": "Unknown account found during Plaid sync!",
                        "item": item,
                    },
                )
                updated_accounts.add(account)
                if created:
                    account.save()
                    
                new_transaction, created = PlaidTransaction.objects.get_or_create(
                    transaction_id=transaction["transaction_id"],
                    defaults={
                        "date": transaction["date"],
                        "datetime": transaction["datetime"],
                        "authorized_date": transaction["authorized_date"],
                        "authorized_datetime": transaction["authorized_datetime"],
                        "name": transaction["name"],
                        "merchant_name": transaction["merchant_name"],
                        "website": transaction["website"],
                        "amount": transaction["amount"],
                        "check_number": transaction["check_number"],                    
                        "account": account,
                        "personal_finance_category": category,
                        "personal_finance_confidence": confidence,
                        "pending": transaction["pending"],
                    }
                )
                new_transactions.append(new_transaction)
                new_transaction.save()

            # Save the cursor for the next time we sync
            item.cursor = cursor                    
            item.save()
            for account in updated_accounts:
                account.last_updated = datetime.datetime.now()
                account.save()
            print("No more transactions to sync for item {0}".format(item.item_id))
    return new_transactions
    
    
def _update_investments(client: plaid_api.PlaidApi, start_date=None, end_date=None):
    new_transactions = []
    for item in PlaidItem.objects.all():
        access_token = item.access_token
        if start_date is None:
            # If date not set, set to today minus 2 years
            start_date = date.today() - timedelta(days=365 * 2)
        if end_date is None:
            end_date = date.today()

        request = InvestmentsTransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            response = client.investments_transactions_get(request)
            investment_transactions = response["investment_transactions"]
            securities = {
                security["security_id"]: security for security in response["securities"]
            }
        except plaid.ApiException as e:
            print(e)
            print(
                "Error getting investment transactions for item {0}".format(
                    item.item_id
                )
            )
            continue

        while len(investment_transactions) < response["total_investment_transactions"]:
            request = InvestmentsTransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=InvestmentsTransactionsGetRequestOptions(
                    offset=len(investment_transactions)
                ),
            )
            response = client.investments_transactions_get(request)            
            securities |= {
                security["security_id"]: security for security in response["securities"]
            }
            investment_transactions.extend(response["transactions"])

        for transaction in investment_transactions:
            print(transaction)
            account, created = Account.objects.get_or_create(
                plaid_id=transaction["account_id"],
                defaults={
                    "name": "Unknown account found during Plaid sync!",
                    "item": item,
                },
            )
            if created:
                account.save()

            if transaction["security_id"] is not None:
                plaid_security = securities.get(transaction["security_id"])
                security, created = PlaidSecurity.objects.get_or_create(
                    security_id=plaid_security["security_id"],                    
                    defaults={
                        "name": plaid_security["name"],                        
                        "ticker_symbol": plaid_security["ticker_symbol"],
                        "type": plaid_security["type"],
                        "market_identifier_code": plaid_security["market_identifier_code"],
                        "is_cash_equivalent": plaid_security["is_cash_equivalent"],
                        "isin": plaid_security["isin"],
                        "cusip": plaid_security["cusip"],
                    },
                )
                
                if created:
                    security.save()
            transaction_type, created = PlaidInvestmentTransactionType.objects.get_or_create(
                type=transaction["type"],
                subtype=transaction["subtype"],
            )
            
            if created:
                transaction_type.save()
                
            new_transaction, created = PlaidInvestmentTransaction.objects.get_or_create(
                investment_transaction_id=transaction["investment_transaction_id"],
                defaults={
                    "date": transaction["date"],
                    "name": transaction["name"],
                    "quantity": transaction["quantity"],
                    "amount": transaction["amount"],
                    "price": transaction["price"],
                    "account": account,
                    "security": security,
                    "fees": transaction["fees"],
                    "cancel_transaction_id": transaction["cancel_transaction_id"],
                    "type": transaction_type,
                },
            )
            
            if created:
                new_transaction.save()
            new_transactions.append(new_transaction)            

    return new_transactions            

@csrf_exempt
def update_transactions(request):
    if request.method == 'POST':
        config = _load_config_file()
        # Get the Plaid configuration from the TOML file
        client_id = config["PLAID"]["client_id"]
        secret = config["PLAID"]["secret"]
        
        
        configuration = plaid.Configuration(
            host=plaid.Environment.Production,
            api_key={
                "clientId": client_id,
                "secret": secret,
            },
        )

        api_client = plaid.ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)
        
        new_transactions = _update_transactions(client)
        new_investment_transactions = _update_investments(client)
        return render(request, 'transactions.html', {'transactions': new_transactions, 'investment_transactions': new_investment_transactions})        

def transaction_filter(request):
    form = TransactionFilterForm(request.POST or None)
    transactions = PlaidTransaction.objects.none()  # Empty QuerySet
    investment_transactions = PlaidInvestmentTransaction.objects.none()  # Empty QuerySet

    if form.is_valid():
        account = form.cleaned_data['account']
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']

        transactions = PlaidTransaction.objects.filter(account=account)
        investment_transactions = PlaidInvestmentTransaction.objects.filter(account=account)

        if start_date:
            transactions = transactions.filter(date__gte=start_date)
            investment_transactions = investment_transactions.filter(date__gte=start_date)
        if end_date:
            transactions = transactions.filter(date__lte=end_date)
            investment_transactions = investment_transactions.filter(date__lte=end_date)

    return render(request, 'transaction_filter.html', {'form': form, 'transactions': transactions, 'investment_transactions': investment_transactions})

def output_beancount(request):
    # Take in a list of transactions from the form and output them in beancount format    
    transaction_ids = request.POST.getlist('transactions')        
    investment_transaction_ids = request.POST.getlist('investment-transactions')        
    transactions = PlaidTransaction.objects.filter(id__in=transaction_ids).order_by('date')
    investment_transactions = PlaidInvestmentTransaction.objects.filter(id__in=investment_transaction_ids).order_by('date')
    renderer = BeancountRenderer(transactions, investment_transactions)    
    output = [ renderer._printer(transaction) for transaction in renderer.transactions + renderer.investment_transactions ]    
    return render(request, 'output_beancount.html', {'transactions': output})