#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import requests
from dotenv import load_dotenv

TOKEN_FILE_KEYS = [
    "SCHWAB_ACCESS_TOKEN",
    "SCHWAB_REFRESH_TOKEN",
    "SCHWAB_TOKEN_TYPE",
    "SCHWAB_SCOPE",
    "SCHWAB_ACCESS_TOKEN_EXPIRES_AT",
    "SCHWAB_LAST_REFRESHED_AT",
]


class SchwabQuoteTester:
    def __init__(self, debug: bool = False):
        self.base_dir = Path(__file__).resolve().parent
        self.config_file = self.base_dir / "schwab.env"
        self.token_file = self.base_dir / "schwab_token.env"
        self._configure_logging(debug)
        self._load_env()
        self.client_id = os.getenv("SCHWAB_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("SCHWAB_CLIENT_SECRET", "").strip()
        self.token_url = os.getenv("SCHWAB_TOKEN_URL", "https://api.schwabapi.com/v1/oauth/token").strip()
        self.marketdata_base_url = os.getenv("SCHWAB_MARKETDATA_BASE_URL", "https://api.schwabapi.com/marketdata/v1").strip().rstrip("/")
        self.access_token = os.getenv("SCHWAB_ACCESS_TOKEN", "").strip()
        self.refresh_token = os.getenv("SCHWAB_REFRESH_TOKEN", "").strip()
        self.token_type = os.getenv("SCHWAB_TOKEN_TYPE", "Bearer").strip() or "Bearer"
        self.scope = os.getenv("SCHWAB_SCOPE", "api").strip() or "api"
        self.access_token_expires_at = os.getenv("SCHWAB_ACCESS_TOKEN_EXPIRES_AT", "").strip()
        self.last_refreshed_at = os.getenv("SCHWAB_LAST_REFRESHED_AT", "").strip()

    def _configure_logging(self, debug: bool) -> None:
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stdout,
        )
        self.log = logging.getLogger("schwab_quote_test")

    def _load_env(self) -> None:
        if self.config_file.exists():
            load_dotenv(self.config_file)
        if self.token_file.exists():
            load_dotenv(self.token_file, override=True)

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _iso_utc(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _write_token_file(self) -> None:
        values = {
            "SCHWAB_ACCESS_TOKEN": self.access_token,
            "SCHWAB_REFRESH_TOKEN": self.refresh_token,
            "SCHWAB_TOKEN_TYPE": self.token_type,
            "SCHWAB_SCOPE": self.scope,
            "SCHWAB_ACCESS_TOKEN_EXPIRES_AT": self.access_token_expires_at,
            "SCHWAB_LAST_REFRESHED_AT": self.last_refreshed_at,
        }
        lines = [f"{k}={values.get(k, '')}" for k in TOKEN_FILE_KEYS]
        self.token_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.log.info("Updated %s", self.token_file)

    def _parse_expiry(self) -> datetime | None:
        if not self.access_token_expires_at:
            return None
        try:
            return datetime.fromisoformat(self.access_token_expires_at.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def refresh_access_token(self) -> None:
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Missing SCHWAB_CLIENT_ID or SCHWAB_CLIENT_SECRET in schwab.env")
        if not self.refresh_token:
            raise RuntimeError("Missing SCHWAB_REFRESH_TOKEN in schwab_token.env")

        self.log.info("Refreshing Schwab access token")
        response = requests.post(
            self.token_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Token refresh failed: HTTP {response.status_code} {response.text}")

        payload = response.json()
        self.access_token = payload.get("access_token", self.access_token)
        self.refresh_token = payload.get("refresh_token", self.refresh_token)
        self.token_type = payload.get("token_type", self.token_type) or self.token_type
        self.scope = payload.get("scope", self.scope) or self.scope

        expires_in = int(payload.get("expires_in", 1800))
        now = self._utc_now()
        self.last_refreshed_at = self._iso_utc(now)
        self.access_token_expires_at = self._iso_utc(now + timedelta(seconds=expires_in))
        self._write_token_file()

    def ensure_token(self) -> None:
        expiry = self._parse_expiry()
        now = self._utc_now()
        if not self.access_token:
            self.refresh_access_token()
            return
        if expiry is None:
            self.log.info("Access token expiry missing; attempting quote call first and refreshing on auth failure")
            return
        if now >= (expiry - timedelta(seconds=60)):
            self.log.info("Access token expired or near expiry at %s", self.access_token_expires_at)
            self.refresh_access_token()

    def fetch_quote(self, symbol: str) -> dict:
        url = f"{self.marketdata_base_url}/quotes"
        params = {"symbols": symbol}
        self.log.debug("GET %s params=%s", url, params)
        response = requests.get(url, headers=self._auth_headers(), params=params, timeout=30)

        if response.status_code in (401, 403):
            self.log.info("Quote auth failed for %s with HTTP %s; refreshing token and retrying once", symbol, response.status_code)
            self.refresh_access_token()
            response = requests.get(url, headers=self._auth_headers(), params=params, timeout=30)

        if response.status_code >= 400:
            raise RuntimeError(f"Quote request failed for {symbol}: HTTP {response.status_code} {response.text}")

        return response.json()


    def print_quote_old(self, symbol: str, payload: dict) -> None:
        item = payload.get(symbol) if isinstance(payload, dict) else None
        if not item and isinstance(payload, dict) and len(payload) == 1:
            item = next(iter(payload.values()))
        if not isinstance(item, dict):
            print(f"{symbol}: received payload but could not find normalized quote object")
            print(payload)
            return

        fields = {
            "symbol": item.get("symbol") or symbol,
            "assetMainType": item.get("assetMainType"),
            "assetSubType": item.get("assetSubType"),
            "quoteType": item.get("quoteType"),
            "description": item.get("description"),
            "bid": item.get("bidPrice") if item.get("bidPrice") is not None else item.get("bid"),
            "ask": item.get("askPrice") if item.get("askPrice") is not None else item.get("ask"),
            "last": item.get("lastPrice") if item.get("lastPrice") is not None else item.get("last"),
            "mark": item.get("mark"),
            "close": item.get("closePrice") if item.get("closePrice") is not None else item.get("close"),
            "netChange": item.get("netChange"),
            "totalVolume": item.get("totalVolume"),
        }

        print(f"\n=== {symbol} ===")
        for k, v in fields.items():
            print(f"{k}: {v}")

        if self.log.isEnabledFor(logging.DEBUG):
            print(json.dumps(payload, indent=2))

    def normalize_quote(self, symbol: str, payload: dict) -> dict:
        item = payload.get(symbol) if isinstance(payload, dict) else None
        if not item and isinstance(payload, dict) and len(payload) == 1:
            item = next(iter(payload.values()))
        if not isinstance(item, dict):
            return {
                "symbol": symbol,
                "error": "received payload but could not find normalized quote object",
                "raw": payload,
            }

        quote = item.get("quote", {}) or {}
        reference = item.get("reference", {}) or {}

        return {
            "symbol": item.get("symbol") or symbol,
            "assetMainType": item.get("assetMainType"),
            "assetSubType": item.get("assetSubType"),
            "quoteType": item.get("quoteType") or quote.get("quoteType"),
            "description": reference.get("description") or item.get("description"),
            "exchange": reference.get("exchangeName") or reference.get("exchange"),
            "bid": quote.get("bidPrice"),
            "ask": quote.get("askPrice"),
            "last": quote.get("lastPrice"),
            "mark": quote.get("mark"),
            "close": quote.get("closePrice"),
            "netChange": quote.get("netChange"),
            "totalVolume": quote.get("totalVolume"),
            "openPrice": quote.get("openPrice"),
            "highPrice": quote.get("highPrice"),
            "lowPrice": quote.get("lowPrice"),
            "securityStatus": quote.get("securityStatus"),
            "tradeTime": quote.get("tradeTime"),
        }

    def print_quote(self, symbol: str, payload: dict, short: bool = False) -> None:
        if short:
            fields = self.normalize_quote(symbol, payload)
            print(f"\n=== {symbol} ===")
            for k, v in fields.items():
                print(f"{k}: {v}")
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Schwab quotes for one or more tickers.")
    parser.add_argument("--tickers", nargs="+", default=["SPX"], help="One or more ticker symbols. Default: SPX")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging to stdout")
    parser.add_argument("--short", action="store_true", help="Print normalized summary instead of full JSON payload")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tester = SchwabQuoteTester(debug=args.debug)

    try:
        tester.ensure_token()
        for ticker in args.tickers:
            payload = tester.fetch_quote(ticker)
            tester.print_quote(ticker, payload, short=args.short)
        return 0
    except Exception as exc:
        tester.log.exception("schwab_quote_test failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

