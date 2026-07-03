# schwab_broker

`schwab_broker` contains Charles Schwab broker scripts for OAuth, quotes, and option chains.

This folder is currently the primary active broker implementation inside `broker_api`, with working support for token refresh, quote retrieval, and option-chain retrieval for indexes, stocks, and selected futures symbol mappings. [cite:850][cite:849]

## Current files

### `schwab_option_chain.py`
Fetches Schwab option chains from the market data API.

Current capabilities include:
- one or more tickers via `--tickers`,
- default symbol handling for `SPX` and other mapped symbols,
- DTE filtering via `--dte MIN MAX`,
- strike count control via `--strikes`,
- optional normalized output via `--short`,
- raw JSON output by default for field discovery,
- symbol mapping for indexes and selected futures roots.

This script is currently useful for exploring chain payloads, Greeks, implied volatility, volume, open interest, and other option contract metadata. [cite:849]

### `schwab_quote_test.py`
Fetches Schwab market quotes for one or more symbols.

Current capabilities include:
- token validation / refresh,
- quote retrieval for one or more tickers,
- short normalized output or full JSON output,
- CLI testing support for development.

### `schwab_callback.py`
OAuth callback helper for Schwab authorization flow.

Used during setup to capture or complete the authorization-token flow needed for local development.

### `schwab.env`
Local configuration template for:
- client ID,
- client secret,
- token URL,
- market-data base URL.

This file in Git should contain variable names only or empty values.

### `schwab_token.env`
Local token file used for:
- access token,
- refresh token,
- token type,
- scope,
- expiry tracking.

This should never contain live secrets in a public repository.

### `logs/`
Local log output folder for development and testing.

## Current functionality

The Schwab scripts currently focus on:
- OAuth/token lifecycle,
- quote retrieval,
- option chain retrieval,
- symbol normalization.

### Index symbol normalization
Examples:
- `SPX -> $SPX`
- `NDX -> $NDX` [cite:849]

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
- `MGC` [cite:849]

This is currently intended as practical symbol handling for quote and chain testing, not yet a full futures-roll engine.

## Current status

### Working now
- token refresh,
- quote retrieval,
- option chain retrieval,
- raw JSON inspection,
- normalized short output,
- basic symbol mapping.

### Likely next steps
- refine normalized option-chain output,
- add account endpoint support,
- research or add order entry support,
- determine whether Schwab API workflows can support the needed live-trading use cases. [cite:850]

## Design approach

The scripts are intentionally simple and command-line driven.

The goal is:
- to validate real broker connectivity quickly,
- to inspect raw broker payloads directly,
- and to support later integration into larger systems such as futures workflows, MEIC, DB-Alerts, and other trading services.

## Example use

### Quote test
```bash
python3 schwab_quote_test.py --tickers SPX
python3 schwab_quote_test.py --tickers SPX SPY QQQ --short
```

### Option chain
```bash
python3 schwab_option_chain.py --tickers SPX
python3 schwab_option_chain.py --tickers SPX --dte 0 45 --strikes 25 --short
python3 schwab_option_chain.py --tickers SPX --dte 7 7 --strikes 2 --range ITM
```

## Notes

- Raw JSON output is intentionally preserved because Schwab returns many useful fields that may later be normalized selectively.
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
- MEIC,
- DB-Alerts,
- and other trading automation components where broker-native data is better than generic public data.

For slower workflows, other data sources may still be used when appropriate. [cite:716]
