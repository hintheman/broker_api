# etrade_broker

`etrade_broker` contains early E*TRADE broker scripts and setup notes for sandbox access.

At this time, this folder should be treated as **sandbox-only**. Production E*TRADE API support is still pending, so the current scripts are for token setup, experimentation, and early development rather than live broker use. [cite:716]

## Current status

Current support is limited to:
- sandbox token setup,
- early sandbox quote testing,
- initial broker folder structure for future expansion. [cite:716]

Production support is **not** complete yet.

## Purpose

This folder exists so E*TRADE can be developed as one broker adapter inside the broader `broker_api` repository.

The goal is to support, over time:
- market quotes,
- option chains,
- account access,
- and possibly trading workflows,

once production approval and credentials are available. [cite:715][cite:716]

## Current files

Typical contents may include:
- sandbox token helper scripts,
- env template files,
- early quote test scripts,
- notes for future production onboarding.

## Security

Do not commit:
- live API keys,
- live secrets,
- access tokens,
- refresh tokens,
- account numbers,
- or private user data.

Checked-in env files should contain variable names only or blank values.

## Near-term roadmap

1. Keep sandbox setup working.
2. Wait for or re-attempt production approval.
3. Add production token flow if approved.
4. Expand support for quotes and option chains.
5. Add account and trade support only after production access is stable. [cite:716]

## Notes

This folder is intentionally simple for now.

It exists to preserve the E*TRADE integration path while Schwab is currently the more active broker implementation in this repository. [cite:716]
