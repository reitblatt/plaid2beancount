from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from beancount import loader, core
import plaid
from plaid.api import plaid_api
from plaid.configuration import Configuration, Environment
from plaid.api_client import ApiClient

from .models import PlaidItem, Account, FinanceCategory, PlaidTransaction, PlaidInvestmentTransaction, PlaidSecurity, PlaidInvestmentTransactionType
from .forms import TransactionFilterForm
from .beancount_renderer import BeancountRenderer
from .plaid_fetch import fetch_investments, fetch_transactions
from .config import load_config_file

def starting_page(request):
    return render(request, 'starting_page.html')


"""
The plaid configuration assumes that the beancount accounts are structured so that all of the 
asset accounts at a given institution are under a parent account with the institution's name. 
For example, if you have a bank account at Foo Bank, the accounts would be structured like this:

Assets:Foo-Bank
Assets:Foo-Bank:Checking

Etc

We store the plaid login info (i.e. 'item_id' and 'access_token') under the parent (institution) account, 
and the per-account info (i.e. 'account_id') under the child account, like so:
open 2000-01-01 Assets:Foo-Bank
  access_token: "production-..."
  plaid_item_id: "..."
  
open 2000-01-01 Assets:Foo-Bank:Checking
    plaid_account_id: "..."
    
By default, transactions for each account are stored under accounts/Instutition/Account-Name.beancount

E.g.:
Assets:Ally:Savings

accounts/Ally/Savings.beancount
"""
def _load_beancount_accounts(file_path):
    entries, _, _= loader.load_file(file_path)
    # We want to pull out just the accounts and metadat
    accounts = [entry for entry in entries if isinstance(entry, core.data.Open)]
    
    items = {
        account.account: account
        for account in accounts
        if "plaid_item_id" in account.meta and "plaid_access_token" in account.meta
    }
    
    plaid_accounts = [
        (account, items[core.account.parent(account.account)].meta['plaid_item_id'], items[core.account.parent(account.account)].meta['plaid_access_token'])
        for account in accounts
        if "plaid_account_id" in account.meta                
    ]        
    
    # print(plaid_accounts)

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
    return short_names, expense_accounts, plaid_accounts

def _load_beancount_entries():
    config = load_config_file()        
    root_file = config["BEANCOUNT"]["root_file"]

    # Load the beancount file
    entries, _, _= loader.load_file(root_file)
        
    return entries

def _get_beancount_accounts_directory():
    config = load_config_file()        
    root_file = config["BEANCOUNT"]["root_file"]
    import os
    root_file = os.path.expanduser(root_file)
    # abs_file_path = os.path.abspath(root_file)
    return os.path.dirname(root_file)
    
def _calculate_filename_from_account(account: str):    
    account_parts = account.split(':')
    file_name = None
    if account_parts[0] == 'Assets':
        if len(account_parts) >= 3:
            file_name = f"accounts/{account_parts[1]}/{account_parts[2]}.beancount"
        else:
            print(f"Account {account} is not structured correctly")
    elif account_parts[0] == 'Liabilities':
        if account_parts[1] == 'Credit-Card' and len(account_parts) >= 4:            
            file_name = f"accounts/{account_parts[2]}/{account_parts[3]}.beancount"
        elif len(account_parts) >= 3:
            file_name = f"accounts/{account_parts[1]}/{account_parts[2]}.beancount"
        else:
            print(f"Account {account} is not structured correctly")
    return file_name

@csrf_exempt
def load_configuration(request):
    if request.method == 'POST':
        config = load_config_file()
        
        root_file = config["BEANCOUNT"]["root_file"]

        del config["BEANCOUNT"]

        # Load the beancount file
        _, expense_accounts, plaid_accounts = _load_beancount_accounts(root_file)

        # update expense accounts with the new accounts
        for category in FinanceCategory.objects.all():
            if category.detailed in expense_accounts:
                category.expense_account = expense_accounts[category.detailed]
            else:
                category.expense_account = None

            category.save()        

        # Remove the Plaid configuration from the TOML file
        del config["PLAID"]

        for account, item_id, access_token in plaid_accounts:            
            account_id = account.meta['plaid_account_id']

            # First, check if the parent item (institution) exists
            item, created = PlaidItem.objects.get_or_create(
                item_id=item_id,
                defaults={
                    "access_token": access_token,
                },
            )

            if created:
                item.save()
            # Split the account name into the institution and the account
            file_name = _calculate_filename_from_account(account.account)
            
            django_account, created = Account.objects.get_or_create(
                plaid_id=account_id,
                defaults={
                    "name": account.meta["short_name"],
                    "item": item,
                    "beancount_name": account.account,
                    "transaction_file": file_name,
                },
            )
            if created:
                django_account.save()
            else:
                # update the account name if it's changed
                if django_account.beancount_name != account.account:
                    django_account.beancount_name = account.account
                    django_account.save()
                if django_account.transaction_file != file_name:
                    django_account.transaction_file = file_name
                    django_account.save()
            print(django_account)
            print(file_name)
        accounts = Account.objects.all()
        return render(request, 'accounts.html', {'accounts': accounts})
    


@csrf_exempt
def update_transactions(request):
    if request.method == 'POST':
        config = load_config_file()
        # Get the Plaid configuration from the TOML file
        client_id = config["PLAID"]["client_id"]
        secret = config["PLAID"]["secret"]
        
        
        configuration = Configuration(
            host=Environment.Production,
            api_key={
                "clientId": client_id,
                "secret": secret,
            },
        )

        api_client = ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)
        
        new_transactions = fetch_transactions(client)
        new_investment_transactions = fetch_investments(client)
        return render(request, 'transactions.html', {'transactions': new_transactions, 'investment_transactions': new_investment_transactions})        

def transaction_filter(request):
    form = TransactionFilterForm(request.POST or None)
    transactions = PlaidTransaction.objects.none()  # Empty QuerySet
    investment_transactions = PlaidInvestmentTransaction.objects.none()  # Empty QuerySet
    investment_transactions = PlaidInvestmentTransaction.objects.none()  # Empty QuerySet

    if form.is_valid():
        account = form.cleaned_data['account']
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']

        transactions = PlaidTransaction.objects.filter(account=account).filter(pending=False)
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

def update_beancount(request):
    # For each account, look up the most recent transaction with a plaid_transaction_id, 
    # and output all transactions since then    
    accounts = Account.objects.filter(transaction_file__isnull=False)
    entries = _load_beancount_entries()
    import os
    
    os.chdir(_get_beancount_accounts_directory())    
    for account in accounts:        
        file_name = account.transaction_file                
        account_matcher = core.account.parent_matcher(account.beancount_name)
        filtered_entries = [
            entry for entry in entries 
            if isinstance(entry, core.data.Transaction) and                 
                "plaid_transaction_id" in entry.meta and
                any(account_matcher(posting.account) for posting in entry.postings)
            ]
        if not filtered_entries:
            print(f"No transactions found for {account}")
            continue
        most_recent_transaction = max(filtered_entries, key=lambda x: x.date)
        transactions = PlaidTransaction.objects.filter(account=account).filter(pending=False).filter(date__gt=most_recent_transaction.date).order_by('date')
        investment_transactions = PlaidInvestmentTransaction.objects.filter(account=account).filter(date__gt=most_recent_transaction.date).order_by('date')
        renderer = BeancountRenderer(transactions, investment_transactions)
        output = [ renderer._printer(transaction) for transaction in renderer.transactions + renderer.investment_transactions ] 
        with open(file_name, 'a') as f:
            f.writelines(output)                    
    
    return render(request, 'output_beancount.html', {'transactions': []})