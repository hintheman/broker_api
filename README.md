# broker_api

`broker_api` is a command-line-first broker integration repository for market data, option chains, authentication flows, and early broker adapter development.

The repository is being used to explore and validate broker-native connectivity for trading workflows where broker data is preferable to generic public feeds. Current work is centered on Schwab, with E*TRADE preserved as an early sandbox integration path.

## Current purpose

This repository exists to:

- test real broker connectivity quickly,
- inspect raw broker payloads directly,
- normalize symbols where needed for development workflows,
- support later integration into larger trading systems,
- keep broker-specific tooling separate from strategy bots.

The overall design is intentionally simple and practical: small Python scripts, environment files, and command-line usage for rapid testing and iteration.

## Repository layout

### `schwab_broker/`
Primary active broker implementation.

This folder currently contains Schwab scripts for:

- OAuth / token flow,
- token refresh,
- quote retrieval,
- option chain retrieval,
- symbol normalization for indexes and selected futures roots.

See [`schwab_broker/README.md`](schwab_broker/README.md) for folder-specific details.

### `etrade_broker/`
Early E*TRADE sandbox integration area.

This folder currently exists for:

- sandbox token setup,
- early quote testing,
- future expansion into a fuller broker adapter.

At this time it should be treated as sandbox-first and not production-ready.

See [`etrade_broker/README.md`](etrade_broker/README.md) for folder-specific details.

## Current status

### Working now
- Schwab token refresh flow,
- Schwab quote retrieval,
- Schwab option chain retrieval,
- raw JSON inspection,
- normalized short output in selected scripts,
- basic symbol mapping,
- early E*TRADE sandbox structure.

### In progress
- improved normalized broker outputs,
- better symbol handling across brokers,
- evaluation of broker-native workflows for broader trading-system use.

### Likely next steps
- expand Schwab account endpoint support,
- research or add order-entry support where practical,
- continue E*TRADE production-readiness research,
- strengthen broker adapters for downstream strategy systems.

## Design approach

The repository follows a command-line-first workflow.

The goals are:

- easy local testing,
- fast inspection of raw responses,
- minimal abstraction during discovery,
- better confidence before integrating broker logic into larger services.

This repo is not intended to be a polished SDK or general-purpose client library at this stage. It is an active development workspace for broker connectivity and workflow validation.

## Example usage

### Schwab quotes
```bash
cd schwab_broker
python3 schwab_quote_test.py --tickers SPX
python3 schwab_quote_test.py --tickers SPX SPY QQQ --short
```

### Schwab option chains
```bash
cd schwab_broker
python3 schwab_option_chain.py --tickers SPX
python3 schwab_option_chain.py --tickers SPX --dte 0 45 --strikes 25 --short
python3 schwab_option_chain.py --tickers SPX --dte 7 7 --strikes 2 --range ITM
```

### E*TRADE sandbox
```bash
cd etrade_broker
python3 sandbox_token.py
python3 etrade_quote.py
```

## Symbol handling

A practical amount of broker-specific symbol normalization is included where needed for development and testing.

Examples may include:

- index mapping such as `SPX -> $SPX`,
- broker-specific handling for symbols like `NDX`,
- selected futures-root normalization for workflows involving symbols such as `ES`, `NQ`, `MES`, `MNQ`, `CL`, `MCL`, `GC`, and `MGC`.

This should currently be viewed as development-oriented mapping, not a complete contract-roll or production-grade symbol engine.

## Security

Do not commit:

- live client IDs tied to private apps unless intentionally public,
- live client secrets,
- access tokens,
- refresh tokens,
- account numbers,
- private trading data,
- personal credentials.

Checked-in env files should be templates only, with blank values or variable names only.

## Notes

- Raw JSON output is intentionally preserved in several scripts because field discovery is still important.
- Broker support is uneven by design right now; Schwab is the most active implementation.
- This repository should be viewed as active development, not finalized broker infrastructure.

## Relationship to larger systems

This repository is being developed as a broker adapter layer that can later support broader trading and alerting systems, including futures workflows, MEIC-related tools, DB-Alerts, and other automation components.

Where broker-native data is not necessary, other data sources may still remain useful for slower or less sensitive workflows.
