import os

from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "etrade.env")

CONSUMER_KEY = os.getenv("ETRADE_SANDBOX_KEY")
CONSUMER_SECRET = os.getenv("ETRADE_SANDBOX_SECRET")

REQUEST_TOKEN_URL = "https://apisb.etrade.com/oauth/request_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
ACCESS_TOKEN_URL = "https://apisb.etrade.com/oauth/access_token"

def main():
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        callback_uri="oob"
    )

    fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    resource_owner_key = fetch_response.get("oauth_token")
    resource_owner_secret = fetch_response.get("oauth_token_secret")

    print("Request token OK")
    print("oauth_token:", resource_owner_key)
    print("oauth_token_secret:", resource_owner_secret)
    print()
    print("Open this URL in your browser:")
    print(f"{AUTHORIZE_URL}?key={CONSUMER_KEY}&token={resource_owner_key}")
    print()
    verifier = input("Paste verifier code here: ").strip()

    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )

    access_tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)
    print("\nAccess token OK")
    print(access_tokens)

if __name__ == "__main__":
    main()
