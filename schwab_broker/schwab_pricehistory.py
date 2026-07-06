#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
BROKER_DIR = BASE_DIR
DEFAULT_MARKETDATA_PY = Path('/opt/tastydaytraders/as-kbn-futures')

if str(BROKER_DIR) not in sys.path:
    sys.path.insert(0, str(BROKER_DIR))
if DEFAULT_MARKETDATA_PY.exists() and str(DEFAULT_MARKETDATA_PY) not in sys.path:
    sys.path.insert(0, str(DEFAULT_MARKETDATA_PY))

from SchwabAuthManager import SchwabAuthManager, SchwabAuthError, SchwabReauthRequired

import SchwabAuthManager as sam
print("SchwabAuthManager loaded from:", sam.__file__)
print("Has request:", hasattr(SchwabAuthManager, "request"))

try:
    from MarketData import BrokerRouter  # optional sanity import
except Exception:
    BrokerRouter = None

INTERVAL_MAP = {
    '1m': ('day', 1, 'minute', 1),
    '5m': ('day', 5, 'minute', 5),
    '10m': ('day', 10, 'minute', 10),
    '15m': ('day', 10, 'minute', 15),
    '30m': ('day', 10, 'minute', 30),
    '1d': ('year', 1, 'daily', 1),
}


def setup_logging(debug: bool) -> logging.Logger:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout,
    )
    return logging.getLogger('schwab_pricehistory')


class SchwabPriceHistoryTester:
    def __init__(
        self,
        env_file: Path,
        token_file: Path,
        marketdata_base_url: Optional[str] = None,
        debug: bool = False,
    ):
        self.log = setup_logging(debug)
        self.auth = SchwabAuthManager(env_file=env_file, token_file=token_file)
        self.marketdata_base_url = (marketdata_base_url or self.auth.marketdata_base_url).rstrip('/')

    def fetch_raw(
        self,
        symbol: str,
        timeframe: str = '15m',
        period_type: Optional[str] = None,
        period: Optional[int] = None,
        frequency_type: Optional[str] = None,
        frequency: Optional[int] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        need_extended_hours: bool = True,
        need_previous_close: bool = True,
    ) -> tuple[requests.Response, dict]:
        if not (period_type and period and frequency_type and frequency):
            if timeframe not in INTERVAL_MAP:
                raise ValueError(f'Unsupported timeframe: {timeframe}')
            period_type, period, frequency_type, frequency = INTERVAL_MAP[timeframe]

        url = f'{self.marketdata_base_url}/pricehistory'
        params = {
            'symbol': symbol,
            'periodType': period_type,
            'period': period,
            'frequencyType': frequency_type,
            'frequency': frequency,
            'needExtendedHoursData': str(need_extended_hours).lower(),
            'needPreviousClose': str(need_previous_close).lower(),
        }
        if start_date is not None:
            params['startDate'] = int(start_date)
        if end_date is not None:
            params['endDate'] = int(end_date)

        self.log.info('GET %s', url)
        self.log.info('params=%s', params)
        response = self.auth.request('GET', url, params=params, timeout=30)
        self.log.info('HTTP %s', response.status_code)
        self.log.debug('response text=%s', response.text[:4000])

        try:
            payload = response.json()
        except Exception:
            payload = {'_raw_text': response.text}

        return response, payload

    def normalize_candles(self, payload: dict) -> Optional[pd.DataFrame]:
        candles = payload.get('candles') if isinstance(payload, dict) else None
        if not candles:
            return None

        df = pd.DataFrame(candles)
        required = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]
        if missing:
            self.log.warning('Missing candle columns: %s', missing)
            return None

        df['datetime'] = pd.to_datetime(df['datetime'], unit='ms', utc=True)
        df = df.rename(columns={'datetime': 'timestamp'})
        df = df.set_index('timestamp')
        df = df[['open', 'high', 'low', 'close', 'volume']].copy()
        df = df.sort_index()
        return df

    def print_summary(self, symbol: str, payload: dict) -> None:
        if not isinstance(payload, dict):
            print(payload)
            return

        candles = payload.get('candles') or []
        print(f'\nsymbol: {payload.get("symbol", symbol)}')
        print(f'empty: {payload.get("empty")}')
        print(f'previousClose: {payload.get("previousClose")}')
        print(f'previousCloseDate: {payload.get("previousCloseDate")}')
        print(f'candle_count: {len(candles)}')
        if candles:
            print('first_candle:', json.dumps(candles[0], indent=2))
            print('last_candle:', json.dumps(candles[-1], indent=2))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Standalone Schwab price history / fetch_bars tester')
    p.add_argument('--symbol', default='AMD', help='Ticker or futures symbol to test, default AMD')
    p.add_argument('--timeframe', default='15m', choices=sorted(INTERVAL_MAP.keys()), help='Bar interval, default 15m')
    p.add_argument('--env-file', default=str(BROKER_DIR / 'schwab.env'))
    p.add_argument('--token-file', default=str(BROKER_DIR / 'schwab_token.env'))
    p.add_argument('--marketdata-path', default=str(DEFAULT_MARKETDATA_PY), help='Directory containing MarketData.py')
    p.add_argument('--start-date', type=int, default=None, help='Epoch milliseconds')
    p.add_argument('--end-date', type=int, default=None, help='Epoch milliseconds')
    p.add_argument('--period-type', default=None)
    p.add_argument('--period', type=int, default=None)
    p.add_argument('--frequency-type', default=None)
    p.add_argument('--frequency', type=int, default=None)
    p.add_argument('--no-extended-hours', dest='need_extended_hours', action='store_false', default=True)
    p.add_argument('--no-previous-close', dest='need_previous_close', action='store_false', default=True)
    p.add_argument('--full-json', action='store_true', help='Print full JSON payload')
    p.add_argument('--debug', action='store_true')
    return p.parse_args()


def main() -> int:
    args = parse_args()

    md_path = Path(args.marketdata_path)
    if md_path.exists() and str(md_path) not in sys.path:
        sys.path.insert(0, str(md_path))

    log = setup_logging(args.debug)
    log.info('Broker dir=%s', BROKER_DIR)
    log.info('MarketData import available=%s', BrokerRouter is not None)

    tester = SchwabPriceHistoryTester(
        env_file=Path(args.env_file),
        token_file=Path(args.token_file),
        debug=args.debug,
    )

    try:
        response, payload = tester.fetch_raw(
            symbol=args.symbol,
            timeframe=args.timeframe,
            period_type=args.period_type,
            period=args.period,
            frequency_type=args.frequency_type,
            frequency=args.frequency,
            start_date=args.start_date,
            end_date=args.end_date,
            need_extended_hours=args.need_extended_hours,
            need_previous_close=args.need_previous_close,
        )
    except (SchwabAuthError, SchwabReauthRequired, requests.RequestException, ValueError) as exc:
        log.exception('price history request failed: %s', exc)
        return 1

    if args.full_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        tester.print_summary(args.symbol, payload)
        df = tester.normalize_candles(payload)
        if df is None:
            print('\nnormalized_df: None')
        else:
            print(f'\nnormalized_df_len: {len(df)}')
            print(f'normalized_df_first_ts: {df.index[0] if len(df) else None}')
            print(f'normalized_df_last_ts: {df.index[-1] if len(df) else None}')
            print(df.tail(5).to_string())

    return 0 if response.status_code < 400 else 1


if __name__ == '__main__':
    raise SystemExit(main())

