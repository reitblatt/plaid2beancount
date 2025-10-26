from celery import shared_task
from .plaid_fetch import fetch_investments, fetch_transactions
from .config import load_config_file

import plaid
from plaid.api import plaid_api
from plaid.configuration import Configuration, Environment
from plaid.api_client import ApiClient

@shared_task
def fetch_data():
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
    print(f"fetched {new_transactions.length()} transactions")
    new_investment_transactions = fetch_investments(client)
    print(f"fetched {new_investment_transactions.length()} investment transactions")
