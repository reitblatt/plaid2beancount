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

def fetch_investments(client: plaid_api.PlaidApi, start_date=None, end_date=None):
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
            # print(transaction)
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


def fetch_transactions(client: plaid_api.PlaidApi):
    new_transactions = []
    updated_accounts = set()
    for item in PlaidItem.objects.all():
        print("About to update transactions for item {0}".format(item.item_id))
        access_token = item.access_token
        cursor = item.cursor
        if cursor is None:
            cursor = ""
        has_more = True
        try:
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
                    #print(transaction)                
                        
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
        except plaid.ApiException as e:
            print(e)
            print(
                "Error getting transactions for item {0}".format(
                    item.item_id
                )
            )
            continue
    return new_transactions
           