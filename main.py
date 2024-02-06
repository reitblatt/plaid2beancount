import plaid
from plaid.api import plaid_api
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from beancount import loader
from models import *
import configparser


# Specify the path to the TOML file
file_path = "/Users/reitblatt/.config/plaid2text/config"

# Read the contents of the TOML file
config = configparser.ConfigParser()   
config.read(file_path)            

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
        defaults={'access_token': access_token, }        
    )
    
    if created:
        item.save()
        
    account, created = Account.get_or_create(
        plaid_id=account_id,
        defaults={'name': account_name, 'item': item},        
    )
    if created:    
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