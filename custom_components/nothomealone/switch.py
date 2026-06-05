"""Switch platform for Occupiedo integration."""
from __future__ import annotations

import datetime
import logging
import random
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util
from homeassistant.components.recorder.history import state_changes_during_period

from .const import DOMAIN, CONF_ENTITIES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Occupiedo switch platform."""
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
        self._unsub_callbacks: list[Callable[[], None]] = []

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

        if self._is_on:
            _LOGGER.info("%s: Restored as ON, scheduling simulation", self.name)
            schedule = await self._async_calculate_schedule()
            await self._async_schedule_today(schedule)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is being removed from hass."""
        _LOGGER.debug("%s: Removing entity, canceling scheduled events", self.name)
        self._cancel_scheduled_events()
        await super().async_will_remove_from_hass()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the simulation (calculate and schedule events)."""
        _LOGGER.info("Enabling simulation for %s", self.name)
        self._is_on = True
        self.async_write_ha_state()
        
        schedule = await self._async_calculate_schedule()
        await self._async_schedule_today(schedule)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the simulation (turn off all target entities and cancel scheduling)."""
        _LOGGER.info("Disabling simulation for %s: canceling schedules and turning OFF target entities", self.name)
        self._is_on = False
        self.async_write_ha_state()
        
        self._cancel_scheduled_events()
        await self._async_turn_off_entities()

    def _cancel_scheduled_events(self) -> None:
        """Cancel all scheduled callbacks."""
        for unsub in self._unsub_callbacks:
            try:
                unsub()
            except Exception as err:
                _LOGGER.debug("%s: Error canceling callback: %s", self.name, err)
        self._unsub_callbacks.clear()

    async def _async_call_service(self, service: str, entity_id: str) -> None:
        """Call turn_on/turn_off service for a specific entity."""
        try:
            await self.hass.services.async_call(
                "homeassistant",
                service,
                {"entity_id": entity_id},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("%s: Failed to call %s for %s: %s", self.name, service, entity_id, err)

    async def _async_turn_off_entities(self) -> None:
        """Turn off all controlled entities immediately."""
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

    async def _async_calculate_schedule(self) -> dict[str, tuple[float, float]]:
        """Calculate the typical turn-on and turn-off times for each entity (in seconds since midnight)."""
        schedule: dict[str, tuple[float, float]] = {}
        
        now = dt_util.now()
        start_time = now - datetime.timedelta(days=7)
        end_time = now
        
        # Check if recorder is active
        if "recorder" not in self.hass.config.components:
            _LOGGER.warning("Recorder not active, using default scheduling (19:00 - 22:00) for all entities")
            for entity_id in self._entities:
                schedule[entity_id] = (19 * 3600.0, 22 * 3600.0)
            return schedule

        for entity_id in self._entities:
            try:
                # Query history in the executor to avoid blocking the event loop
                history_data = await self.hass.async_add_executor_job(
                    state_changes_during_period,
                    self.hass,
                    start_time,
                    end_time,
                    entity_id,
                )
                
                states = history_data.get(entity_id, [])
                
                turn_on_times_by_date: dict[datetime.date, list[float]] = {}
                turn_off_times_by_date: dict[datetime.date, list[float]] = {}
                
                prev_state: str | None = None
                for state in states:
                    state_val = state.state
                    
                    # Convert last_changed to local datetime
                    local_dt = dt_util.as_local(state.last_changed)
                    dt_date = local_dt.date()
                    dt_time = local_dt.time()
                    
                    is_on_transition = (state_val == "on" and prev_state != "on" and prev_state is not None)
                    is_off_transition = (state_val != "on" and prev_state == "on" and prev_state is not None)
                    
                    prev_state = state_val
                    
                    seconds_since_midnight = dt_time.hour * 3600.0 + dt_time.minute * 60.0 + dt_time.second
                    
                    # evening window: 16:00 to 23:59:59
                    if 57600.0 <= seconds_since_midnight <= 86399.0:
                        if is_on_transition:
                            turn_on_times_by_date.setdefault(dt_date, []).append(seconds_since_midnight)
                        elif is_off_transition:
                            turn_off_times_by_date.setdefault(dt_date, []).append(seconds_since_midnight)
                
                daily_turn_ons: list[float] = []
                daily_turn_offs: list[float] = []
                
                all_dates = set(turn_on_times_by_date.keys()) | set(turn_off_times_by_date.keys())
                for dt_date in all_dates:
                    ons = turn_on_times_by_date.get(dt_date, [])
                    offs = turn_off_times_by_date.get(dt_date, [])
                    if ons:
                        daily_turn_ons.append(min(ons))
                    if offs:
                        daily_turn_offs.append(max(offs))
                
                if daily_turn_ons:
                    avg_on = sum(daily_turn_ons) / len(daily_turn_ons)
                else:
                    avg_on = 19 * 3600.0
                    
                if daily_turn_offs:
                    avg_off = sum(daily_turn_offs) / len(daily_turn_offs)
                else:
                    avg_off = 22 * 3600.0
                    
                schedule[entity_id] = (avg_on, avg_off)
                _LOGGER.debug(
                    "%s: Calculated average times for %s: ON = %02d:%02d, OFF = %02d:%02d (from %d days of data)",
                    self.name,
                    entity_id,
                    int(avg_on // 3600),
                    int((avg_on % 3600) // 60),
                    int(avg_off // 3600),
                    int((avg_off % 3600) // 60),
                    len(all_dates),
                )
                
            except Exception as err:
                _LOGGER.error(
                    "%s: Error calculating schedule for %s, falling back to default: %s",
                    self.name,
                    entity_id,
                    err,
                )
                schedule[entity_id] = (19 * 3600.0, 22 * 3600.0)
                
        return schedule

    async def _async_schedule_today(self, schedule: dict[str, tuple[float, float]]) -> None:
        """Schedule the turn-on and turn-off events for today based on averages and jitter."""
        if not self._is_on:
            _LOGGER.debug("%s: Switch is off, skipping scheduling", self.name)
            return

        self._cancel_scheduled_events()
        
        now = dt_util.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for entity_id, (avg_on, avg_off) in schedule.items():
            # Random jitter +/- 20 minutes
            jitter = random.randint(-20, 20) * 60
            target_on = avg_on + jitter
            target_off = avg_off + jitter
            
            # Enforce constraints
            target_on = max(57600.0, min(target_on, target_off - 300.0))
            target_off = max(target_on + 300.0, min(target_off, 86399.0))
            
            on_dt = today_start + datetime.timedelta(seconds=target_on)
            off_dt = today_start + datetime.timedelta(seconds=target_off)
            
            # Catch-up logic
            if on_dt <= now < off_dt:
                _LOGGER.info(
                    "%s: Catch-up for %s: current time is within window [%s, %s]. Turning ON immediately.",
                    self.name,
                    entity_id,
                    on_dt.strftime("%H:%M:%S"),
                    off_dt.strftime("%H:%M:%S"),
                )
                await self._async_call_service("turn_on", entity_id)
                self._schedule_event(entity_id, "turn_off", off_dt)
                
            elif now < on_dt:
                _LOGGER.debug(
                    "%s: Scheduling %s: ON at %s, OFF at %s",
                    self.name,
                    entity_id,
                    on_dt.strftime("%H:%M:%S"),
                    off_dt.strftime("%H:%M:%S"),
                )
                self._schedule_event(entity_id, "turn_on", on_dt)
                self._schedule_event(entity_id, "turn_off", off_dt)
                
            else:
                _LOGGER.debug(
                    "%s: %s scheduling skipped for today (past OFF time %s)",
                    self.name,
                    entity_id,
                    off_dt.strftime("%H:%M:%S"),
                )
                
        # Schedule rollover for tomorrow
        tomorrow_start = today_start + datetime.timedelta(days=1)
        rollover_dt = tomorrow_start + datetime.timedelta(seconds=5)
        
        _LOGGER.debug(
            "%s: Scheduling daily rollover at %s",
            self.name,
            rollover_dt.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._schedule_rollover(rollover_dt)

    def _schedule_event(self, entity_id: str, service: str, dt: datetime.datetime) -> None:
        """Schedule a service call at a specific datetime."""
        utc_dt = dt_util.as_utc(dt)
        
        async def _callback(_point_in_time: datetime.datetime) -> None:
            _LOGGER.info("%s: Running scheduled %s for %s", self.name, service, entity_id)
            await self._async_call_service(service, entity_id)
            
        unsub = async_track_point_in_time(self.hass, _callback, utc_dt)
        self._unsub_callbacks.append(unsub)

    def _schedule_rollover(self, dt: datetime.datetime) -> None:
        """Schedule daily rollover/recalculation at midnight."""
        utc_dt = dt_util.as_utc(dt)
        
        async def _callback(_point_in_time: datetime.datetime) -> None:
            _LOGGER.info("%s: Running daily rollover recalculation", self.name)
            schedule = await self._async_calculate_schedule()
            await self._async_schedule_today(schedule)
            
        unsub = async_track_point_in_time(self.hass, _callback, utc_dt)
        self._unsub_callbacks.append(unsub)
