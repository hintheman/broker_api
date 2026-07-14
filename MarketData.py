from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from typing import Optional, Literal

import pandas as pd
import requests
import yfinance as yf

from SchwabAuthManager import SchwabAuthManager, SchwabReauthRequired

BROKER_CHOICES = ("schwab", "yfinance")
BROKER_FALLBACK_CHOICES = ("yfinance", "none")
ProviderName = Literal["schwab", "yfinance"]

PERIOD_MAP = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "60d",
    "90m": "60d",
    "1h": "60d",
    "1d": "2y",
    "5d": "5y",
    "1wk": "10y",
    "1mo": "max",
    "3mo": "max",
}

SCHWAB_PRICEHISTORY_MAP = {
    "1m": (1, "minute", 1, "day"),
    "5m": (5, "minute", 5, "day"),
    "10m": (10, "minute", 10, "day"),
    "15m": (15, "minute", 10, "day"),
    "30m": (30, "minute", 10, "day"),
    "1h": (60, "minute", 1, "month"),
    "1d": (1, "daily", 1, "year"),
    "1wk": (1, "weekly", 10, "year"),
}

logger = logging.getLogger(__name__)


@dataclass
class MarketDataConfig:
    broker: ProviderName = "schwab"
    broker_fallback: Optional[ProviderName] = "yfinance"


class YahooMarketDataProvider:
    def fetch_bars(self, symbol: str, interval: str, bars: int = 300) -> Optional[pd.DataFrame]:
        period = PERIOD_MAP.get(interval, "60d")
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if df is None or df.empty:
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0].lower() for c in df.columns]
            else:
                df.columns = [str(c).lower() for c in df.columns]

            if "adj close" in df.columns and "close" not in df.columns:
                df = df.rename(columns={"adj close": "close"})

            df = df[["open", "high", "low", "close", "volume"]].dropna()

            if len(df) > 1:
                df = df.iloc[:-1]

            return df.tail(bars)
        except Exception:
            return None


class SchwabMarketDataProvider:
    base_url = "https://api.schwabapi.com/marketdata/v1"

    def __init__(self, auth: SchwabAuthManager, timeout: int = 20):
        self.auth = auth
        self.timeout = timeout
        self.session = requests.Session()

    def _request(self, method: str, path: str, *, params: dict | None = None) -> Optional[requests.Response]:
        url = f"{self.base_url}{path}"

        try:
            self.auth.ensure_valid_token()
        except Exception as e:
            logger.exception("Schwab preflight token refresh failed: %s", e)
            return None

        try:
            r = self.session.request(
                method,
                url,
                headers=self.auth.auth_headers(),
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            logger.warning("Schwab request transport error path=%s error=%s", path, e)
            return None

        if r.status_code in (401, 403):
            logger.warning("Schwab auth failure %s on %s, forcing token refresh", r.status_code, path)
            try:
                self.auth.ensure_valid_token(force_refresh=True)
            except Exception as e:
                logger.exception("Schwab forced refresh failed after %s on %s: %s", r.status_code, path, e)
                return None

            try:
                r = self.session.request(
                    method,
                    url,
                    headers=self.auth.auth_headers(),
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                logger.warning("Schwab retry transport error path=%s error=%s", path, e)
                return None

        if r.status_code >= 400:
            body = r.text[:500] if r.text else ""
            logger.warning("Schwab request failed path=%s status=%s body=%s", path, r.status_code, body)
            return None

        return r

    def fetch_quote(self, symbol: str) -> Optional[dict]:
        params = {"symbols": symbol, "fields": "quote"}
        r = self._request("GET", "/quotes", params=params)
        if r is None:
            return None

        try:
            data = r.json()
        except ValueError:
            logger.warning("Schwab quotes returned non-JSON for symbol=%s", symbol)
            return None

        return data.get(symbol) or data.get(symbol.upper())

    def fetch_bars(self, symbol: str, interval: str, bars: int = 300) -> Optional[pd.DataFrame]:
        spec = SCHWAB_PRICEHISTORY_MAP.get(interval)
        if spec is None:
            logger.warning("Unsupported Schwab interval=%s symbol=%s", interval, symbol)
            return None

        frequency, frequency_type, period, period_type = spec
        params = {
            "symbol": symbol,
            "frequencyType": frequency_type,
            "frequency": frequency,
            "needExtendedHoursData": "false",
            "needPreviousClose": "false",
        }
        if period_type == "day":
            # Schwab's relative periodType=day window excludes the still-open
            # current session entirely (it only rolls in after the day closes),
            # so pass explicit bounds to force today's in-progress bars in.
            now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
            params["startDate"] = now_ms - period * 24 * 60 * 60 * 1000
            params["endDate"] = now_ms
        else:
            params["periodType"] = period_type
            params["period"] = period

        r = self._request("GET", "/pricehistory", params=params)
        if r is None:
            return None

        try:
            payload = r.json()
        except ValueError:
            logger.warning("Schwab pricehistory returned non-JSON for symbol=%s interval=%s", symbol, interval)
            return None

        candles = payload.get("candles") or []
        if not candles:
            logger.info("Schwab returned no candles for symbol=%s interval=%s", symbol, interval)
            return None

        df = pd.DataFrame(candles)
        if df.empty:
            return None

        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
            df = df.set_index("datetime")

        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        if len(cols) < 5:
            logger.warning(
                "Schwab missing OHLCV columns symbol=%s interval=%s cols=%s",
                symbol,
                interval,
                list(df.columns),
            )
            return None

        df = df[cols].dropna()

        if len(df) > 1:
            df = df.iloc[:-1]

        return df.tail(bars)


class BrokerRouter:
    def __init__(
        self,
        primary: str = "schwab",
        fallback: Optional[str] = "yfinance",
        auth: Optional[SchwabAuthManager] = None,
        env_file: str = "schwab.env",
        token_file: str = "schwab_token.env",
    ):
        self.primary = primary
        self.fallback = None if fallback in (None, "none") else fallback

        if auth is not None:
            self.auth = auth
        elif primary == "schwab" or self.fallback == "schwab":
            self.auth = SchwabAuthManager(env_file=env_file, token_file=token_file)
        else:
            self.auth = None

        self.providers = {
            "yfinance": YahooMarketDataProvider(),
            "schwab": SchwabMarketDataProvider(self.auth) if self.auth else None,
        }

    def _get_provider(self, name: str):
        p = self.providers.get(name)
        if p is None:
            raise ValueError(f"Provider not configured: {name}")
        return p

    def fetch_bars(self, symbol: str, interval: str, bars: int = 300) -> Optional[pd.DataFrame]:
        for name in [self.primary, self.fallback]:
            if not name:
                continue
            try:
                df = self._get_provider(name).fetch_bars(symbol, interval, bars)
                if df is not None and not df.empty:
                    return df
            except SchwabReauthRequired:
                if name == self.primary and not self.fallback:
                    raise
                continue
            except Exception:
                continue
        return None

    def fetch_quote(self, symbol: str) -> Optional[dict]:
        provider = self._get_provider(self.primary)
        if not hasattr(provider, "fetch_quote"):
            return None
        return provider.fetch_quote(symbol)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--broker", choices=BROKER_CHOICES, default="schwab")
    p.add_argument("--broker-fallback", choices=BROKER_FALLBACK_CHOICES, default="yfinance")
    p.add_argument("--symbol")
    p.add_argument("--interval", default="1d")
    p.add_argument("--bars", type=int, default=100)
    p.add_argument("--schwab-env", default="schwab.env")
    p.add_argument("--schwab-token-env", default="schwab_token.env")
    return p


def main() -> None:
    args = build_parser().parse_args()
    router = BrokerRouter(
        primary=args.broker,
        fallback=args.broker_fallback,
        env_file=args.schwab_env,
        token_file=args.schwab_token_env,
    )

    if args.symbol:
        df = router.fetch_bars(args.symbol, args.interval, args.bars)
        if df is None:
            print("No data returned")
        else:
            print(df.tail())


if __name__ == "__main__":
    main()
