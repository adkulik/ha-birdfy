"""Config flow for Birdfy."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
import uuid

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import BirdfyApi, BirdfyAuthError, BirdfyError, hash_password
from .const import (
    CONF_PASSWORD_HASH,
    CONF_SCAN_INTERVAL,
    CONF_SPECIES_LANGUAGE,
    CONF_UDID,
    SPECIES_LANGUAGES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class BirdfyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Birdfy."""

    VERSION = 1

    async def _async_try_login(
        self, email: str, password: str, udid: str
    ) -> tuple[str | None, str | None, int]:
        """Return (password_hash, user_id, device_count) or set an error key."""
        password_hash = hash_password(password)
        api = BirdfyApi(async_get_clientsession(self.hass), email, password_hash, udid)
        await api.async_login()
        devices = await api.async_get_devices()
        return password_hash, api.user_id, len(devices)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            udid = f"android-{uuid.uuid4()}"
            try:
                password_hash, user_id, count = await self._async_try_login(
                    email, user_input[CONF_PASSWORD], udid
                )
            except BirdfyAuthError:
                errors["base"] = "invalid_auth"
            except BirdfyError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Birdfy login")
                errors["base"] = "unknown"
            else:
                if count == 0:
                    errors["base"] = "no_devices"
                else:
                    await self.async_set_unique_id(str(user_id))
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=email,
                        data={
                            CONF_EMAIL: email,
                            CONF_PASSWORD_HASH: password_hash,
                            CONF_UDID: udid,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EMAIL, default=(user_input or {}).get(CONF_EMAIL, "")
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
                vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                password_hash, user_id, _ = await self._async_try_login(
                    entry.data[CONF_EMAIL], user_input[CONF_PASSWORD], entry.data[CONF_UDID]
                )
            except BirdfyAuthError:
                errors["base"] = "invalid_auth"
            except BirdfyError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Birdfy login")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(user_id))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD_HASH: password_hash}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BirdfyOptionsFlow()


class BirdfyOptionsFlow(OptionsFlow):
    """Options: how often to poll the Birdfy cloud."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_SPECIES_LANGUAGE: user_input[CONF_SPECIES_LANGUAGE],
                }
            )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        language = self.config_entry.options.get(CONF_SPECIES_LANGUAGE, "auto")
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=10,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_SPECIES_LANGUAGE, default=language): SelectSelector(
                    SelectSelectorConfig(
                        options=SPECIES_LANGUAGES,
                        translation_key=CONF_SPECIES_LANGUAGE,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
