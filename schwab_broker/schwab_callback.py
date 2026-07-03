from flask import Flask, request
import os
import base64
import requests
import json
import logging

from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "schwab.env")

app = Flask(__name__)

CLIENT_ID = os.environ["SCHWAB_CLIENT_ID"]
CLIENT_SECRET = os.environ["SCHWAB_CLIENT_SECRET"]
REDIRECT_URI = "https://tastydaytraders.com/callback"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

LOG_FILE = BASE_DIR / "callback.log"

handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(message)s"
))
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)

@app.route("/")
def home():
    auth_url = (
        "https://api.schwabapi.com/v1/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={requests.utils.quote(REDIRECT_URI, safe='')}"
        "&response_type=code"
    )
    app.logger.info("home hit from ip=%s", request.headers.get("X-Forwarded-For", request.remote_addr))
    app.logger.debug("generated auth_url=%s", auth_url)
    return f"""
    <h2>Schwab OAuth Test</h2>
    <p><a href="{auth_url}">Login to Schwab</a></p>
    <p>After login, Schwab should redirect back to <code>{REDIRECT_URI}</code>.</p>
    """

@app.route("/callback")
def callback():
    app.logger.info("callback hit")
    app.logger.debug("request.url=%s", request.url)
    app.logger.debug("request.args=%s", dict(request.args))

    error = request.args.get("error")
    if error:
        app.logger.error("oauth error received: %s", error)
        return f"OAuth error: {error}", 400

    code = request.args.get("code")
    if not code:
        app.logger.error("missing code; args=%s", dict(request.args))
        return f"Missing code. Query args received: {dict(request.args)}", 400

    app.logger.info("authorization code received, len=%s", len(code))

    basic_auth = base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode("utf-8")
    ).decode("utf-8")

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    app.logger.debug("posting token request to %s", TOKEN_URL)
    app.logger.debug("token request data=%s", {
        "grant_type": data["grant_type"],
        "code_preview": code[:12] + "...",
        "redirect_uri": data["redirect_uri"],
    })

    try:
        resp = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
        app.logger.info("token response status=%s", resp.status_code)
        app.logger.debug("token response headers=%s", dict(resp.headers))
        app.logger.debug("token raw response=%s", resp.text)

        try:
            payload = resp.json()
        except Exception as json_err:
            app.logger.exception("failed to parse token response json: %s", json_err)
            payload = {"raw_text": resp.text}

        return f"""
        <h2>Schwab Callback Received</h2>
        <p><strong>Authorization code received.</strong></p>
        <p>HTTP status from token endpoint: {resp.status_code}</p>
        <pre>{json.dumps(payload, indent=2)}</pre>
        """, resp.status_code

    except Exception as e:
        app.logger.exception("callback token exchange failed: %s", e)
        return f"""
        <h2>Callback Exception</h2>
        <pre>{str(e)}</pre>
        <p>Check callback.log on the server.</p>
        """, 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8001, debug=True)
