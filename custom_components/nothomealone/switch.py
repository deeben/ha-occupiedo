"""Switch platform for Home Not Alone integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CONF_ENTITIES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Home Not Alone switch platform."""
    _LOGGER.debug("Setting up switch platform for entry %s", entry.title)
    async_add_entities([NotHomeAloneSimulationSwitch(entry)])


class NotHomeAloneSimulationSwitch(SwitchEntity, RestoreEntity):
    """Switch entity that controls the presence simulation (baseline group switch)."""

    _attr_has_entity_name = True
    _attr_translation_key = "simulation_switch"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self.entry = entry
        self._attr_name = None  # Inherits title from config entry
        self._attr_unique_id = f"switch_{entry.entry_id}"
        self._is_on = False

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.entry.title

    @property
    def is_on(self) -> bool:
        """Return True if the simulation is enabled."""
        return self._is_on

    @property
    def _entities(self) -> list[str]:
        """Return the list of controlled entities."""
        config = {**self.entry.data, **self.entry.options}
        return config.get(CONF_ENTITIES, [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "controlled_entities": self._entities,
        }

    async def async_added_to_hass(self) -> None:
        """Call when entity is about to be added to Home Assistant."""
        await super().async_added_to_hass()
        _LOGGER.debug("Entity %s added to hass. Restoring state...", self.name)
        
        # Restore the previous switch state
        state = await self.async_get_last_state()
        if state:
            self._is_on = (state.state == "on")
        else:
            self._is_on = False
            
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the simulation (turn on all target entities)."""
        _LOGGER.info("Enabling simulation for %s: turning ON target entities", self.name)
        self._is_on = True
        await self._async_turn_on_entities()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the simulation (turn off all target entities)."""
        _LOGGER.info("Disabling simulation for %s: turning OFF target entities", self.name)
        self._is_on = False
        await self._async_turn_off_entities()
        self.async_write_ha_state()

    async def _async_turn_on_entities(self) -> None:
        """Turn on the controlled entities."""
        entities = self._entities
        if not entities:
            _LOGGER.warning("%s: No controlled entities defined to turn ON", self.name)
            return
            
        _LOGGER.debug("%s: Turning ON controlled entities: %s", self.name, entities)
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_on",
                {"entity_id": entities},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("%s: Failed to turn ON entities: %s", self.name, err)

    async def _async_turn_off_entities(self) -> None:
        """Turn off the controlled entities."""
        entities = self._entities
        if not entities:
            _LOGGER.warning("%s: No controlled entities defined to turn OFF", self.name)
            return
            
        _LOGGER.debug("%s: Turning OFF controlled entities: %s", self.name, entities)
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entities},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("%s: Failed to turn OFF entities: %s", self.name, err)
