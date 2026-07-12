from flask import Flask, request
import os
import logging
import sys

from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "schwab.env")

# This file gets deployed both here and as a standalone copy at home/schwab_callback.py
# (that's where the systemd unit's WorkingDirectory + bare "schwab_callback:app" import
# actually looks). Make sure SchwabAuthManager.py is importable either way.
SCHWAB_BROKER_DIR = BASE_DIR / "schwab_broker" if (BASE_DIR / "schwab_broker").exists() else BASE_DIR
if str(SCHWAB_BROKER_DIR) not in sys.path:
    sys.path.insert(0, str(SCHWAB_BROKER_DIR))

from SchwabAuthManager import SchwabAuthManager, SchwabAuthError

app = Flask(__name__)

CLIENT_ID = os.environ["SCHWAB_CLIENT_ID"]
REDIRECT_URI = "https://tastydaytraders.com/callback"

LOG_FILE = BASE_DIR / "callback.log"

handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3)
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(message)s"
))
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Note: this used to run at DEBUG and logged the full raw token response (access_token,
# refresh_token, id_token) to callback.log in plaintext. Kept at INFO now -- this
# service must never write real token values anywhere except schwab_token.env.

@app.route("/")
def home():
    import requests
    auth_url = (
        "https://api.schwabapi.com/v1/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={requests.utils.quote(REDIRECT_URI, safe=chr(39))}"
        "&response_type=code"
    )
    app.logger.info("home hit from ip=%s", request.headers.get("X-Forwarded-For", request.remote_addr))
    return f"""
    <h2>Schwab OAuth Test</h2>
    <p><a href="{auth_url}">Login to Schwab</a></p>
    <p>After login, Schwab should redirect back to <code>{REDIRECT_URI}</code>.</p>
    """

@app.route("/callback")
def callback():
    app.logger.info("callback hit")

    error = request.args.get("error")
    if error:
        app.logger.error("oauth error received: %s", error)
        return f"OAuth error: {error}", 400

    code = request.args.get("code")
    if not code:
        app.logger.error("missing code; args=%s", dict(request.args))
        return f"Missing code. Query args received: {dict(request.args)}", 400

    app.logger.info("authorization code received, len=%s", len(code))

    # Route through the same SchwabAuthManager every other bot uses (BASE_DIR is
    # anchored to SchwabAuthManager.py's own location, so this always resolves to
    # schwab_broker/schwab.env + schwab_broker/schwab_token.env regardless of which
    # copy of this callback script is running). This is the actual fix: the old
    # version here did its own separate token-endpoint POST and just displayed the
    # raw JSON on the page -- it never touched schwab_token.env at all, which is why
    # the timestamps stayed stale after a manual reauth and why the raw JSON kept
    # getting hand-copied into notes (and leaking) instead.
    try:
        auth = SchwabAuthManager()
        payload = auth.exchange_authorization_code(code)
        app.logger.info(
            "token exchange succeeded, schwab_token.env updated, expires_in=%s",
            payload.get("expires_in"),
        )
        return f"""
        <h2>Schwab Callback Received</h2>
        <p><strong>Authorization code exchanged and schwab_token.env updated.</strong></p>
        <p>Token type: {auth.token_type} &nbsp;|&nbsp; expires in: {payload.get('expires_in', '?')}s</p>
        <p>Refreshed at: {auth.last_refreshed_at}</p>
        <p>Nothing to copy or paste -- you can close this tab.</p>
        """, 200
    except SchwabAuthError as e:
        app.logger.exception("token exchange failed: %s", e)
        return f"""
        <h2>Callback Exception</h2>
        <pre>{str(e)}</pre>
        <p>Check callback.log on the server.</p>
        """, 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=True)
