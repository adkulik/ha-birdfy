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
CENTRAL_API = "https://centralapi.nvts.co"
PLAY_API = "https://api2.netvue.co"
MEDIA_BACKEND = "fused-v1"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class BirdfyError(Exception):
    """Generic Birdfy API error."""


class BirdfyAuthError(BirdfyError):
    """Login failed or the session was rejected."""

class BirdfyLiveError(BirdfyError):
    """Live view could not be started."""


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
    """One motion event from the camera, with Birdfy's AI result."""

    alarm_id: str
    timestamp: float  # seconds since epoch
    ai_status: str | None
    species: list[str]  # most frequent first
    bird_count: int
    confidence: int | None
    candidates: list[str]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    details: dict[str, Any] = field(default_factory=dict, repr=False)

    def download_request(self, serial: str) -> dict[str, Any]:
        """The eventList item the Birdfy web app sends to /event/downloadLink."""
        pictures = self.raw.get("pictureList") or ""
        if isinstance(pictures, str):
            pictures = [p for p in pictures.split(",") if p]
        item: dict[str, Any] = {
            "serialnumber": serial,
            "alarmId": self.alarm_id,
            "dataGroup": ["pic"],
            "pic": self.raw.get("pic") or "",
            "pictureList": pictures,
            "type": self.raw.get("type", 50),
        }
        for key in ("recordDir", "aiRecordDir"):
            if self.details.get(key):
                item[key] = self.details[key]
        return item

    @property
    def is_bird(self) -> bool:
        """True when Birdfy's AI found at least one bird."""
        return bool(self.species) or self.ai_status == "auto_success"

    @property
    def primary_species(self) -> str | None:
        return self.species[0] if self.species else None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BirdfyEvent | None:
        alarm_id = data.get("alarmId") or data.get("id")
        if not alarm_id:
            return None
        ts = float(data.get("alertTime") or data.get("time") or 0)
        if ts > 1e12:  # milliseconds
            ts /= 1000
        desc = data.get("description")
        if isinstance(desc, str) and desc:
            try:
                desc = json.loads(desc)
            except ValueError:
                desc = None
        if not isinstance(desc, dict):
            desc = {}

        counts: dict[str, int] = {}
        tracks: set[str] = set()
        confidence: int | None = None
        labels = desc.get("aiLabels")
        if isinstance(labels, dict):
            for frame in labels.values():
                for group in frame if isinstance(frame, list) else []:
                    if not isinstance(group, dict) or group.get("name", "bird") != "bird":
                        continue
                    for obj in group.get("objects") or []:
                        if not isinstance(obj, dict):
                            continue
                        name = str(obj.get("desc") or "").strip()
                        if name:
                            counts[name] = counts.get(name, 0) + 1
                        if obj.get("track") is not None:
                            tracks.add(str(obj["track"]))
                        conf = obj.get("confidence")
                        if isinstance(conf, (int, float)):
                            confidence = max(confidence or 0, int(conf))
        species = sorted(counts, key=lambda n: -counts[n])

        candidates: list[str] = []
        cand = data.get("candidates")
        if isinstance(cand, dict):
            for names in cand.values():
                for name in names if isinstance(names, list) else []:
                    if isinstance(name, str) and name not in candidates and name not in species:
                        candidates.append(name)

        return cls(
            alarm_id=str(alarm_id),
            timestamp=ts,
            ai_status=data.get("aiRecognitionStatus"),
            species=species,
            bird_count=len(tracks) or (1 if species else 0),
            confidence=confidence,
            candidates=candidates,
            raw=data,
            details=desc,
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
        return await self._request("GET", url, params=params)

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        """Signed request; logs in first and retries once on an expired session."""
        for attempt in (1, 2):
            if self._token is None:
                await self.async_login()
            try:
                headers = self._auth_headers()
                if json_body is not None:
                    headers["Content-Type"] = "application/json"
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    status = resp.status
                    data = await resp.json(content_type=None) if status < 500 else None
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise BirdfyError(f"Request failed: {type(err).__name__}") from err

            if status == 401 and attempt == 1:
                _LOGGER.debug("Birdfy session expired, logging in again")
                self._token = None
                continue
            if status == 401:
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

    async def async_get_event_picture(self, serial: str, event: BirdfyEvent) -> bytes | None:
        """Download the main photo of one event.

        The temporary download link is used once and never stored or logged.
        """
        data = await self._request(
            "POST",
            f"{CENTRAL_API}/event/downloadLink",
            json_body={"eventList": [event.download_request(serial)]},
        )
        data = _unwrap(data) if isinstance(data, dict) else data
        items = data.get("eventList") if isinstance(data, dict) else None
        urls: list[str] = []
        for item in items or []:
            if isinstance(item, dict) and str(item.get("alarmId")) == event.alarm_id:
                urls = [u for u in item.get("picList") or [] if isinstance(u, str)]
        if not urls:
            _LOGGER.debug(
                "No photo link for event %s; response keys: %s",
                event.alarm_id,
                sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            return None
        try:
            async with self._session.get(urls[0], timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    _LOGGER.debug("Photo download failed: HTTP %s", resp.status)
                    return None
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Photo download failed: %s", type(err).__name__)
            return None

    # --- Live view (WebRTC through the Birdfy relay, as the Birdfy web app does) ---

    async def async_live_start(self, serial: str, sensor: int) -> str:
        """Ask the camera for a live session; returns the relay session key."""
        data = await self._request(
            "POST",
            f"https://{self._region}-api2.netvue.co/devices/{serial}/play",
            json_body={
                "serialNumber": serial,
                "callType": 0,
                "sensorId": sensor,
                "provider": "AGORA_WEBRTC",
                "mediaBackendVersion": MEDIA_BACKEND,
            },
        )
        data = _unwrap(data) if isinstance(data, dict) else {}
        provider = data.get("provider")
        session_key = data.get("sessionKey")
        if provider != "NV_RELAY" or not session_key:
            _LOGGER.debug(
                "Live start not usable: provider=%s keys=%s", provider, sorted(data.keys())
            )
            raise BirdfyLiveError(f"Unsupported live provider: {provider}")
        return str(session_key)

    async def async_live_open(
        self, serial: str, sensor: int, session_key: str, external_id: str, offer: str
    ) -> str:
        """Send the WebRTC offer to the relay; returns the SDP answer."""
        data = await self._request(
            "POST",
            f"{PLAY_API}/devices/{serial}/play",
            json_body={
                "serialNumber": serial,
                "provider": "NV_RELAY",
                "mediaBackendVersion": MEDIA_BACKEND,
                "callType": 0,
                "sensorId": sensor,
                "sessionKey": session_key,
                "rtcAction": "open",
                "rtcClient": "web-client",
                "externalSessionId": external_id,
                "offer": offer,
            },
        )
        data = _unwrap(data) if isinstance(data, dict) else {}
        answer = data.get("rtcAnswer")
        if not isinstance(answer, str) or not answer.startswith("v=0"):
            _LOGGER.debug("No SDP answer; response keys: %s", sorted(data.keys()))
            raise BirdfyLiveError("The relay did not return an answer")
        return answer

    async def async_live_close(
        self, serial: str, sensor: int, session_key: str, external_id: str
    ) -> None:
        """Close a live session."""
        await self._request(
            "POST",
            f"{PLAY_API}/devices/{serial}/play",
            json_body={
                "serialNumber": serial,
                "provider": "NV_RELAY",
                "mediaBackendVersion": MEDIA_BACKEND,
                "callType": 0,
                "sensorId": sensor,
                "sessionKey": session_key,
                "rtcAction": "close",
                "rtcClient": "web-client",
                "externalSessionId": external_id,
            },
        )
