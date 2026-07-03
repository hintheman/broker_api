#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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

INDEX_MAPPING = {
    "SPX": "$SPX",
    "$SPX": "$SPX",
    "NDX": "$NDX",
    "$NDX": "$NDX",
}

QUARTERLY_FUTURES = {"ES", "NQ", "MES", "MNQ"}
MONTHLY_FUTURES = {"CL", "MCL", "GC", "MGC"}

MONTH_CODES = {
    1: "F",
    2: "G",
    3: "H",
    4: "J",
    5: "K",
    6: "M",
    7: "N",
    8: "Q",
    9: "U",
    10: "V",
    11: "X",
    12: "Z",
}

VALID_CONTRACT_TYPES = {"ALL", "CALL", "PUT"}
VALID_RANGES = {"ALL", "ITM", "NTM", "OTM", "SAK", "SBK", "SNK"}
VALID_EXP_MONTHS = {"ALL", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}


def quarter_contract_month(month: int) -> int:
    if month <= 3:
        return 3
    if month <= 6:
        return 6
    if month <= 9:
        return 9
    return 12


def resolve_futures_symbol(root: str, as_of: date | None = None) -> str:
    """
    Resolve a plain futures root into a Schwab-style current contract symbol.

    Quarterly products:
      ES, NQ, MES, MNQ -> use current quarter month H/M/U/Z

    Monthly products:
      CL, MCL, GC, MGC -> use current calendar month

    Schwab futures symbol format is:
      / + root + month code + year code
    """
    as_of = as_of or date.today()
    root = root.strip().upper()

    if root in QUARTERLY_FUTURES:
        contract_month = quarter_contract_month(as_of.month)
        contract_year = as_of.year
        return f"/{root}{MONTH_CODES[contract_month]}{contract_year % 100:02d}"

    if root in MONTHLY_FUTURES:
        contract_month = as_of.month
        contract_year = as_of.year
        return f"/{root}{MONTH_CODES[contract_month]}{contract_year % 100:02d}"

    return root


def symbol_mapping(symbol: str, as_of: date | None = None) -> str:
    """
    Normalize user-friendly symbols into Schwab-specific symbols.

    Stocks/ETFs:
      AAPL -> AAPL
      SPY  -> SPY

    Indexes:
      SPX  -> $SPX
      NDX  -> $NDX

    Futures roots:
      ES   -> /ESU26  (example)
      NQ   -> /NQU26  (example)
      MES  -> /MESU26
      MNQ  -> /MNQU26
      CL   -> /CLN26  (example, current month logic)
      MCL  -> /MCLN26
      GC   -> /GCN26
      MGC  -> /MGCN26
    """
    s = symbol.strip().upper()

    if s in INDEX_MAPPING:
        return INDEX_MAPPING[s]

    if s in QUARTERLY_FUTURES or s in MONTHLY_FUTURES:
        return resolve_futures_symbol(s, as_of=as_of)

    return s


class SchwabOptionChainClient:
    def __init__(self, debug: bool = False):
        self.base_dir = Path(__file__).resolve().parent
        self.config_file = self.base_dir / "schwab.env"
        self.token_file = self.base_dir / "schwab_token.env"
        self._configure_logging(debug)
        self._load_env()

        self.client_id = os.getenv("SCHWAB_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("SCHWAB_CLIENT_SECRET", "").strip()
        self.token_url = os.getenv(
            "SCHWAB_TOKEN_URL",
            "https://api.schwabapi.com/v1/oauth/token",
        ).strip()
        self.marketdata_base_url = os.getenv(
            "SCHWAB_MARKETDATA_BASE_URL",
            "https://api.schwabapi.com/marketdata/v1",
        ).strip().rstrip("/")

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
        self.log = logging.getLogger("schwab_option_chain")

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
            self.log.info("Access token expiry missing; attempting option chain call first and refreshing on auth failure")
            return
        if now >= (expiry - timedelta(seconds=60)):
            self.log.info("Access token expired or near expiry at %s", self.access_token_expires_at)
            self.refresh_access_token()

    def _validate_contract_type(self, contract_type: str) -> str:
        value = contract_type.strip().upper()
        if value not in VALID_CONTRACT_TYPES:
            raise ValueError(f"Invalid --contract-type '{contract_type}'. Valid values: {sorted(VALID_CONTRACT_TYPES)}")
        return value

    def _validate_range(self, strike_range: str) -> str:
        value = strike_range.strip().upper()
        if value not in VALID_RANGES:
            raise ValueError(f"Invalid --range '{strike_range}'. Valid values: {sorted(VALID_RANGES)}")
        return value

    def _validate_exp_month(self, exp_month: str) -> str:
        value = exp_month.strip().upper()
        if value not in VALID_EXP_MONTHS:
            raise ValueError(f"Invalid --exp-month '{exp_month}'. Valid values: {sorted(VALID_EXP_MONTHS)}")
        return value

    def fetch_option_chain(
        self,
        symbol: str,
        dte_min: int,
        dte_max: int,
        strikes: str,
        contract_type: str = "ALL",
        strike_range: str = "ALL",
        exp_month: str = "ALL",
    ) -> dict:
        normalized_symbol = symbol_mapping(symbol, as_of=date.today())
        contract_type = self._validate_contract_type(contract_type)
        strike_range = self._validate_range(strike_range)
        exp_month = self._validate_exp_month(exp_month)

        today = date.today()
        params = {
            "symbol": normalized_symbol,
            "includeUnderlyingQuote": "true",
            "strategy": "SINGLE",
            "contractType": contract_type,
            "fromDate": (today + timedelta(days=dte_min)).isoformat(),
            "toDate": (today + timedelta(days=dte_max)).isoformat(),
        }

        if strike_range != "ALL":
            params["range"] = strike_range

        if exp_month != "ALL":
            params["expMonth"] = exp_month

        if str(strikes).lower() != "all":
            params["strikeCount"] = int(strikes)

        url = f"{self.marketdata_base_url}/chains"
        self.log.info("Fetching option chain for requested=%s normalized=%s", symbol, normalized_symbol)
        self.log.debug("GET %s params=%s", url, params)

        response = requests.get(url, headers=self._auth_headers(), params=params, timeout=45)

        if response.status_code in (401, 403):
            self.log.info(
                "Option chain auth failed for %s with HTTP %s; refreshing token and retrying once",
                normalized_symbol,
                response.status_code,
            )
            self.refresh_access_token()
            response = requests.get(url, headers=self._auth_headers(), params=params, timeout=45)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Option chain request failed for requested={symbol} normalized={normalized_symbol}: "
                f"HTTP {response.status_code} {response.text}"
            )

        return response.json()

    def _flatten_map(self, exp_date_map: dict, put_call: str) -> list[dict]:
        rows = []
        if not isinstance(exp_date_map, dict):
            return rows

        for exp_key, strike_map in exp_date_map.items():
            exp_date = exp_key.split(":")[0]
            dte = None
            if ":" in exp_key:
                try:
                    dte = int(exp_key.split(":")[1])
                except ValueError:
                    dte = None

            if not isinstance(strike_map, dict):
                continue

            for strike_key, contracts in strike_map.items():
                if not isinstance(contracts, list):
                    continue

                for contract in contracts:
                    if not isinstance(contract, dict):
                        continue

                    rows.append({
                        "symbol": contract.get("symbol"),
                        "putCall": contract.get("putCall") or put_call,
                        "description": contract.get("description"),
                        "expirationDate": exp_date,
                        "daysToExpiration": contract.get("daysToExpiration", dte),
                        "strikePrice": contract.get("strikePrice", strike_key),
                        "bid": contract.get("bid"),
                        "ask": contract.get("ask"),
                        "last": contract.get("last"),
                        "mark": contract.get("mark"),
                        "bidSize": contract.get("bidSize"),
                        "askSize": contract.get("askSize"),
                        "highPrice": contract.get("highPrice"),
                        "lowPrice": contract.get("lowPrice"),
                        "openPrice": contract.get("openPrice"),
                        "closePrice": contract.get("closePrice"),
                        "totalVolume": contract.get("totalVolume"),
                        "openInterest": contract.get("openInterest"),
                        "volatility": contract.get("volatility"),
                        "delta": contract.get("delta"),
                        "gamma": contract.get("gamma"),
                        "theta": contract.get("theta"),
                        "vega": contract.get("vega"),
                        "rho": contract.get("rho"),
                        "timeValue": contract.get("timeValue"),
                        "intrinsicValue": contract.get("intrinsicValue"),
                        "theoreticalOptionValue": contract.get("theoreticalOptionValue"),
                        "theoreticalVolatility": contract.get("theoreticalVolatility"),
                        "inTheMoney": contract.get("inTheMoney"),
                        "mini": contract.get("mini"),
                        "nonStandard": contract.get("nonStandard"),
                        "raw": contract,
                    })
        return rows

    def normalize_chain(self, requested_symbol: str, payload: dict) -> dict:
        normalized_symbol = symbol_mapping(requested_symbol, as_of=date.today())
        call_rows = self._flatten_map(payload.get("callExpDateMap", {}), "CALL")
        put_rows = self._flatten_map(payload.get("putExpDateMap", {}), "PUT")

        return {
            "requestedSymbol": requested_symbol,
            "normalizedSymbol": normalized_symbol,
            "status": payload.get("status"),
            "underlying": {
                "symbol": payload.get("symbol"),
                "underlyingPrice": payload.get("underlyingPrice"),
                "interestRate": payload.get("interestRate"),
                "volatility": payload.get("volatility"),
                "daysToExpiration": payload.get("daysToExpiration"),
                "numberOfContracts": payload.get("numberOfContracts"),
                "assetMainType": payload.get("assetMainType"),
                "assetSubType": payload.get("assetSubType"),
                "isDelayed": payload.get("isDelayed"),
                "underlying": payload.get("underlying"),
            },
            "calls": call_rows,
            "puts": put_rows,
            "callCount": len(call_rows),
            "putCount": len(put_rows),
        }

    def print_chain(self, symbol: str, payload: dict, short: bool = False) -> None:
        if short:
            print(json.dumps(self.normalize_chain(symbol, payload), indent=2, sort_keys=True))
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Schwab option chains for one or more tickers.")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=["$SPX"],
        help="One or more ticker symbols. Default: $SPX",
    )
    parser.add_argument(
        "--dte",
        nargs=2,
        type=int,
        metavar=("MIN", "MAX"),
        default=[0, 45],
        help="DTE range as MIN MAX. Default: 0 45",
    )
    parser.add_argument(
        "--strikes",
        default="50",
        help="Strike count above/below ATM, or 'all'. Default: 50",
    )
    parser.add_argument(
        "--contract-type",
        choices=["ALL", "CALL", "PUT"],
        default="ALL",
        help="Contract type filter. Default: ALL",
    )
    parser.add_argument(
        "--range",
        default="ALL",
        help="Strike range filter such as ALL, ITM, NTM, OTM, SAK, SBK, SNK. Default: ALL",
    )
    parser.add_argument(
        "--exp-month",
        default="ALL",
        help="Expiration month filter: ALL, JAN, FEB, MAR, APR, MAY, JUN, JUL, AUG, SEP, OCT, NOV, DEC",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--short", action="store_true", help="Print normalized summary instead of full JSON payload")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = SchwabOptionChainClient(debug=args.debug)

    try:
        dte_min, dte_max = args.dte
        if dte_min > dte_max:
            raise ValueError("--dte MIN cannot be greater than MAX")

        if str(args.strikes).lower() != "all":
            strike_count = int(args.strikes)
            if strike_count < 1:
                raise ValueError("--strikes must be 'all' or an integer >= 1")

        client.ensure_token()

        for ticker in args.tickers:
            payload = client.fetch_option_chain(
                symbol=ticker,
                dte_min=dte_min,
                dte_max=dte_max,
                strikes=args.strikes,
                contract_type=args.contract_type,
                strike_range=args.range,
                exp_month=args.exp_month,
            )
            client.print_chain(ticker, payload, short=args.short)

        return 0
    except Exception as exc:
        client.log.exception("schwab_option_chain failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
