from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from beancount import loader, core
import plaid
from plaid.api import plaid_api

from .models import PlaidItem, Account, FinanceCategory, PlaidTransaction, PlaidInvestmentTransaction, PlaidSecurity, PlaidInvestmentTransactionType
from .forms import TransactionFilterForm
from .beancount_renderer import BeancountRenderer
from .plaid_fetch import fetch_investments, fetch_transactions
from .config import load_config_file

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
    
@csrf_exempt
def load_configuration(request):
    if request.method == 'POST':
        config = load_config_file()
        
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
    


@csrf_exempt
def update_transactions(request):
    if request.method == 'POST':
        config = load_config_file()
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
        investment_transactions = PlaidInvestmentTransaction.objects.filter(account=account).filter(pending=False)        

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