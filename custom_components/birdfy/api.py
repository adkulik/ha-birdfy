"""Minimal client for the Birdfy (Netvue) cloud API.

Only what is needed to read bird visit events is implemented: login, the
device list, the event list and the event snapshot. There is no video code.

Security notes:
- The plain password is never stored. The Birdfy login only needs the MD5 hash
  of the password, so that hash is what the config entry keeps.
- Tokens, signatures and presigned URLs are never written to the log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

UCID = "b3cf543b57"
USER_AGENT = "Birdfy/1.19.2 (build 123960) NetvueSDK/1.6.1 Android/12"
LOGIN_URL = "https://localweb.nvts.co/v1/users/login/v2"
DEFAULT_LOCAL_ENDPOINT = "https://localweb.nvts.co"
DEFAULT_REGION = "eu-central-1"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class BirdfyError(Exception):
    """Generic Birdfy API error."""


class BirdfyAuthError(BirdfyError):
    """Login failed or the session was rejected."""


def hash_password(password: str) -> str:
    """Return the password hash the Birdfy login expects (MD5 hex)."""
    return hashlib.md5(password.encode()).hexdigest()  # noqa: S324 - required by the Birdfy API


def _hmac_hex(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def _signature(token: str, udid: str, userid: str, ts: str) -> str:
    """Chained HMAC-SHA256 signature used in the x-nvs-* headers."""
    key = "nvs1" + token
    for msg in (UCID, udid, userid, ts):
        key = _hmac_hex(key.encode(), msg)
    return _hmac_hex(key.encode(), "nvs1_request")


def _unwrap(data: Any) -> Any:
    """Some endpoints wrap the payload in a ``data`` object."""
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        inner = dict(data["data"])
        inner.setdefault("ret", data.get("ret"))
        return inner
    return data


@dataclass
class BirdfyDevice:
    """A Birdfy camera on the account."""

    serial: str
    name: str
    model: str | None = None
    firmware: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BirdfyDevice | None:
        serial = (
            data.get("serialNumber")
            or data.get("deviceSn")
            or data.get("sn")
            or data.get("addxSn")
        )
        if not serial:
            return None
        return cls(
            serial=str(serial),
            name=str(data.get("deviceName") or data.get("name") or "Birdfy"),
            model=data.get("model") or data.get("modelNo") or data.get("deviceModel"),
            firmware=data.get("firmwareVersion") or data.get("fwVersion"),
            raw=data,
        )


@dataclass
class BirdfyEvent:
    """One bird visit / motion event."""

    alarm_id: str
    timestamp: float  # seconds since epoch
    label: str | None
    record_url: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BirdfyEvent | None:
        alarm_id = data.get("alarmId") or data.get("id")
        if not alarm_id:
            return None
        ts = float(data.get("alertTime") or data.get("time") or 0)
        if ts > 1e12:  # milliseconds
            ts /= 1000
        record_url = None
        desc = data.get("description")
        if isinstance(desc, str) and desc:
            try:
                desc = json.loads(desc)
            except ValueError:
                desc = None
        if isinstance(desc, dict):
            record_url = desc.get("recordUrl") or None
        label = data.get("label")
        return cls(
            alarm_id=str(alarm_id),
            timestamp=ts,
            label=str(label).strip() if label else None,
            record_url=record_url,
            raw=data,
        )


class BirdfyApi:
    """Async Birdfy cloud client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password_hash: str,
        udid: str,
    ) -> None:
        self._session = session
        self._email = email.strip().lower()
        self._password_hash = password_hash
        self._udid = udid
        self._token: str | None = None
        self._userid: str | None = None
        self._region = DEFAULT_REGION
        self._local_endpoint = DEFAULT_LOCAL_ENDPOINT

    @property
    def api_base(self) -> str:
        return f"https://{self._region}-api2.nvts.co"

    @property
    def user_id(self) -> str | None:
        return self._userid

    async def async_login(self) -> None:
        """Log in and keep the session token in memory only."""
        payload = {
            "username": self._email,
            "password": self._password_hash,
            "locale": "en-US",
            "platform": 0,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "x-nvs-ucid": UCID,
            "x-nvs-udid": self._udid,
        }
        try:
            async with self._session.post(
                LOGIN_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                status = resp.status
                data = _unwrap(await resp.json(content_type=None))
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise BirdfyError(f"Login request failed: {type(err).__name__}") from err

        if not isinstance(data, dict):
            raise BirdfyError(f"Unexpected login response (HTTP {status})")
        ret = data.get("ret")
        token = data.get("token") or data.get("accessToken")
        userid = data.get("userID") or data.get("userId") or data.get("userid")
        if status in (401, 403) or ret not in (0, None) or not token or userid is None:
            _LOGGER.debug(
                "Birdfy login rejected: HTTP %s, ret=%s, msg=%s, keys=%s",
                status,
                ret,
                data.get("msg"),
                sorted(data.keys()),
            )
            raise BirdfyAuthError("Invalid Birdfy credentials")

        self._token = str(token)
        self._userid = str(userid)
        self._region = str(data.get("region") or DEFAULT_REGION)
        self._local_endpoint = str(data.get("localEndpoint") or DEFAULT_LOCAL_ENDPOINT)
        _LOGGER.debug("Birdfy login ok (region %s)", self._region)

    def _auth_headers(self) -> dict[str, str]:
        assert self._token and self._userid
        ts = str(int(time.time() * 1000))
        return {
            "Accept": "application/json",
            "Accept-Charset": "UTF-8",
            "User-Agent": USER_AGENT,
            "x-nvs-signature": _signature(self._token, self._udid, self._userid, ts),
            "x-nvs-time": ts,
            "x-nvs-ucid": UCID,
            "x-nvs-udid": self._udid,
            "x-nvs-userid": self._userid,
            "x-nvs-version": '{"signature":2}',
        }

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Signed GET; logs in first and retries once on an auth error."""
        for attempt in (1, 2):
            if self._token is None:
                await self.async_login()
            try:
                async with self._session.get(
                    url,
                    headers=self._auth_headers(),
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    status = resp.status
                    data = await resp.json(content_type=None) if status < 500 else None
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise BirdfyError(f"Request failed: {type(err).__name__}") from err

            if status in (401, 403) and attempt == 1:
                _LOGGER.debug("Birdfy session expired, logging in again")
                self._token = None
                continue
            if status in (401, 403):
                raise BirdfyAuthError(f"Request rejected (HTTP {status})")
            if status >= 400:
                raise BirdfyError(f"HTTP {status} from Birdfy API")
            return data
        raise BirdfyError("Request failed")  # pragma: no cover

    async def async_get_devices(self) -> list[BirdfyDevice]:
        data = await self._get(f"{self._local_endpoint}/v1/devices/v3")
        data = _unwrap(data) if isinstance(data, dict) else data
        items: list[Any] = []
        if isinstance(data, dict):
            items = data.get("devices") or data.get("deviceList") or []
        elif isinstance(data, list):
            items = data
        devices = [d for d in (BirdfyDevice.from_api(i) for i in items if isinstance(i, dict)) if d]
        if not devices and isinstance(data, dict):
            _LOGGER.debug("No devices found; response keys: %s", sorted(data.keys()))
        return devices

    async def async_get_events(self, serial: str, limit: int) -> list[BirdfyEvent]:
        data = await self._get(
            f"{self.api_base}/devices/{serial}/events",
            params={"limit": limit, "ignoreAiLabels": "false", "reverse": 1},
        )
        data = _unwrap(data) if isinstance(data, dict) else data
        items = data.get("events", []) if isinstance(data, dict) else data or []
        events = [e for e in (BirdfyEvent.from_api(i) for i in items if isinstance(i, dict)) if e]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events

    async def async_get_event_picture(self, serial: str, alarm_id: str) -> bytes | None:
        """Download the snapshot of one event (the presigned URL is not kept)."""
        data = await self._get(f"{self.api_base}/devices/{serial}/events/{alarm_id}/pic")
        data = _unwrap(data) if isinstance(data, dict) else data
        url = data.get("url") if isinstance(data, dict) else None
        if not url:
            return None
        try:
            async with self._session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    _LOGGER.debug("Snapshot download failed: HTTP %s", resp.status)
                    return None
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Snapshot download failed: %s", type(err).__name__)
            return None
