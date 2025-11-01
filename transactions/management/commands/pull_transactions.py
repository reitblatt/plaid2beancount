from . import AccountsCommand
from beancount import loader, core
import configparser
from transactions.models import FinanceCategory, PlaidItem, Account
import plaid
from plaid.api import plaid_api
from plaid.configuration import Configuration, Environment
from plaid.api_client import ApiClient

try:
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
except ImportError:
    from plaid.models import TransactionsSyncRequest

class Command(AccountsCommand):
    help = 'Pull transactions from Plaid and load them into the database'

    def add_arguments(self, parser):
        super().add_arguments(parser)                
                
        
    def _load_beancount_accounts(self, file_path):
        entries, errors, options = loader.load_file(file_path)
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
    
    def _update_transactions(self, client: plaid_api.PlaidApi):
        for item in PlaidItem.select():
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
                    if transaction["personal_finance_category"] is not None:
                        category, created = FinanceCategory.get_or_create(
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

                    account, created = Account.get_or_create(
                        plaid_id=transaction["account_id"],
                        defaults={
                            "name": "Unknown account found during Plaid sync!",
                            "item": item,
                        },
                    )
                    if created:
                        account.save()

                    PlaidTransaction(
                        date=transaction["date"],
                        datetime=transaction["datetime"],
                        authorized_date=transaction["authorized_date"],
                        authorized_datetime=transaction["authorized_datetime"],
                        name=transaction["name"],
                        merchant_name=transaction["merchant_name"],
                        website=transaction["website"],
                        amount=transaction["amount"],
                        check_number=transaction["check_number"],
                        transaction_id=transaction["transaction_id"],
                        account=account,
                        personal_finance_category=category,
                        personal_finance_confidence=confidence,
                        pending=transaction["pending"],
                    ).save()

                # Save the cursor for the next time we sync
                item.cursor = cursor
                item.save()
                print("No more transactions to sync for item {0}".format(item.item_id))

    def handle(self, *args, **options):
        
        # Specify the path to the TOML file
        file_path = "/Users/reitblatt/.config/plaid2text/config"

        # Read the contents of the TOML file
        config = configparser.ConfigParser()
        config.read(file_path)

        root_file = args.root_file
        if root_file is None:
            root_file = config["BEANCOUNT"]["root_file"]

        del config["BEANCOUNT"]

        # Load the beancount file
        bc_accounts, expense_accounts = self._load_beancount_accounts(root_file)

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
            account, created = Account.get_or_create(
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

        configuration = Configuration(
            host=Environment.Production,
            api_key={
                "clientId": client_id,
                "secret": secret,
            },
        )

        api_client = ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)

    
        self._update_transactions(client)
        # _update_investments(client)        