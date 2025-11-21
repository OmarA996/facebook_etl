import os
from dotenv import load_dotenv

# Load variables from .env file in project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")

if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_API_VERSION = os.getenv("META_API_VERSION", "v21.0")
META_AD_ACCOUNT_IDS = [
    acc.strip()
    for acc in os.getenv("META_AD_ACCOUNT_IDS", "").split(",")
    if acc.strip()
]

BASE_META_URL = f"https://graph.facebook.com/{META_API_VERSION}"

DB_CONN_STRING = os.getenv("DB_CONN_STRING", "")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
