import os
import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "etrade.env")

CONSUMER_KEY = os.getenv("ETRADE_SANDBOX_KEY")
CONSUMER_SECRET = os.getenv("ETRADE_SANDBOX_SECRET")
ACCESS_TOKEN = os.getenv("ETRADE_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ETRADE_ACCESS_TOKEN_SECRET")

url = "https://apisb.etrade.com/v1/market/quote/ESU6"

auth = OAuth1(
    CONSUMER_KEY,
    client_secret=CONSUMER_SECRET,
    resource_owner_key=ACCESS_TOKEN,
    resource_owner_secret=ACCESS_TOKEN_SECRET,
    signature_method="HMAC-SHA1"
)

headers = {"Accept": "application/json"}

r = requests.get(url, auth=auth, headers=headers, timeout=30)
print(r.status_code)
print(r.text)
