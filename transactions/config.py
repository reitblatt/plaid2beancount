import configparser
import os

def load_config_file():
    # Specify the path to the TOML file
    file_path = "~/.config/plaid2text/config"
    full_path = os.path.expanduser(file_path)

    # Read the contents of the TOML file
    config = configparser.ConfigParser()
    config.read(full_path)
    
    return config