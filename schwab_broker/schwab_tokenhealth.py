#!/usr/bin/env python3
"""Cron: check Schwab token health, refresh if needed, warn via email if refresh token nearing 7-day expiry."""

from __future__ import annotations
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from SchwabAuthManager import SchwabAuthManager, SchwabAuthError, SchwabReauthRequired

ALERT_TO = "hintheman@gmail.com"
ALERT_FROM = "hintheman@gmail.com"          # Gmail SMTP requires From == authenticated account
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "hintheman@gmail.com"
SMTP_APP_PASSWORD_ENV_KEY = "SCHWAB_ALERT_SMTP_PASS"   # store in schwab.env

REFRESH_TOKEN_LIFETIME_DAYS = 7
WARN_WINDOW_DAYS = 2


def send_email(subject: str, body: str, smtp_password: str) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ALERT_FROM
    msg["To"] = ALERT_TO

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, smtp_password)
        server.send_message(msg)


def main() -> int:
    mgr = SchwabAuthManager()
    from SchwabAuthManager import load_env_file
    env = load_env_file(mgr.env_file)
    smtp_password = env.get(SMTP_APP_PASSWORD_ENV_KEY, "")

    if not smtp_password:
        print("Missing SCHWAB_ALERT_SMTP_PASS in schwab.env", file=sys.stderr)
        return 1

    warnings = []
    errors = []

    # 1. Ensure/refresh access token
    try:
        mgr.ensure_valid_token()
    except SchwabReauthRequired as e:
        errors.append(f"REAUTH REQUIRED: {e}")
    except SchwabAuthError as e:
        errors.append(f"Auth error during access token refresh: {e}")

    # 2. Check refresh token age against 7-day hard limit
    mgr.reload()
    if mgr.last_refreshed_at:
        try:
            last_refresh = datetime.fromisoformat(mgr.last_refreshed_at.replace("Z", "+00:00"))
        except ValueError:
            last_refresh = None
    else:
        last_refresh = None

    if last_refresh:
        refresh_token_expiry = last_refresh + timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS)
        now = datetime.now(timezone.utc)
        days_left = (refresh_token_expiry - now).total_seconds() / 86400

        if days_left <= WARN_WINDOW_DAYS:
            warnings.append(
                f"Schwab refresh token expires in ~{days_left:.1f} day(s) "
                f"(est. hard cutoff {refresh_token_expiry.isoformat()}). "
                f"You must manually redo the OAuth browser login before then."
            )
    else:
        warnings.append("Could not determine last refresh timestamp — check schwab_token.env manually.")

    if errors or warnings:
        subject = "[Schwab Auth] " + ("REAUTH NEEDED" if errors else "Token expiring soon")
        body = "\n\n".join(errors + warnings)
        send_email(subject, body, smtp_password)
        print(body)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
