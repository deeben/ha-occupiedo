"""Config flow for Home Not Alone integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_ENTITIES,
    CONF_START_TYPE,
    CONF_START_TIME,
    CONF_START_SUN_EVENT,
    CONF_START_RANDOM_MIN,
    CONF_START_RANDOM_MAX,
    CONF_END_TYPE,
    CONF_END_TIME,
    CONF_END_SUN_EVENT,
    CONF_END_RANDOM_MIN,
    CONF_END_RANDOM_MAX,
    CONF_SIMULATION_MODE,
    CONF_REPLAY_DAYS_BACK,
    CONF_REPLAY_JITTER_MIN,
    CONF_REPLAY_JITTER_MAX,
    TYPE_FIXED,
    TYPE_SUN,
    SUN_SUNSET,
    SUN_SUNRISE,
    MODE_SIMPLE,
    MODE_REPLAY,
    DEFAULT_START_TYPE,
    DEFAULT_START_TIME,
    DEFAULT_START_SUN_EVENT,
    DEFAULT_START_RANDOM_MIN,
    DEFAULT_START_RANDOM_MAX,
    DEFAULT_END_TYPE,
    DEFAULT_END_TIME,
    DEFAULT_END_SUN_EVENT,
    DEFAULT_END_RANDOM_MIN,
    DEFAULT_END_RANDOM_MAX,
    DEFAULT_SIMULATION_MODE,
    DEFAULT_REPLAY_DAYS_BACK,
    DEFAULT_REPLAY_JITTER_MIN,
    DEFAULT_REPLAY_JITTER_MAX,
)


def get_schedule_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return the schedule schema with defaults/suggested values."""
    return vol.Schema(
        {
            vol.Required(
                CONF_SIMULATION_MODE,
                default=defaults.get(CONF_SIMULATION_MODE, DEFAULT_SIMULATION_MODE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[MODE_SIMPLE, MODE_REPLAY],
                    translation_key="simulation_mode",
                    mode="dropdown",
                )
            ),
            vol.Required(
                CONF_REPLAY_DAYS_BACK,
                default=defaults.get(CONF_REPLAY_DAYS_BACK, DEFAULT_REPLAY_DAYS_BACK),
            ): vol.Coerce(int),
            vol.Required(
                CONF_REPLAY_JITTER_MIN,
                default=defaults.get(CONF_REPLAY_JITTER_MIN, DEFAULT_REPLAY_JITTER_MIN),
            ): vol.Coerce(int),
            vol.Required(
                CONF_REPLAY_JITTER_MAX,
                default=defaults.get(CONF_REPLAY_JITTER_MAX, DEFAULT_REPLAY_JITTER_MAX),
            ): vol.Coerce(int),
            vol.Required(
                CONF_START_TYPE, default=defaults.get(CONF_START_TYPE, DEFAULT_START_TYPE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[TYPE_FIXED, TYPE_SUN],
                    translation_key="start_type",
                    mode="dropdown",
                )
            ),
            vol.Optional(
                CONF_START_TIME, default=defaults.get(CONF_START_TIME, DEFAULT_START_TIME)
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_START_SUN_EVENT,
                default=defaults.get(CONF_START_SUN_EVENT, DEFAULT_START_SUN_EVENT),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SUN_SUNSET, SUN_SUNRISE],
                    translation_key="start_sun_event",
                    mode="dropdown",
                )
            ),
            vol.Required(
                CONF_START_RANDOM_MIN,
                default=defaults.get(CONF_START_RANDOM_MIN, DEFAULT_START_RANDOM_MIN),
            ): vol.Coerce(int),
            vol.Required(
                CONF_START_RANDOM_MAX,
                default=defaults.get(CONF_START_RANDOM_MAX, DEFAULT_START_RANDOM_MAX),
            ): vol.Coerce(int),
            vol.Required(
                CONF_END_TYPE, default=defaults.get(CONF_END_TYPE, DEFAULT_END_TYPE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[TYPE_FIXED, TYPE_SUN],
                    translation_key="end_type",
                    mode="dropdown",
                )
            ),
            vol.Optional(
                CONF_END_TIME, default=defaults.get(CONF_END_TIME, DEFAULT_END_TIME)
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_END_SUN_EVENT,
                default=defaults.get(CONF_END_SUN_EVENT, DEFAULT_END_SUN_EVENT),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SUN_SUNSET, SUN_SUNRISE],
                    translation_key="end_sun_event",
                    mode="dropdown",
                )
            ),
            vol.Required(
                CONF_END_RANDOM_MIN,
                default=defaults.get(CONF_END_RANDOM_MIN, DEFAULT_END_RANDOM_MIN),
            ): vol.Coerce(int),
            vol.Required(
                CONF_END_RANDOM_MAX,
                default=defaults.get(CONF_END_RANDOM_MAX, DEFAULT_END_RANDOM_MAX),
            ): vol.Coerce(int),
        }
    )


def validate_schedule_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate schedule settings and return dict of errors."""
    errors: dict[str, str] = {}

    start_type = user_input.get(CONF_START_TYPE)
    end_type = user_input.get(CONF_END_TYPE)

    # Validate start requirements
    if start_type == TYPE_FIXED and not user_input.get(CONF_START_TIME):
        errors[CONF_START_TIME] = "start_time_required"
    if start_type == TYPE_SUN and not user_input.get(CONF_START_SUN_EVENT):
        errors[CONF_START_SUN_EVENT] = "start_sun_event_required"

    # Validate end requirements
    if end_type == TYPE_FIXED and not user_input.get(CONF_END_TIME):
        errors[CONF_END_TIME] = "end_time_required"
    if end_type == TYPE_SUN and not user_input.get(CONF_END_SUN_EVENT):
        errors[CONF_END_SUN_EVENT] = "end_sun_event_required"

    # Validate random range
    start_min = user_input.get(CONF_START_RANDOM_MIN)
    start_max = user_input.get(CONF_START_RANDOM_MAX)
    if start_min is not None and start_max is not None:
        try:
            if int(start_min) > int(start_max):
                errors[CONF_START_RANDOM_MIN] = "start_min_greater_than_max"
        except (ValueError, TypeError):
            pass

    end_min = user_input.get(CONF_END_RANDOM_MIN)
    end_max = user_input.get(CONF_END_RANDOM_MAX)
    if end_min is not None and end_max is not None:
        try:
            if int(end_min) > int(end_max):
                errors[CONF_END_RANDOM_MIN] = "end_min_greater_than_max"
        except (ValueError, TypeError):
            pass

    # Validate Replay Mode parameters
    sim_mode = user_input.get(CONF_SIMULATION_MODE)
    if sim_mode == MODE_REPLAY:
        replay_days = user_input.get(CONF_REPLAY_DAYS_BACK)
        if replay_days is not None:
            try:
                if int(replay_days) <= 0:
                    errors[CONF_REPLAY_DAYS_BACK] = "replay_days_back_invalid"
            except (ValueError, TypeError):
                errors[CONF_REPLAY_DAYS_BACK] = "replay_days_back_invalid"
                
        jitter_min = user_input.get(CONF_REPLAY_JITTER_MIN)
        jitter_max = user_input.get(CONF_REPLAY_JITTER_MAX)
        if jitter_min is not None and jitter_max is not None:
            try:
                if int(jitter_min) > int(jitter_max):
                    errors[CONF_REPLAY_JITTER_MIN] = "replay_jitter_min_greater_than_max"
            except (ValueError, TypeError):
                pass

    return errors


class NotHomeAloneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Home Not Alone."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.init_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Handle profile name and entity list."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.init_data = user_input
            return await self.async_step_schedule()

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

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Handle schedule and offsets."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = validate_schedule_input(user_input)
            if not errors:
                combined_data = {**self.init_data, **user_input}
                return self.async_create_entry(
                    title=self.init_data["name"], data=combined_data
                )

        schema_defaults = {
            CONF_SIMULATION_MODE: DEFAULT_SIMULATION_MODE,
            CONF_REPLAY_DAYS_BACK: DEFAULT_REPLAY_DAYS_BACK,
            CONF_REPLAY_JITTER_MIN: DEFAULT_REPLAY_JITTER_MIN,
            CONF_REPLAY_JITTER_MAX: DEFAULT_REPLAY_JITTER_MAX,
            CONF_START_TYPE: DEFAULT_START_TYPE,
            CONF_START_TIME: DEFAULT_START_TIME,
            CONF_START_SUN_EVENT: DEFAULT_START_SUN_EVENT,
            CONF_START_RANDOM_MIN: DEFAULT_START_RANDOM_MIN,
            CONF_START_RANDOM_MAX: DEFAULT_START_RANDOM_MAX,
            CONF_END_TYPE: DEFAULT_END_TYPE,
            CONF_END_TIME: DEFAULT_END_TIME,
            CONF_END_SUN_EVENT: DEFAULT_END_SUN_EVENT,
            CONF_END_RANDOM_MIN: DEFAULT_END_RANDOM_MIN,
            CONF_END_RANDOM_MAX: DEFAULT_END_RANDOM_MAX,
        }

        if user_input is not None:
            schema_defaults.update(user_input)

        return self.async_show_form(
            step_id="schedule",
            data_schema=get_schedule_schema(schema_defaults),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NotHomeAloneOptionsFlowHandler:
        """Get the options flow for this handler."""
        return NotHomeAloneOptionsFlowHandler(config_entry)


class NotHomeAloneOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Not Home Alone options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = validate_schedule_input(user_input)
            if not errors:
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
        ).extend(get_schedule_schema(current_config).schema)

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
