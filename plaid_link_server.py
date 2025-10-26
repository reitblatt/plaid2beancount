from flask import Flask, request, render_template_string, jsonify
import plaid
from plaid.api import plaid_api
from plaid.configuration import Configuration, Environment
from plaid.api_client import ApiClient

try:
    from plaid.model.country_code import CountryCode
    from plaid.model.products import Products
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_update import LinkTokenCreateRequestUpdate
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.accounts_get_request import AccountsGetRequest
except ImportError:
    # Newer SDK uses different import paths
    from plaid.models import CountryCode
    from plaid.models import Products
    from plaid.models import LinkTokenCreateRequest
    from plaid.models import LinkTokenCreateRequestUpdate
    from plaid.models import ItemPublicTokenExchangeRequest
    from plaid.models import AccountsGetRequest

import configparser
import os
import json
import argparse
import sys

from beancount import loader
from beancount.core.data import Open

# Global variables (will be set by command-line args)
config = None
client = None
root_file = None

def load_config_and_client(config_file):
    """Load config and initialize Plaid client."""
    global config, client
    config = configparser.ConfigParser()
    config.read(os.path.expanduser(config_file))

    configuration = Configuration(
        host=Environment.Production,
        api_key={
            "clientId": config["PLAID"]["client_id"],
            "secret": config["PLAID"]["secret"],
        },
    )
    api_client = ApiClient(configuration)
    client = plaid_api.PlaidApi(api_client)

def get_plaid_items_from_beancount(beancount_file):
    """Extract Plaid items from beancount file.

    Returns:
        Dict mapping item_id to (account_name, access_token, short_name)
    """
    entries, _, _ = loader.load_file(beancount_file)
    accounts = [entry for entry in entries if isinstance(entry, Open)]

    items = {}
    for account in accounts:
        if "plaid_item_id" in account.meta and "plaid_access_token" in account.meta:
            item_id = account.meta["plaid_item_id"]
            access_token = account.meta["plaid_access_token"]
            short_name = account.meta.get("short_name", account.account)
            items[item_id] = (account.account, access_token, short_name)

    return items

def update_access_token_in_beancount(beancount_file, account_name, new_access_token):
    """Update the access token for an account in the beancount file."""
    with open(beancount_file, 'r') as f:
        lines = f.readlines()

    new_lines = []
    in_account = False
    account_indent = ""

    for line in lines:
        # Check if this line opens the account we're looking for
        if f"open {account_name}" in line:
            in_account = True
            new_lines.append(line)
            # Determine the indentation used for metadata
            account_indent = "  "
        elif in_account:
            # Check if we're still in the account's metadata section
            if line.strip() and not line.startswith(account_indent) and not line.startswith("  "):
                # We've left the account section
                in_account = False
                new_lines.append(line)
            elif "plaid_access_token:" in line:
                # Replace the access token
                new_lines.append(f'{account_indent}plaid_access_token: "{new_access_token}"\n')
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(beancount_file, 'w') as f:
        f.writelines(new_lines)

    print(f"Updated access token for {account_name} in {beancount_file}")

app = Flask(__name__)

# HTML template for the update mode page
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Update Plaid Permissions</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .success { color: green; font-weight: bold; }
        .error { color: red; font-weight: bold; }
        button { padding: 10px 20px; font-size: 16px; cursor: pointer; margin: 10px 0; }
        ul { list-style-type: none; padding: 0; }
        li { margin: 10px 0; padding: 10px; background-color: #f5f5f5; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>Update Plaid Permissions</h1>
    {% if items %}
        <p>Items that need reauthorization:</p>
        <ul>
        {% for item in items %}
            <li>
                <strong>{{ item.short_name }}</strong> ({{ item.account_name }})<br>
                <small>Item ID: {{ item.item_id }}</small>
            </li>
        {% endfor %}
        </ul>
        <div id="status"></div>
        <button id="link-button">Update Credentials</button>
        <br>
        <button id="refresh" onclick="window.location.reload()">Check Next Item</button>
    {% else %}
        <p>No items need reauthorization.</p>
    {% endif %}

    <script>
        {% if link_token %}
        const handler = Plaid.create({
            token: '{{ link_token }}',
            onSuccess: async (public_token, metadata) => {
                document.getElementById('status').innerHTML = 'Updating access token...';
                try {
                    const response = await fetch('/exchange_token', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            public_token: public_token,
                            item_id: metadata.item_id,
                            account_name: '{{ current_item.account_name }}'
                        })
                    });
                    const result = await response.json();
                    if (result.success) {
                        document.getElementById('status').className = 'success';
                        document.getElementById('status').innerHTML = 'Successfully updated credentials! Click "Check Next Item" to continue.';
                        document.getElementById('link-button').style.display = 'none';
                    } else {
                        document.getElementById('status').className = 'error';
                        document.getElementById('status').innerHTML = 'Error: ' + result.error;
                    }
                } catch (error) {
                    document.getElementById('status').className = 'error';
                    document.getElementById('status').innerHTML = 'Error: ' + error;
                }
            },
            onExit: (err, metadata) => {
                if (err != null) {
                    document.getElementById('status').className = 'error';
                    document.getElementById('status').innerHTML = 'Error: ' + err.error_message;
                }
            }
        });

        document.getElementById('link-button').onclick = () => {
            document.getElementById('status').innerHTML = '';
            handler.open();
        };
        {% endif %}
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    # Get items that need reauthorization
    items_needing_auth = []

    try:
        # Get all items from beancount file
        all_items = get_plaid_items_from_beancount(root_file)

        for item_id, (account_name, access_token, short_name) in all_items.items():
            try:
                # Try to get account information to check if reauth is needed
                accounts_request = AccountsGetRequest(
                    access_token=access_token
                )
                client.accounts_get(accounts_request)
            except plaid.ApiException as e:
                if e.status == 400 and "ITEM_LOGIN_REQUIRED" in str(e):
                    items_needing_auth.append({
                        "item_id": item_id,
                        "account_name": account_name,
                        "access_token": access_token,
                        "short_name": short_name
                    })
                else:
                    print(f"Error checking item {short_name}: {e}")
    except Exception as e:
        print(f"Error getting items: {e}")
        return f"Error loading items from {root_file}: {e}"

    if not items_needing_auth:
        return render_template_string(HTML_TEMPLATE, items=[], link_token=None)

    # Create link token for update mode (for the first item needing auth)
    try:
        current_item = items_needing_auth[0]
        link_token_request = LinkTokenCreateRequest(
            user={"client_user_id": "user-id"},
            client_name="Plaid2Beancount",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
            access_token=current_item["access_token"],
            update=LinkTokenCreateRequestUpdate(
                account_selection_enabled=False
            )
        )
        link_token_response = client.link_token_create(link_token_request)
        link_token = link_token_response["link_token"]
    except Exception as e:
        print(f"Error creating link token: {e}")
        return f"Error creating link token: {e}"

    return render_template_string(
        HTML_TEMPLATE,
        items=items_needing_auth,
        link_token=link_token,
        current_item=current_item
    )

@app.route('/exchange_token', methods=['POST'])
def exchange_token():
    data = request.get_json()
    public_token = data.get('public_token')
    account_name = data.get('account_name')

    try:
        # Exchange public token for access token
        exchange_request = ItemPublicTokenExchangeRequest(
            public_token=public_token
        )
        exchange_response = client.item_public_token_exchange(exchange_request)
        new_access_token = exchange_response["access_token"]

        # Update the beancount file
        update_access_token_in_beancount(root_file, account_name, new_access_token)

        return jsonify({"success": True})
    except Exception as e:
        print(f"Error exchanging token: {e}")
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plaid Link Update Server')
    parser.add_argument(
        '--root-file',
        required=True,
        help='Path to the root beancount file'
    )
    parser.add_argument(
        '--config-file',
        default='~/.config/plaid2text/config',
        help='Path to the config file (default: ~/.config/plaid2text/config)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port to run the server on (default: 5000)'
    )

    args = parser.parse_args()

    # Set global root_file
    root_file = args.root_file

    # Load config and initialize client
    load_config_and_client(args.config_file)

    print(f"Starting Plaid Link Update Server on port {args.port}")
    print(f"Using root file: {root_file}")
    print(f"Open http://localhost:{args.port} in your browser")

    app.run(port=args.port, debug=False) 