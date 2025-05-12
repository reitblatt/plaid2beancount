import configparser
import os
from datetime import date
from beancount.core.data import Custom
from beancount.parser import printer
from beancount.parser import parser
from beancount.core import data
from typing import Dict, List, Tuple

def _get_account_name(config_section: str) -> str:
    """Convert config section name to Beancount account name."""
    # Remove any special characters and convert to title case
    name = config_section.replace('_', ' ').title()
    # Add appropriate prefix based on the section name
    if 'checking' in config_section.lower():
        return f"Assets:Checking:{name}"
    elif 'savings' in config_section.lower():
        return f"Assets:Savings:{name}"
    elif 'cd' in config_section.lower():
        return f"Assets:CD:{name}"
    elif 'card' in config_section.lower():
        return f"Liabilities:Credit-Card:{name}"
    elif 'ira' in config_section.lower():
        return f"Assets:Investment:IRA:{name}"
    elif 'brokerage' in config_section.lower():
        return f"Assets:Investment:Brokerage:{name}"
    else:
        return f"Assets:{name}"

def migrate_cursors(config_path: str, root_file: str):
    """Migrate cursors from config file to a new Beancount file."""
    # Load config
    config = configparser.ConfigParser()
    config.read(config_path)
    
    # Create cursor directives
    cursor_directives = []
    
    # Process each section in config
    for section in config.sections():
        if section not in ["PLAID", "BEANCOUNT"]:
            item_id = config[section]["item_id"]
            cursor = config[section].get("cursor", "")
            
            if cursor:
                account_name = _get_account_name(section)
                cursor_directive = Custom(
                    date=date.today(),
                    meta={"plaid_transaction_id": f"cursor_{date.today()}"},
                    type="plaid_cursor",
                    values=[(account_name, "string"), (cursor, "string"), (item_id, "string")]
                )
                cursor_directives.append(cursor_directive)
    
    # Write cursor directives to a new file
    cursors_file = os.path.join(os.path.dirname(root_file), "plaid_cursors.beancount")
    
    # Generate content directly
    content = []
    for directive in cursor_directives:
        # Format the directive as a string
        directive_str = f"{directive.date} custom \"{directive.type}\""
        for value, _ in directive.values:
            directive_str += f" \"{value}\""
        directive_str += "\n"
        for key, value in directive.meta.items():
            directive_str += f"  {key}: \"{value}\"\n"
        content.append(directive_str)
    
    # Write to file
    with open(cursors_file, 'w') as f:
        f.write(''.join(content))
    
    print(f"Successfully migrated {len(cursor_directives)} cursors to {cursors_file}")
    print(f"Please add 'include \"plaid_cursors.beancount\"' to your root file.")

if __name__ == "__main__":
    config_path = os.path.expanduser("~/.config/plaid2text/config")
    root_file = os.path.expanduser("~/Dropbox/Documents/Statements/beancount/reitblatt.beancount")
    migrate_cursors(config_path, root_file) 