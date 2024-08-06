import configparser

def load_config_file():
    # Specify the path to the TOML file
    file_path = "/Users/reitblatt/.config/plaid2text/config"

    # Read the contents of the TOML file
    config = configparser.ConfigParser()
    config.read(file_path)
    
    return config