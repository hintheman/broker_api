# broker_api

`broker_api` is a public Git repository for broker connectivity used by a larger trading and alerting system.

The purpose of this repository is to build and maintain lightweight broker adapters for:
- market quotes,
- option chains,
- account access,
- and eventually order entry / trade management,

across multiple brokers and data providers.

The design goal is modularity. Each broker should have its own folder, scripts, env templates, and documentation so the rest of the trading system can swap or compare broker integrations more easily. [cite:715]

## Current broker folders

### `schwab_broker`
Current active broker integration for:
- OAuth callback flow,
- quote retrieval,
- option chain retrieval,
- symbol normalization for indexes and selected futures roots.

This broker is currently the most developed in the repository and is the main path being explored for quotes, option chains, and Greeks. [cite:850][cite:849]

### `etrade_broker`
Current limited broker integration for:
- sandbox token setup,
- early sandbox quote experimentation.

This folder is not yet production-ready. Production E*TRADE access is still pending and the current implementation should be treated as sandbox-only. [cite:716]

## Why this repository exists

The broader trading system has multiple bots and services that need market data and, eventually, broker access. Rather than hard-coding one broker into each bot, this repository is meant to provide broker-specific adapters in one place.

This allows:
- cleaner separation of broker logic from strategy logic,
- easier testing of quotes and option chains across brokers,
- a path toward account and trade APIs later,
- and flexibility if one broker has better support for certain products than another. [cite:715][cite:832]

## Current scope

The repository currently focuses on:
- quote retrieval,
- option chain retrieval,
- OAuth / token handling,
- symbol mapping and normalization,
- command-line scripts for manual testing and development.

It does **not** yet provide a complete unified Python package, a production trade router, or paper-trading abstraction across brokers. Those may be added later as support matures.

## Planned additions

Potential future broker or data-provider additions include:

### CQG Client Web API
Target use case:
- real-time futures quotes,
- futures market data support,
- possible futures-oriented integration for time-sensitive workflows.

CQG is of interest primarily for stronger futures coverage. Access and onboarding are still pending. [cite:851]

### Tradier Broker API
Target use case:
- stock trading,
- options trading,
- futures support if available and practical for the broader system.

Tradier is being considered as another broker path for broader execution support. [cite:715]

## Repository philosophy

This repository is intended to be:
- simple,
- script-first,
- transparent,
- and practical.

The goal is to get broker connectivity working in real workflows first, then refactor later if a common adapter layer becomes worth the effort.

## Environment files and secrets

This public repository should only contain env **templates** or env files with variable names and empty values.

Do not commit live credentials, refresh tokens, access tokens, or private account details.

Typical local practice is:
- keep checked-in env files as templates only,
- fill local secrets on private machines or private servers,
- and keep token-bearing files out of public source control.

## Status summary

| Broker | Quotes | Option Chain | Account | Trade | Status |
|---|---|---|---|---|---|
| Schwab | Working | Working | Planned | Planned | Active |
| E*TRADE | Sandbox only | Early / limited | Pending | Pending | Waiting |
| CQG | Not started | Not started | N/A | N/A | Candidate |
| Tradier | Not started | Not started | Not started | Not started | Candidate |

## Intended audience

This repository is mainly for:
- the maintainer's own trading infrastructure,
- future broker integration work,
- and reference use by other developers exploring broker connectivity for market data and trading automation.

## Near-term roadmap

1. Continue stabilizing Schwab quote and option-chain scripts.
2. Keep E*TRADE sandbox support in place while waiting for production approval.
3. Evaluate CQG for real-time futures quote needs.
4. Evaluate Tradier for broader stock/options/futures trading support.
5. Add account and trading support only after quote and option-chain workflows are reliable.
