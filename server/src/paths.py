import os


SERVER_DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data')
)
CONFIG_PATH = os.path.join(SERVER_DATA_DIR, 'config.json')
BAN_STATE_PATH = os.path.join(SERVER_DATA_DIR, 'banned_ips.json')
