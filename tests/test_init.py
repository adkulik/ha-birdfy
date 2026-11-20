"""Tests for the Birdfy integration (cloud API mocked)."""
from datetime import timedelta
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

from custom_components.birdfy.api import BirdfyAuthError, BirdfyDevice, BirdfyEvent, hash_password
from custom_components.birdfy.const import CONF_PASSWORD_HASH, CONF_UDID, DOMAIN
from custom_components.birdfy.diagnostics import async_get_config_entry_diagnostics

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
    p = "custom_components.birdfy.api.BirdfyApi"
    return [
        patch(f"{p}.async_login", AsyncMock()),
        patch(f"{p}.user_id", "42"),
        patch(f"{p}.async_get_devices", AsyncMock(return_value=[DEVICE])),
        patch(f"{p}.async_get_events", AsyncMock(side_effect=lambda *a, **k: list(events))),
    ]


async def test_config_flow(hass):
    patches = api_patch([])
    for p in patches:
        p.start()
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        with patch("custom_components.birdfy.async_setup_entry", return_value=True):
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
    with patch("custom_components.birdfy.api.BirdfyApi.async_login", AsyncMock(side_effect=BirdfyAuthError)):
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
        assert hass.states.get("image.eteto_last_visit_photo") is None

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
    with patch("custom_components.birdfy.api.BirdfyApi.async_get_devices", AsyncMock(side_effect=BirdfyAuthError("x"))):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())
