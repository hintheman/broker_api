"""Shared Discord notification utilities for tastydaytraders bots.

Canonical color palette, EDT timestamp formatting, footer conventions, webhook
resolution, and retry/send plumbing -- extracted from db-alerts.py (the
reference implementation) to eliminate duplicate copies across bots. Import
alongside MarketData.py / schwab_broker.SchwabAuthManager the same way:

    from DiscordNotifier import DiscordNotifier
    notifier = DiscordNotifier(bot_name="my-bot", bot_version="1.0", webhook_env="DISCORD_MY_BOT_WEBHOOK")

Domain-specific embed building (candidate/leg formatting, trade theses, etc.)
stays in each bot -- this module only covers what's genuinely identical
across bots: color, time, footer, webhook, and HTTP send.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

EASTERN_TZ = ZoneInfo("America/New_York")


class DiscordNotifier:
    # Canonical semantic palette (Tailwind-style hex), single source of truth
    # for every bot -- sourced from db-alerts.py's own color scheme.
    BULLISH = 0x22C55E  # green -- positive outcome / win / bullish signal / session start
    BEARISH = 0xEC4899  # pink  -- negative outcome / loss / bearish signal
    NEUTRAL = 0xEAB308  # amber -- no signal / pending entry / informational

    def __init__(
        self,
        bot_name: str,
        bot_version: str,
        webhook_env: Optional[str] = None,
        broker: Optional[str] = None,
        timeout: tuple[float, float] = (3.05, 15),
    ):
        self.bot_name = bot_name
        self.bot_version = bot_version
        self.webhook_env = webhook_env
        self.broker = broker  # short name e.g. "schwab", "yfinance" -- settable post-init too
        self.timeout = timeout
        self._session = None

    # ─── timestamps (always EDT/EST for anything shown in a Discord message) ──

    @staticmethod
    def now_edt(dt: Optional[datetime] = None) -> str:
        if dt is None:
            dt = datetime.now(timezone.utc)
        return dt.astimezone(EASTERN_TZ).strftime("%b %d, %Y %I:%M %p %Z")

    @staticmethod
    def bar_time_edt(ts_value) -> str:
        """Convert a bar timestamp (pandas Timestamp, ISO string, whatever the
        broker feed handed back -- usually UTC) into a human EDT string."""
        try:
            import pandas as pd
            bar_dt = pd.Timestamp(ts_value)
            if bar_dt.tzinfo is None:
                bar_dt = bar_dt.tz_localize("UTC")
            bar_dt = bar_dt.tz_convert(EASTERN_TZ)
            return bar_dt.strftime("%b %d, %Y %I:%M %p %Z")
        except Exception:
            return str(ts_value)

    # ─── color ──────────────────────────────────────────────────────────────

    @classmethod
    def color_for_side(cls, side: str) -> int:
        """Map a semantic label onto the canonical 3-color palette. Extend the
        alias sets below rather than adding new raw hex values elsewhere."""
        s = (side or "").upper()
        if s in ("BULLISH", "BUY", "WIN", "TP", "TAKE_PROFIT", "CALLED_AWAY", "LONG", "STARTUP"):
            return cls.BULLISH
        if s in ("BEARISH", "SELL", "LOSS", "ASSIGNED", "SHORT"):
            return cls.BEARISH
        return cls.NEUTRAL

    # ─── ansi (Discord ```ansi fenced code block colors) ───────────────────

    @staticmethod
    def ansi(line: str, color_code: Optional[str] = None, bold: bool = False) -> str:
        if not color_code and not bold:
            return line
        parts = []
        if bold:
            parts.append("1")
        if color_code:
            parts.append(color_code)
        prefix = f"[{';'.join(parts)}m"
        return f"{prefix}{line}[0m"

    # ─── footer ─────────────────────────────────────────────────────────────

    def build_footer(
        self,
        extra: Optional[list[str]] = None,
        timestamp: bool = True,
    ) -> str:
        """Canonical footer: bot name+version, then anything bot-specific,
        then an EDT timestamp -- one place, one order, instead of every bot
        re-deciding where these go. Broker now lives as its own body field
        (see build_broker_field()), not the footer."""
        bits = [f"{self.bot_name} {self.bot_version}"]
        if extra:
            bits.extend(str(x) for x in extra if x)
        if timestamp:
            bits.append(self.now_edt())
        return " | ".join(bits)[:2048]

    # ─── broker body field ──────────────────────────────────────────────────

    @staticmethod
    def build_broker_field(broker: str) -> tuple[str, str]:
        """('Broker', <name>) tuple for a bot's own ansi-colored fields list --
        primary broker only, no fallback. Render with palette color '33'
        (orange) rather than cycling through the standard palette, since this
        one field is meant to stand out."""
        return ("Broker", broker.capitalize())

    # ─── webhook resolution ─────────────────────────────────────────────────

    def resolve_webhook(self, discord_arg: Optional[str], known_webhooks: Optional[dict] = None, logger=None) -> str:
        """
        --discord value resolution:
          None / ""                  -> "" (discord off)
          full https://discord... URL -> used directly
          name in known_webhooks      -> known_webhooks[name]
          "default" or == webhook_env -> os.getenv(webhook_env)
          anything else               -> treated as an env var name to read
        """
        known_webhooks = known_webhooks or {}
        if not discord_arg:
            return ""

        if discord_arg.startswith("https://discord.com/api/webhooks/"):
            return discord_arg

        if discord_arg in known_webhooks:
            return known_webhooks[discord_arg]

        if discord_arg == "default" or (self.webhook_env and discord_arg == self.webhook_env):
            webhook = os.getenv(self.webhook_env, "").strip() if self.webhook_env else ""
            if not webhook and logger:
                logger.warning("Discord webhook not set in env var %s", self.webhook_env)
            return webhook

        webhook = os.getenv(discord_arg, "").strip()
        if webhook:
            return webhook

        if logger:
            logger.warning("Discord target not recognized: %s", discord_arg)
        return ""

    # ─── http send ──────────────────────────────────────────────────────────

    def _get_session(self):
        if self._session is not None:
            return self._session
        try:
            import requests
            from requests.adapters import HTTPAdapter
            try:
                from urllib3.util.retry import Retry
            except Exception:
                Retry = None
        except Exception:
            return None

        session = requests.Session()
        if Retry is not None:
            retry = Retry(
                total=3, connect=3, read=3, status=3, backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=frozenset(["POST"]), raise_on_status=False,
            )
            session.mount("http://", HTTPAdapter(max_retries=retry))
            session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session = session
        return session

    def send(self, payload: dict, webhook_url: str, logger=None) -> bool:
        if not webhook_url:
            if logger:
                logger.warning("Discord webhook not resolved")
            return False

        session = self._get_session()
        if session is None:
            if logger:
                logger.warning("requests not available; cannot send Discord")
            return False

        try:
            r = session.post(webhook_url, json=payload, timeout=self.timeout)
            if r.status_code >= 300:
                if logger:
                    logger.error("Discord post failed: %s %s", r.status_code, r.text[:300])
                return False
            if logger:
                logger.info("Discord message sent")
            return True
        except Exception as e:
            if logger:
                logger.error("Discord post error: %s", e)
            return False
