"""Config flow for Occupiedo integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import DOMAIN, CONF_ENTITIES


class NotHomeAloneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Occupiedo."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title=user_input["name"], data=user_input
            )

        entities_schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Required(CONF_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=entities_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NotHomeAloneOptionsFlowHandler:
        """Get the options flow for this handler."""
        return NotHomeAloneOptionsFlowHandler(config_entry)


class NotHomeAloneOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Occupiedo options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_config = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            current_config.update(user_input)

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENTITIES, default=current_config.get(CONF_ENTITIES, [])
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
