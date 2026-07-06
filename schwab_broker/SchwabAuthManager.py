from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import requests


class SchwabAuthError(RuntimeError):
    pass


class SchwabReauthRequired(SchwabAuthError):
    pass


def load_env_file(path: str | Path) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}

    data: Dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def save_env_file(path: str | Path, data: Dict[str, object], ordered_keys: Optional[list[str]] = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    keys = ordered_keys or list(data.keys())
    lines = []
    for k in keys:
        v = data.get(k, "")
        if v is None:
            v = ""
        s = str(v)
        if " " in s:
            s = json.dumps(s)
        lines.append(f"{k}={s}")

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


class SchwabAuthManager:
    BASE_DIR = Path(__file__).resolve().parent

    AUTH_BASE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
    DEFAULT_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
    DEFAULT_MARKETDATA_BASE_URL = "https://api.schwabapi.com/marketdata/v1"

    TOKEN_FILE_KEYS = [
        "SCHWAB_ACCESS_TOKEN",
        "SCHWAB_REFRESH_TOKEN",
        "SCHWAB_TOKEN_TYPE",
        "SCHWAB_SCOPE",
        "SCHWAB_ACCESS_TOKEN_EXPIRES_AT",
        "SCHWAB_LAST_REFRESHED_AT",
    ]

    def __init__(
        self,
        env_file: str | Path | None = None,
        token_file: str | Path | None = None,
        timeout: int = 30,
        refresh_leeway_seconds: int = 60,
    ):
        self.env_file = Path(env_file) if env_file else self.BASE_DIR / "schwab.env"
        self.token_file = Path(token_file) if token_file else self.BASE_DIR / "schwab_token.env"
        self.timeout = timeout
        self.refresh_leeway_seconds = refresh_leeway_seconds

        self.client_id = ""
        self.client_secret = ""
        self.redirect_uri = ""
        self.token_url = self.DEFAULT_TOKEN_URL
        self.marketdata_base_url = self.DEFAULT_MARKETDATA_BASE_URL

        self.access_token = ""
        self.refresh_token = ""
        self.token_type = "Bearer"
        self.scope = "api"
        self.access_token_expires_at = ""
        self.last_refreshed_at = ""

        self.session = requests.Session()

        self.reload()

        if not self.client_id or not self.client_secret or not self.redirect_uri:
            raise SchwabAuthError(
                f"Missing SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, or SCHWAB_REDIRECT_URI in {self.env_file}"
            )

    def reload(self) -> None:
        env = load_env_file(self.env_file)
        token_state = load_env_file(self.token_file)

        self.client_id = env.get("SCHWAB_CLIENT_ID", "").strip()
        self.client_secret = env.get("SCHWAB_CLIENT_SECRET", "").strip()
        self.redirect_uri = env.get("SCHWAB_REDIRECT_URI", "").strip()
        self.token_url = env.get("SCHWAB_TOKEN_URL", self.DEFAULT_TOKEN_URL).strip()
        self.marketdata_base_url = env.get(
            "SCHWAB_MARKETDATA_BASE_URL",
            self.DEFAULT_MARKETDATA_BASE_URL,
        ).strip().rstrip("/")

        self.access_token = token_state.get("SCHWAB_ACCESS_TOKEN", "").strip()
        self.refresh_token = token_state.get("SCHWAB_REFRESH_TOKEN", "").strip()
        self.token_type = token_state.get("SCHWAB_TOKEN_TYPE", "Bearer").strip() or "Bearer"
        self.scope = token_state.get("SCHWAB_SCOPE", "api").strip() or "api"
        self.access_token_expires_at = token_state.get("SCHWAB_ACCESS_TOKEN_EXPIRES_AT", "").strip()
        self.last_refreshed_at = token_state.get("SCHWAB_LAST_REFRESHED_AT", "").strip()

    def build_authorize_url(self, state: str = "schwab-auth") -> str:
        from urllib.parse import urlencode

        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
            }
        )
        return f"{self.AUTH_BASE_URL}?{query}"

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _iso_utc(self, dt: datetime) -> str:
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _parse_expiry(self) -> Optional[datetime]:
        if not self.access_token_expires_at:
            return None
        try:
            return datetime.fromisoformat(self.access_token_expires_at.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _write_token_file(self) -> None:
        values = {
            "SCHWAB_ACCESS_TOKEN": self.access_token,
            "SCHWAB_REFRESH_TOKEN": self.refresh_token,
            "SCHWAB_TOKEN_TYPE": self.token_type,
            "SCHWAB_SCOPE": self.scope,
            "SCHWAB_ACCESS_TOKEN_EXPIRES_AT": self.access_token_expires_at,
            "SCHWAB_LAST_REFRESHED_AT": self.last_refreshed_at,
        }
        save_env_file(self.token_file, values, ordered_keys=self.TOKEN_FILE_KEYS)

    def _token_expiring(self) -> bool:
        expiry = self._parse_expiry()
        if expiry is None:
            return False
        return self._utc_now() >= (expiry - timedelta(seconds=self.refresh_leeway_seconds))

    def ensure_valid_token(self, force_refresh: bool = False) -> str:
        self.reload()

        if force_refresh or not self.access_token:
            self.refresh_access_token()
            self.reload()
            if not self.access_token:
                raise SchwabReauthRequired("No Schwab access token available after refresh")
            return self.access_token

        expiry = self._parse_expiry()
        if expiry is not None and self._token_expiring():
            self.refresh_access_token()
            self.reload()

        if not self.access_token:
            raise SchwabReauthRequired("Schwab token unavailable after refresh")

        return self.access_token

    def refresh_access_token(self) -> Dict[str, object]:
        self.reload()

        if not self.client_id or not self.client_secret:
            raise SchwabAuthError(f"Missing SCHWAB_CLIENT_ID or SCHWAB_CLIENT_SECRET in {self.env_file}")

        if not self.refresh_token:
            raise SchwabReauthRequired(f"Missing SCHWAB_REFRESH_TOKEN in {self.token_file}")

        response = self.session.post(
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
            timeout=self.timeout,
        )

        if response.status_code in (400, 401, 403):
            raise SchwabReauthRequired(
                f"Refresh failed and likely requires reauth: HTTP {response.status_code} {response.text[:300]}"
            )

        if response.status_code >= 400:
            raise SchwabAuthError(
                f"Refresh failed: HTTP {response.status_code} {response.text[:300]}"
            )

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
        return payload

    def exchange_authorization_code(self, code: str) -> Dict[str, object]:
        if not self.client_id or not self.client_secret or not self.redirect_uri:
            raise SchwabAuthError(
                f"Missing SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET, or SCHWAB_REDIRECT_URI in {self.env_file}"
            )

        response = self.session.post(
            self.token_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            raise SchwabAuthError(
                f"Authorization code exchange failed: HTTP {response.status_code} {response.text[:300]}"
            )

        payload = response.json()

        self.access_token = payload.get("access_token", "")
        self.refresh_token = payload.get("refresh_token", self.refresh_token)
        self.token_type = payload.get("token_type", "Bearer") or "Bearer"
        self.scope = payload.get("scope", "api") or "api"

        expires_in = int(payload.get("expires_in", 1800))
        now = self._utc_now()
        self.last_refreshed_at = self._iso_utc(now)
        self.access_token_expires_at = self._iso_utc(now + timedelta(seconds=expires_in))

        self._write_token_file()
        return payload

    def exchange_callback_url_for_tokens(self, callback_url: str) -> Dict[str, object]:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(callback_url.strip())
        params = parse_qs(parsed.query)
        code = (params.get("code") or [None])[0]

        if not code:
            raise SchwabAuthError("Callback URL missing code parameter")

        return self.exchange_authorization_code(code)

    def auth_headers(self, force_refresh: bool = False) -> Dict[str, str]:
        token = self.ensure_valid_token(force_refresh=force_refresh)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def request(
        self,
        method: str,
        url: str,
        *,
        retry_on_auth_failure: bool = True,
        **kwargs,
    ) -> requests.Response:
        timeout = kwargs.pop("timeout", self.timeout)
        base_headers = dict(kwargs.pop("headers", {}) or {})

        request_headers = dict(base_headers)
        request_headers.update(self.auth_headers())

        response = self.session.request(
            method=method.upper(),
            url=url,
            headers=request_headers,
            timeout=timeout,
            **kwargs,
        )

        if retry_on_auth_failure and response.status_code in (401, 403):
            self.refresh_access_token()
            retry_headers = dict(base_headers)
            retry_headers.update(self.auth_headers())
            response = self.session.request(
                method=method.upper(),
                url=url,
                headers=retry_headers,
                timeout=timeout,
                **kwargs,
            )

        return response
