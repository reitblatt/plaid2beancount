from flask import Flask, request, render_template_string, jsonify
import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
import configparser
import os
import json

app = Flask(__name__)

# Load config
config = configparser.ConfigParser()
config.read(os.path.expanduser("~/.config/plaid2text/config"))

# Initialize Plaid client
configuration = plaid.Configuration(
    host=plaid.Environment.Production,
    api_key={
        "clientId": config["PLAID"]["client_id"],
        "secret": config["PLAID"]["secret"],
    },
)
api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

# HTML template for the update mode page
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Plaid Link Update Mode</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        .success { color: green; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>Plaid Link Update Mode</h1>
    <p>Please update your credentials for:</p>
    <ul>
    {% for item in items %}
        <li id="item-{{ item.item_id }}">{{ item.name }} ({{ item.item_id }})</li>
    {% endfor %}
    </ul>
    <div id="status"></div>
    <button id="link-button">Update Credentials</button>
    <br><br>
    <button id="refresh" onclick="window.location.reload()">Check Next Item</button>

    <script>
        const handler = Plaid.create({
            token: '{{ link_token }}',
            onSuccess: async (public_token, metadata) => {
                document.getElementById('status').innerHTML = 'Updating access token...';
                try {
                    const response = await fetch('/exchange_token', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            public_token: public_token,
                            item_id: metadata.item_id
                        })
                    });
                    const result = await response.json();
                    if (result.success) {
                        document.getElementById('status').className = 'success';
                        document.getElementById('status').innerHTML = 'Successfully updated credentials! Click "Check Next Item" to continue.';
                        document.getElementById('link-button').style.display = 'none';
                    } else {
                        document.getElementById('status').className = 'error';
                        document.getElementById('status').innerHTML = 'Error updating credentials: ' + result.error;
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
            },
            onEvent: (eventName, metadata) => {
                console.log('onEvent', eventName, metadata);
            }
        });

        document.getElementById('link-button').onclick = () => {
            document.getElementById('status').innerHTML = '';
            handler.open();
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    # Get items that need reauthorization
    items = []
    try:
        # Get all items from the config
        for section in config.sections():
            if section not in ["PLAID", "BEANCOUNT"]:
                item_id = config[section]["item_id"]
                access_token = config[section]["access_token"]
                
                try:
                    # Try to get account information
                    accounts_request = plaid.model.accounts_get_request.AccountsGetRequest(
                        access_token=access_token
                    )
                    client.accounts_get(accounts_request)
                except plaid.ApiException as e:
                    if e.status == 400 and "ITEM_LOGIN_REQUIRED" in str(e):
                        items.append({
                            "name": section,
                            "item_id": item_id,
                            "access_token": access_token
                        })
    except Exception as e:
        print(f"Error getting items: {e}")
    
    if not items:
        return "No items need reauthorization."
    
    # Create link token for update mode
    try:
        link_token_request = plaid.model.link_token_create_request.LinkTokenCreateRequest(
            user={"client_user_id": "user-id"},
            client_name="Plaid2Beancount",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
            access_token=items[0]["access_token"],  # Update the first item that needs reauthorization
            update={
                "account_selection_enabled": False  # Don't allow changing account selection
            }
        )
        link_token_response = client.link_token_create(link_token_request)
        link_token = link_token_response["link_token"]
        current_item = items[0]  # Keep track of which item we're updating
    except Exception as e:
        print(f"Error creating link token: {e}")
        return f"Error creating link token: {e}"
    
    return render_template_string(HTML_TEMPLATE, items=[current_item], link_token=link_token)

@app.route('/exchange_token', methods=['POST'])
def exchange_token():
    data = request.get_json()
    public_token = data.get('public_token')
    item_id = data.get('item_id')
    
    try:
        # Exchange public token for access token
        exchange_request = plaid.model.item_public_token_exchange_request.ItemPublicTokenExchangeRequest(
            public_token=public_token
        )
        exchange_response = client.item_public_token_exchange(exchange_request)
        new_access_token = exchange_response["access_token"]
        
        # Get the item details to match with config
        item_request = plaid.model.item_get_request.ItemGetRequest(
            access_token=new_access_token
        )
        item_response = client.item_get(item_request)
        new_item_id = item_response["item"]["item_id"]
        
        # Update the access token in the config
        for section in config.sections():
            if section not in ["PLAID", "BEANCOUNT"]:
                if config[section]["item_id"] == new_item_id:
                    config[section]["access_token"] = new_access_token
                    with open(os.path.expanduser("~/.config/plaid2text/config"), 'w') as f:
                        config.write(f)
                    return jsonify({"success": True})
        
        return jsonify({"success": False, "error": f"Item not found in config. New item_id: {new_item_id}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(port=5000) 