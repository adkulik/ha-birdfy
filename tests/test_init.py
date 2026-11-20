"""Tests for the Birdfy integration (cloud API mocked)."""
from datetime import timedelta
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

DEVICE = BirdfyDevice(serial="SN123", name="Etető", model="Cam2 Pro", raw={"serialNumber": "SN123", "deviceName": "Etető"})


def ev(alarm_id, label, ago):
    return BirdfyEvent.from_api(
        {"alarmId": alarm_id, "alertTime": int((time.time() - ago) * 1000), "label": label,
         "description": '{"recordUrl": "https://secret"}'}
    )


def api_patch(events):
    p = "custom_components.birdfy.api.BirdfyApi"
    return [
        patch(f"{p}.async_login", AsyncMock()),
        patch(f"{p}.user_id", "42"),
        patch(f"{p}.async_get_devices", AsyncMock(return_value=[DEVICE])),
        patch(f"{p}.async_get_events", AsyncMock(side_effect=lambda *a, **k: list(events))),
        patch(f"{p}.async_get_event_picture", AsyncMock(return_value=b"\xff\xd8jpeg")),
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
    events = [ev("e2", "Great Tit", 60), ev("e1", "Blue Tit", 600)]
    entry = MockConfigEntry(domain=DOMAIN, unique_id="42", data={
        CONF_EMAIL: "a@b.hu", CONF_PASSWORD_HASH: "h", CONF_UDID: "android-x"})
    entry.add_to_hass(hass)
    patches = api_patch(events)
    for p in patches:
        p.start()
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        states = {s.entity_id: s for s in hass.states.async_all()}
        visitor = next(s for k, s in states.items() if k.endswith("last_visitor"))
        assert visitor.state == "Great Tit"
        today = next(s for k, s in states.items() if "visits_today" in k)
        assert today.state == "2"
        event_state = next(s for k, s in states.items() if k.startswith("event."))
        assert event_state.state == "unknown"  # no event fired for old visits
        img = next(s for k, s in states.items() if k.startswith("image."))
        assert img.state != "unknown"

        # A new visit appears.
        events.insert(0, ev("e3", "Robin", 5))
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
        await hass.async_block_till_done()
        event_state = hass.states.get(event_state.entity_id)
        assert event_state.state != "unknown"
        assert event_state.attributes["species"] == "Robin"
        assert event_state.attributes["event_type"] == "bird_visit"
        assert hass.states.get(visitor.entity_id).state == "Robin"
        assert hass.states.get(today.entity_id).state == "3"

        diag = await async_get_config_entry_diagnostics(hass, entry)
        text = str(diag)
        assert "SN123" not in text and "secret" not in text and "a@b.hu" not in text
        assert diag["devices"][0]["last_event_label"] == "Robin"

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
