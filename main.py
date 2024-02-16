import plaid
from plaid.api import plaid_api
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from beancount import loader, core
from models import *
import configparser
import argparse


def _parse_args_and_load_config():
    defaults = {
        'sqlite_db': 'plaid.db',
    }
    
    # Build parser for args on command line
    parser = argparse.ArgumentParser(
        prog='Plaid2Beancount',
        # Don't suppress add_help here so it will handle -h
        # print script description with -h/--help
    )
    parser.set_defaults(**defaults)
    
    parser.add_argument(
        '--sync-all-transactions',
        '-s',
        action='store_true',
        help=(
            'sync transactions into DB for all accounts'
        )
    )
    
    parser.add_argument(
        '--sqlite-db',
        metavar='STR',
        help=(
            'The path to the SQLite database for storing transactions'
            ' (default: {0})'.format(defaults['sqlite_db'])
        )
    )
    
    parser.add_argument(
        '--to-date',
        metavar='STR',
        help=(
            'specify the ending date for transactions to be pulled; '
            'use in conjunction with --from-date to specify range'
            'Date format: YYYY-MM-DD'
        )
    )

    parser.add_argument(
        '--from-date',
        metavar='STR',
        help=(
            'specify a the starting date for transactions to be pulled; '
            'use in conjunction with --to-date to specify range'
            'Date format: YYYY-MM-DD'
        )
    )
    
    parser.add_argument(
        '--output-transactions',
        action='store_true',
        help=(
            'output transactions to a STDOUT in beancount format'
        )
    )
    
    parser.add_argument(
        '--root-file',
        metavar='STR', 
        help=(
            'specify the path to the root file for beancount'
        )
    )


    args = parser.parse_args()
    
    return args


def _update_transactions(client: plaid_api.PlaidApi):
    for item in PlaidItem.select():
        access_token = item.access_token
        cursor = item.cursor
        if cursor is None:        
            cursor = ''
        has_more = True
        
        while has_more:
            request = TransactionsSyncRequest(
                access_token=access_token,
                cursor=cursor,
                count=100,
            )
            
                
            response = client.transactions_sync(request)
            transactions = response['added']
            has_more = response['has_more']
            # Update cursor to the next cursor
            cursor = response['next_cursor']
            
            for transaction in transactions:
                print(transaction)
                if transaction['personal_finance_category'] is not None:            
                    category, created = FinanceCategory.get_or_create(
                        detailed=transaction['personal_finance_category']['detailed'],
                        defaults={'primary': transaction['personal_finance_category']['primary'], 'description': "Unknown (Plaid added a new category!)"}                
                    )
                    if created:
                        # Uh oh! Plaid added a new category...                
                        category.save()
                        
                    confidence = transaction['personal_finance_category']['confidence_level']
                    
                account, created = Account.get_or_create(
                    plaid_id=transaction['account_id'],
                    defaults={'name': "Unknown account found during Plaid sync!", 'item': item}            
                )
                if created:
                    account.save()
                        
                PlaidTransaction(
                    date=transaction['date'],
                    datetime=transaction['datetime'],
                    authorized_date=transaction['authorized_date'],
                    authorized_datetime=transaction['authorized_datetime'],        
                    name=transaction['name'],
                    merchant_name=transaction['merchant_name'],
                    website=transaction['website'],
                    amount=transaction['amount'],
                    check_number=transaction['check_number'],
                    transaction_id=transaction['transaction_id'],
                    account=account,
                    personal_finance_category=category,
                    personal_finance_confidence=confidence,
                    pending=transaction['pending']
                ).save()
                
            # Save the cursor for the next time we sync
            item.cursor = cursor
            item.save()
            print("No more transactions to sync for item {0}".format(item.item_id))
    

def _load_beancount_accounts(file_path):
    entries, errors, options = loader.load_file(file_path)
    # We want to pull out just the accounts and metadat
    accounts = [entry for entry in entries if isinstance(entry, core.data.Open)]
    
    short_names = {account.meta['short_name']: account.account for account in accounts if 'short_name' in account.meta}
    expense_accounts = {account.meta['plaid_category']: account.account for account in accounts if 'plaid_category' in account.meta}
    # convert accounts to a dict from plaid_id to account
    return short_names, expense_accounts

def main():
    args = _parse_args_and_load_config()
    
    # Specify the path to the TOML file
    file_path = "/Users/reitblatt/.config/plaid2text/config"

    # Read the contents of the TOML file
    config = configparser.ConfigParser()
    config.read(file_path)            

    # Load the beancount file
    bc_accounts, expense_accounts = _load_beancount_accounts(args.root_file)
    
    # update expense accounts with the new accounts
    for category in FinanceCategory.select():
        if category.detailed in expense_accounts:
            category.expense_account = expense_accounts[category.detailed]
        else:
            category.expense_account = None
        
        category.save()  

    # Get the Plaid configuration from the TOML file
    client_id = config["PLAID"]["client_id"]
    secret = config["PLAID"]["secret"]

    # Remove the Plaid configuration from the TOML file
    del config["PLAID"]

    for account_name in config.sections():
        access_token = config[account_name]["access_token"]
        item_id = config[account_name]["item_id"]
        account_id = config[account_name]["account"]
        
        # First, check if the parent item (institution) exists
        item, created = PlaidItem.get_or_create(
            item_id=item_id,
            defaults={'access_token': access_token,}
        )
        
        if created:
            item.save()                    
            
        if account_name in bc_accounts:
            beancount_account = bc_accounts[account_name]
        else:
            beancount_account = None
        account, created = Account.get_or_create(
            plaid_id=account_id,
            defaults={'name': account_name, 'item': item, 'beancount_name': beancount_account},        
        )
        if created:    
            account.save()
        else:
            # update the account name if it's changed
            if account.beancount_name != beancount_account:
                account.beancount_name = beancount_account
                account.save()
                            
    configuration = plaid.Configuration(
        host=plaid.Environment.Production,
        api_key={
            'clientId': client_id,
            'secret': secret,
        }
    )

    api_client = plaid.ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)
            
    if args.sync_all_transactions:
        _update_transactions(client)
    if args.output_transactions:
        # Print out new categories
        from beancount_renderer import BeancountRenderer
        # filter by date
        query = PlaidTransaction.select()
        if args.from_date is not None:
            query = query.where(PlaidTransaction.date >= args.from_date)
        if args.to_date is not None:
            query = query.where(PlaidTransaction.date <= args.to_date)
        
        query = query.order_by(PlaidTransaction.date)
        renderer = BeancountRenderer(query)
        for entry in renderer.print():
            print(entry)
        
        
        
if __name__ == '__main__':
    main()