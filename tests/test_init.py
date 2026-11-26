"""Tests for the Birdfy integration (cloud API mocked)."""
from datetime import timedelta
import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.birdfy_connect.api import BirdfyAuthError, BirdfyDevice, BirdfyEvent, hash_password
from custom_components.birdfy_connect.const import CONF_PASSWORD_HASH, CONF_UDID, DOMAIN
from custom_components.birdfy_connect.diagnostics import async_get_config_entry_diagnostics

DEVICE = BirdfyDevice(serial="SN123", name="Etető", model="Cam2 Pro", raw={
    "serialNumber": "SN123", "deviceName": "Etető", "ownerEmail": "own@x.hu", "ownerNickname": "Zsiga",
    "wifiMacAddress": "e8:f4:94:00:00:01", "deviceID": 99, "ownerID": 42, "region": "eu-central-1"})


def ev(alarm_id, label, ago, extra=None):
    """An event in the real Birdfy format; label=None means motion without a bird."""
    desc = {"alarmID": alarm_id, "recordDir": "https://secret/rec"}
    status = "auto_nobirds"
    if label:
        status = "auto_success"
        desc["aiLabels"] = {
            "1": [{"name": "bird", "objects": [{"desc": label, "confidence": 80, "track": "1"}]}],
            "2": [{"name": "bird", "objects": [{"desc": label, "confidence": 70, "track": "2"}]}],
            "3": [{"name": "bird", "objects": [{"desc": extra or label, "confidence": 60, "track": "2"}]}],
        }
    return BirdfyEvent.from_api({
        "type": 50, "alarmId": alarm_id, "alertTime": int((time.time() - ago) * 1000),
        "pic": "nvs-pic:owner/abc.jpeg", "description": json.dumps(desc),
        "aiRecognitionStatus": status, "candidates": {"1": ["Eurasian Blue Tit"]} if label else None,
    })


def api_patch(events):
    p = "custom_components.birdfy_connect.api.BirdfyApi"
    return [
        patch(f"{p}.async_login", AsyncMock()),
        patch(f"{p}.user_id", "42"),
        patch(f"{p}.async_get_devices", AsyncMock(return_value=[DEVICE])),
        patch(f"{p}.async_get_events", AsyncMock(side_effect=lambda *a, **k: list(events))),
        patch(f"{p}.async_get_event_picture", AsyncMock(side_effect=lambda sn, e: f"JPEG-{e.alarm_id}".encode())),
    ]


async def test_config_flow(hass):
    patches = api_patch([])
    for p in patches:
        p.start()
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        with patch("custom_components.birdfy_connect.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_EMAIL: "a@b.hu", CONF_PASSWORD: "titok"}
            )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PASSWORD_HASH] == hash_password("titok")
        assert "titok" not in str(result["data"])
        assert CONF_PASSWORD not in result["data"]
    finally:
        for p in patches:
            p.stop()


async def test_config_flow_bad_auth(hass):
    with patch("custom_components.birdfy_connect.api.BirdfyApi.async_login", AsyncMock(side_effect=BirdfyAuthError)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: "a@b.hu", CONF_PASSWORD: "x"}
        )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_setup_and_new_visit(hass):
    events = [ev("e3", None, 30), ev("e2", "Great Tit", 60), ev("e1", "Blue Tit", 600)]
    entry = MockConfigEntry(domain=DOMAIN, unique_id="42", data={
        CONF_EMAIL: "a@b.hu", CONF_PASSWORD_HASH: "h", CONF_UDID: "android-x"})
    entry.add_to_hass(hass)
    patches = api_patch(events)
    for p in patches:
        p.start()
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        visitor = hass.states.get("sensor.eteto_last_visitor")
        assert visitor.state == "Great Tit"  # the newest event had no bird
        assert visitor.attributes["bird_count"] == 2
        assert visitor.attributes["confidence"] == 80
        assert visitor.attributes["candidates"] == ["Eurasian Blue Tit"]
        today = hass.states.get("sensor.eteto_visits_today")
        assert today.state == "2"
        assert today.attributes["species"] == {"Great Tit": 1, "Blue Tit": 1}
        event_state = hass.states.get("event.eteto_bird_visit")
        assert event_state.state == "unknown"  # no event fired for old visits
        photo = hass.states.get("image.eteto_last_visit_photo")
        assert photo.state != "unknown" and photo.attributes["species"] == "Great Tit"

        # Motion without a bird: no event.
        events.insert(0, ev("e4", None, 10))
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
        await hass.async_block_till_done()
        assert hass.states.get("event.eteto_bird_visit").state == "unknown"

        # Two new birds, a Robin with a Wren in some frames.
        events.insert(0, ev("e5", "Robin", 5, extra="Wren"))
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=122))
        await hass.async_block_till_done()
        event_state = hass.states.get("event.eteto_bird_visit")
        assert event_state.state != "unknown"
        assert event_state.attributes["species"] == "Robin"
        assert event_state.attributes["species_list"] == ["Robin", "Wren"]
        assert event_state.attributes["event_type"] == "bird_visit"
        assert hass.states.get("sensor.eteto_last_visitor").state == "Robin"
        assert hass.states.get("sensor.eteto_visits_today").state == "3"
        # The Wren counts too, even though the Robin is the main species.
        assert hass.states.get("sensor.eteto_visits_today").attributes["species"] == {
            "Great Tit": 1, "Blue Tit": 1, "Robin": 1, "Wren": 1}
        assert hass.states.get("image.eteto_last_visit_photo").attributes["species"] == "Robin"
        assert entry.runtime_data.states["SN123"].photo == b"JPEG-e5"

        diag = await async_get_config_entry_diagnostics(hass, entry)
        text = str(diag)
        for leak in ("SN123", "secret", "a@b.hu", "own@x.hu", "Zsiga", "e8:f4", "abc.jpeg"):
            assert leak not in text, leak
        assert "auto_nobirds" in text and "eu-central-1" in text
        assert diag["devices"][0]["motion_events_today"] == 5
        assert diag["devices"][0]["last_visit_species"] == ["Robin", "Wren"]

        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        for p in patches:
            p.stop()


async def test_auth_failure_starts_reauth(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="42", data={
        CONF_EMAIL: "a@b.hu", CONF_PASSWORD_HASH: "h", CONF_UDID: "android-x"})
    entry.add_to_hass(hass)
    with patch("custom_components.birdfy_connect.api.BirdfyApi.async_get_devices", AsyncMock(side_effect=BirdfyAuthError("x"))):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


def test_hungarian_names():
    from custom_components.birdfy_connect.species import translate
    assert translate("Great Tit", "hu") == "Széncinege"
    assert translate("Eurasian Blue Tit", "hu") == "Kék cinege"
    assert translate("European Robin", "hu") == "Vörösbegy"
    assert translate("great spotted woodpecker", "hu") == "Nagy fakopáncs"
    assert translate("Unknown Bird", "hu") == "Unknown Bird"
    assert translate("Great Tit", "en") == "Great Tit"


async def test_hungarian_entities(hass):
    from custom_components.birdfy_connect.const import CONF_SPECIES_LANGUAGE
    hass.config.language = "hu"
    events = [ev("e2", "Great Tit", 60, extra="Eurasian Blue Tit"), ev("e1", "Great Tit", 600)]
    entry = MockConfigEntry(domain=DOMAIN, unique_id="42", data={
        CONF_EMAIL: "a@b.hu", CONF_PASSWORD_HASH: "h", CONF_UDID: "android-x"})
    entry.add_to_hass(hass)
    patches = api_patch(events)
    for p in patches:
        p.start()
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        visitor = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("latogato") or s.entity_id.endswith("last_visitor"))
        assert visitor.state == "Széncinege"
        assert visitor.attributes["species_en"] == "Great Tit"
        assert visitor.attributes["species_list"] == ["Széncinege", "Kék cinege"]
        assert visitor.attributes["candidates"] == []  # already in species_list

        # Switch to English in the options.
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 60, CONF_SPECIES_LANGUAGE: "en"})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        visitor = hass.states.get(visitor.entity_id)
        assert visitor.state == "Great Tit"
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        for p in patches:
            p.stop()


def test_add_candidates():
    from webrtc_models import RTCIceCandidateInit
    from custom_components.birdfy_connect.camera import add_candidates
    offer = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\na=group:BUNDLE 0 1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=mid:0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=mid:1\r\n"
    out = add_candidates(offer, [
        RTCIceCandidateInit("candidate:1 1 udp 2122260223 192.168.1.5 50000 typ host", sdp_mid="0"),
        RTCIceCandidateInit("candidate:2 1 udp 1686052607 1.2.3.4 50000 typ srflx", sdp_m_line_index=1),
    ])
    lines = out.split("\r\n")
    assert lines.index("a=candidate:1 1 udp 2122260223 192.168.1.5 50000 typ host") < lines.index("m=video 9 UDP/TLS/RTP/SAVPF 96")
    assert lines[-3] == "a=candidate:2 1 udp 1686052607 1.2.3.4 50000 typ srflx"
    assert out.endswith("a=end-of-candidates\r\n")
    assert add_candidates(offer, []) == offer


async def test_live_view(hass):
    from webrtc_models import RTCIceCandidateInit
    from homeassistant.components.camera import WebRTCAnswer, WebRTCError
    from homeassistant.helpers import entity_component
    from custom_components.birdfy_connect.api import BirdfyLiveError
    events = [ev("e1", "Great Tit", 60)]
    entry = MockConfigEntry(domain=DOMAIN, unique_id="42", data={
        CONF_EMAIL: "a@b.hu", CONF_PASSWORD_HASH: "h", CONF_UDID: "android-x"})
    entry.add_to_hass(hass)
    p = "custom_components.birdfy_connect.api.BirdfyApi"
    start = AsyncMock(return_value="SN123_0_LIVING")
    open_ = AsyncMock(return_value="v=0\r\nanswer\r\n")
    close = AsyncMock()
    patches = api_patch(events) + [
        patch(f"{p}.async_live_start", start), patch(f"{p}.async_live_open", open_), patch(f"{p}.async_live_close", close)]
    for x in patches:
        x.start()
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        cams = [s.entity_id for s in hass.states.async_all("camera")]
        assert sorted(cams) == ["camera.eteto_live_view", "camera.eteto_live_view_second_lens"]
        cam = hass.data["entity_components"]["camera"].get_entity("camera.eteto_live_view")
        assert cam.camera_capabilities.frontend_stream_types == {"web_rtc"}
        assert await cam.async_camera_image() == b"JPEG-e1"

        msgs = []
        offer = "v=0\r\na=group:BUNDLE 0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=mid:0\r\n"
        task = hass.async_create_task(cam.async_handle_async_webrtc_offer(offer, "s1", msgs.append))
        await asyncio.sleep(0)
        await cam.async_on_webrtc_candidate("s1", RTCIceCandidateInit("candidate:1 1 udp 1 10.0.0.2 5000 typ host", sdp_mid="0"))
        await cam.async_on_webrtc_candidate("s1", RTCIceCandidateInit(""))
        await task
        assert isinstance(msgs[0], WebRTCAnswer) and msgs[0].answer.startswith("v=0")
        sent_offer = open_.call_args.args[4]
        assert "a=candidate:1 1 udp 1 10.0.0.2 5000 typ host" in sent_offer
        assert start.call_args.args[1] == 0
        cam.close_webrtc_session("s1")
        await hass.async_block_till_done()
        assert close.await_count == 1

        # Error path
        start.side_effect = BirdfyLiveError("nope")
        msgs.clear()
        await cam.async_handle_async_webrtc_offer(offer, "s2", msgs.append)
        assert isinstance(msgs[0], WebRTCError)
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        for x in patches:
            x.stop()


def test_resolve_language():
    from custom_components.birdfy_connect.species import resolve_language
    available = {"de": "Deutsch", "hu": "Magyar", "nb": "Norsk", "pt": "Português",
                 "pt-BR": "Português (Brasil)", "zh-Hans": "简体中文"}
    assert resolve_language("auto", "de", available) == "de"
    assert resolve_language("auto", "pt-BR", available) == "pt-BR"
    assert resolve_language("auto", "nn", available) == "nb"
    assert resolve_language("auto", "zh-Hant", available) == "zh-Hans"
    assert resolve_language("auto", "xx", available) == "en"
    assert resolve_language("de", "hu", available) == "de"
    assert resolve_language("xx", "hu", available) == "en"


def test_ioc_names():
    from custom_components.birdfy_connect.species import load_language, translate
    for lang in ("de", "fr", "hu"):
        load_language(lang)
    assert translate("Great Tit", "de") == "Kohlmeise"
    assert translate("Blue Tit", "de") == "Blaumeise"  # IOC: Eurasian Blue Tit
    assert translate("Robin", "de") == "Rotkehlchen"  # IOC: European Robin
    assert translate("Great Tit", "fr") == "Mésange charbonnière"
    assert translate("Great Tit", "hu") == "Széncinege"  # curated name wins
    assert translate("Some Unknown Bird", "de") == "Some Unknown Bird"


async def test_german_entities(hass):
    hass.config.language = "de"
    events = [ev("e2", "Great Tit", 60, extra="Eurasian Blue Tit")]
    entry = MockConfigEntry(domain=DOMAIN, unique_id="42", data={
        CONF_EMAIL: "a@b.hu", CONF_PASSWORD_HASH: "h", CONF_UDID: "android-x"})
    entry.add_to_hass(hass)
    patches = api_patch(events)
    for p in patches:
        p.start()
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        photo = next(s for s in hass.states.async_all("image"))
        assert photo.attributes["species"] == "Kohlmeise"
        assert photo.attributes["species_list"] == ["Kohlmeise", "Blaumeise"]
        assert photo.attributes["species_en"] == "Great Tit"

        result = await hass.config_entries.options.async_init(entry.entry_id)
        values = [o["value"] for o in result["data_schema"].schema["species_language"].config["options"]]
        assert values[:2] == ["auto", "en"] and "de" in values and "hu" in values
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        for p in patches:
            p.stop()
