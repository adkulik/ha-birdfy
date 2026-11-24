"""Camera entities: live view over WebRTC, as in the Birdfy web app.

The video goes directly from the Birdfy relay server to the browser or the
Home Assistant app; Home Assistant only relays the signaling (offer/answer),
so it does not decode or transcode anything.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import uuid

from webrtc_models import RTCIceCandidateInit

from homeassistant.components.camera import (
    Camera,
    CameraEntityFeature,
    WebRTCAnswer,
    WebRTCError,
    WebRTCSendMessage,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import BirdfyError
from .coordinator import BirdfyConfigEntry, BirdfyCoordinator
from .entity import BirdfyEntity

_LOGGER = logging.getLogger(__name__)

# How long to collect the browser's ICE candidates before sending the offer.
# The relay expects a complete offer (no trickle ICE), like the Birdfy web app sends.
CANDIDATE_WAIT = 1.5
# Live sessions are closed after this long to save the camera battery.
MAX_SESSION_SECONDS = 10 * 60

SENSORS = (
    (0, "live_main"),
    (1, "live_secondary"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BirdfyLiveCamera(coordinator, serial, sensor, key)
        for serial in coordinator.states
        for sensor, key in SENSORS
    )


@dataclass
class _Session:
    sensor: int
    external_id: str
    session_key: str | None = None
    candidates: list[RTCIceCandidateInit] = field(default_factory=list)
    gathering_done: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False
    offer_sent: bool = False
    timer: asyncio.TimerHandle | None = None


def add_candidates(offer: str, candidates: list[RTCIceCandidateInit]) -> str:
    """Put trickled ICE candidates into the offer SDP (non-trickle offer)."""
    if not candidates:
        return offer
    lines = offer.split("\r\n")
    trailing = lines and lines[-1] == ""
    if trailing:
        lines = lines[:-1]
    # Find the start of each m= section and its mid.
    sections: list[tuple[int, str | None]] = []
    for i, line in enumerate(lines):
        if line.startswith("m="):
            sections.append((i, None))
        elif line.startswith("a=mid:") and sections:
            start, _ = sections[-1]
            sections[-1] = (start, line[6:])
    if not sections:
        return offer
    per_section: dict[int, list[str]] = {i: [] for i in range(len(sections))}
    for cand in candidates:
        text = cand.candidate.strip()
        if not text:
            continue
        if not text.startswith("candidate:"):
            text = text.removeprefix("a=")
        index = None
        if cand.sdp_mid is not None:
            index = next((n for n, (_, mid) in enumerate(sections) if mid == cand.sdp_mid), None)
        if index is None and cand.sdp_m_line_index is not None and cand.sdp_m_line_index < len(sections):
            index = cand.sdp_m_line_index
        per_section[index or 0].append(f"a={text}")
    out: list[str] = []
    bounds = [start for start, _ in sections] + [len(lines)]
    out.extend(lines[: bounds[0]])
    for n in range(len(sections)):
        out.extend(lines[bounds[n] : bounds[n + 1]])
        out.extend(per_section[n])
        if per_section[n]:
            out.append("a=end-of-candidates")
    return "\r\n".join(out) + ("\r\n" if trailing else "")


class BirdfyLiveCamera(BirdfyEntity, Camera):
    """Live view of one lens of a Birdfy camera."""

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self, coordinator: BirdfyCoordinator, serial: str, sensor: int, key: str
    ) -> None:
        BirdfyEntity.__init__(self, coordinator, serial, key)
        Camera.__init__(self)
        self._sensor = sensor
        self._sessions: dict[str, _Session] = {}
        self.content_type = "image/jpeg"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Still image: the photo of the latest bird visit."""
        return self.state_data.photo

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        api = self.coordinator.api
        serial = self._serial
        session = _Session(sensor=self._sensor, external_id=str(uuid.uuid4()))
        self._sessions[session_id] = session
        try:
            start = asyncio.create_task(api.async_live_start(serial, self._sensor))
            try:
                await asyncio.wait_for(session.gathering_done.wait(), CANDIDATE_WAIT)
            except TimeoutError:
                pass
            session.session_key = await start
            if session.closed:
                await self._async_close(session)
                return
            session.offer_sent = True
            offer = add_candidates(offer_sdp, session.candidates)
            answer = await api.async_live_open(
                serial, self._sensor, session.session_key, session.external_id, offer
            )
        except BirdfyError as err:
            _LOGGER.warning("Birdfy live view could not start: %s", err)
            self._sessions.pop(session_id, None)
            if session.session_key:
                self.hass.async_create_task(self._async_close(session))
            send_message(WebRTCError("birdfy_live_error", str(err)))
            return
        if session.closed:
            await self._async_close(session)
            return
        send_message(WebRTCAnswer(answer))
        session.timer = self.hass.loop.call_later(
            MAX_SESSION_SECONDS, self.close_webrtc_session, session_id
        )

    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        if not candidate.candidate:
            session.gathering_done.set()
            return
        if not session.offer_sent:
            session.candidates.append(candidate)

    @callback
    def close_webrtc_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        session.closed = True
        session.gathering_done.set()
        if session.timer:
            session.timer.cancel()
        if session.session_key:
            self.hass.async_create_task(self._async_close(session))

    async def _async_close(self, session: _Session) -> None:
        if not session.session_key:
            return
        try:
            await self.coordinator.api.async_live_close(
                self._serial, session.sensor, session.session_key, session.external_id
            )
        except BirdfyError as err:
            _LOGGER.debug("Closing the live session failed: %s", err)

    async def async_will_remove_from_hass(self) -> None:
        for session_id in list(self._sessions):
            self.close_webrtc_session(session_id)
        await super().async_will_remove_from_hass()
