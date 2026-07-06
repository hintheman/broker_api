# schwab_broker

`schwab_broker` contains Charles Schwab broker scripts for OAuth, token management, quotes, price history, and option chains.

This folder is currently the primary active broker implementation inside `broker_api`, with working support for token refresh, token health inspection, quote retrieval, price-history retrieval, and option-chain retrieval for indexes, stocks, and selected futures symbol mappings.

## Current files

### `SchwabAuthManager.py`
Shared authentication and token-management helper for Schwab workflows.

This module is intended to centralize:
- loading credentials and token files,
- validating token state,
- refreshing access tokens,
- saving updated token metadata,
- and reducing duplicate auth logic across Schwab scripts.

Where possible, other Schwab scripts should rely on this manager rather than each script implementing its own token-refresh flow.

### `refresh_schwab_token.py`
Forces or triggers a Schwab token refresh from the command line.

This script is useful for:
- manually refreshing tokens,
- confirming that stored credentials and refresh tokens still work,
- updating local token state before quote or chain testing,
- and debugging OAuth/token-lifecycle issues.

### `schwab_tokenhealth.py`
Checks the current health of the local Schwab token state.

Current uses may include:
- viewing token presence and expiry state,
- verifying whether the current token appears usable,
- checking whether refresh is likely needed,
- and giving a quick CLI health check before running other broker scripts.

This is useful as a lightweight diagnostic tool during development and deployment.

### `schwab_quote_test.py`
Fetches Schwab market quotes for one or more symbols.

Current capabilities include:
- token validation / refresh,
- quote retrieval for one or more tickers,
- short normalized output or full JSON output,
- and CLI testing support for development.

### `schwab_pricehistory.py`
Fetches Schwab price history / candle data for one or more symbols.

Current capabilities may include:
- broker-native historical price retrieval,
- testing symbol compatibility against Schwab market-data endpoints,
- retrieving bar/candle payloads for later normalization,
- and validating whether Schwab data can support time-series workflows now handled elsewhere.

This script is especially useful when comparing Schwab-native history against public-data workflows.

### `schwab_option_chain.py`
Fetches Schwab option chains from the market-data API.

Current capabilities include:
- one or more tickers via `--tickers`,
- default symbol handling for `SPX` and other mapped symbols,
- DTE filtering via `--dte MIN MAX`,
- strike count control via `--strikes`,
- optional normalized output via `--short`,
- raw JSON output by default for field discovery,
- and symbol mapping for indexes and selected futures roots.

This script is currently useful for exploring chain payloads, Greeks, implied volatility, volume, open interest, and other option-contract metadata.

### `schwab_callback.py`
OAuth callback helper for Schwab authorization flow.

Used during setup to capture or complete the authorization-token flow needed for local development.

### `schwab.env`
Local configuration template for:
- client ID,
- client secret,
- token URL,
- market-data base URL,
- callback or redirect settings where needed.

This file in Git should contain variable names only or empty values.

### `schwab_token.env`
Local token file used for:
- access token,
- refresh token,
- token type,
- scope,
- and expiry tracking.

This should never contain live secrets in a public repository.

### `logs/`
Local log output folder for development and testing.

## Current functionality

The Schwab scripts currently focus on:
- OAuth/token lifecycle,
- token refresh,
- token health inspection,
- quote retrieval,
- price-history retrieval,
- option-chain retrieval,
- and symbol normalization.

## Symbol normalization

### Index symbol normalization
Examples:
- `SPX -> $SPX`
- `NDX -> $NDX`

### Futures root normalization
Selected futures roots are mapped into Schwab-compatible current symbols for development workflows.

Examples include:
- `ES`
- `NQ`
- `MES`
- `MNQ`
- `CL`
- `MCL`
- `GC`
- `MGC`

This is currently intended as practical symbol handling for quote, price-history, and chain testing, not yet a full futures-roll engine.

## Current status

### Working now
- token refresh,
- token-health inspection,
- quote retrieval,
- price-history retrieval,
- option-chain retrieval,
- raw JSON inspection,
- normalized short output in selected scripts,
- and basic symbol mapping.

### Likely next steps
- refine normalized option-chain output,
- refine normalized price-history output,
- add account endpoint support,
- research or add order-entry support,
- reduce duplicated auth logic across scripts via `SchwabAuthManager`,
- and determine whether Schwab API workflows can support the needed live-trading use cases.

## Design approach

The scripts are intentionally simple and command-line driven.

The goal is:
- to validate real broker connectivity quickly,
- to inspect raw broker payloads directly,
- to keep broker auth and token handling visible and testable,
- and to support later integration into larger systems such as futures workflows, MEIC, DB-Alerts, and other trading services.

## Example use

### Token refresh
```bash
python3 refresh_schwab_token.py
```

### Token health
```bash
python3 schwab_tokenhealth.py
```

### Quote test
```bash
python3 schwab_quote_test.py --tickers SPX
python3 schwab_quote_test.py --tickers SPX SPY QQQ --short
```

### Price history
```bash
python3 schwab_pricehistory.py --tickers SPX
python3 schwab_pricehistory.py --tickers SPY QQQ
```

### Option chain
```bash
python3 schwab_option_chain.py --tickers SPX
python3 schwab_option_chain.py --tickers SPX --dte 0 45 --strikes 25 --short
python3 schwab_option_chain.py --tickers SPX --dte 7 7 --strikes 2 --range ITM
```

## Notes

- Raw JSON output is intentionally preserved because Schwab returns many useful fields that may later be normalized selectively.
- `SchwabAuthManager.py` should be the preferred place for reusable auth and token logic as the folder matures.
- The folder is still evolving and should be viewed as active development, not a finalized client library.
- Any future account or order scripts should follow the same command-line-first pattern where practical.

## Security

Do not commit:
- live client secrets,
- live refresh tokens,
- live access tokens,
- account numbers,
- or private trading data.

Use checked-in env files only as templates with blank values.

## Relationship to the larger system

This folder is being developed as a broker adapter that can later support:
- futures-oriented quote workflows,
- broker-native price-history workflows,
- MEIC,
- DB-Alerts,
- and other trading automation components where broker-native data is better than generic public data.

For slower workflows, other data sources may still be used when appropriate.
