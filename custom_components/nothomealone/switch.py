"""Switch platform for Home Not Alone integration."""
from __future__ import annotations

import datetime as dt
import logging
import random
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.sun import get_astral_event_date
import homeassistant.util.dt as dt_util

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
    """Switch entity that controls the presence simulation."""

    _attr_has_entity_name = True
    _attr_translation_key = "simulation_switch"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        self.entry = entry
        self._attr_name = None  # Inherits title from config entry via name integration
        self._attr_unique_id = f"switch_{entry.entry_id}"
        
        # State variables
        self._is_on = False
        self._start_time: dt.datetime | None = None
        self._end_time: dt.datetime | None = None
        self._is_active_window = False
        self._next_event: str | None = None
        self._unsub_event: Callable[[], None] | None = None
        self._replay_unsubs: list[Callable[[], None]] = []

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.entry.title

    @property
    def is_on(self) -> bool:
        """Return True if the simulation is enabled."""
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        # Read current config (merging data and options)
        config = {**self.entry.data, **self.entry.options}
        entities = config.get(CONF_ENTITIES, [])
        sim_mode = config.get(CONF_SIMULATION_MODE, DEFAULT_SIMULATION_MODE)
        
        return {
            "controlled_entities": entities,
            "simulation_mode": sim_mode,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "end_time": self._end_time.isoformat() if self._end_time else None,
            "is_active_window": self._is_active_window,
            "next_event": self._next_event,
        }

    async def async_added_to_hass(self) -> None:
        """Call when entity is about to be added to Home Assistant."""
        await super().async_added_to_hass()
        _LOGGER.debug("Entity %s added to hass. Restoring state...", self.name)
        
        # Restore the previous switch state
        state = await self.async_get_last_state()
        if state:
            if state.state == "on":
                self._is_on = True
                await self._async_schedule_next()
            else:
                self._is_on = False
                self._next_event = "Simulation disabled"
        else:
            self._is_on = False
            self._next_event = "Simulation disabled"
            
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Call when entity is being removed from Home Assistant."""
        _LOGGER.debug("Removing entity %s. Cleaning up callbacks...", self.name)
        self._cancel_callbacks()
        await super().async_will_remove_from_hass()

    def _cancel_callbacks(self) -> None:
        """Cancel any scheduled events."""
        if self._unsub_event is not None:
            self._unsub_event()
            self._unsub_event = None
        for unsub in self._replay_unsubs:
            unsub()
        self._replay_unsubs.clear()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the simulation."""
        if self._is_on:
            return
        _LOGGER.info("Enabling presence simulation for %s", self.name)
        self._is_on = True
        await self._async_schedule_next()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the simulation."""
        if not self._is_on:
            return
        _LOGGER.info("Disabling presence simulation for %s", self.name)
        self._is_on = False
        self._cancel_callbacks()
        self._start_time = None
        self._end_time = None
        self._is_active_window = False
        self._next_event = "Simulation disabled"
        
        # Turn off controlled entities on disable to prevent leaving them on
        await self._async_turn_off_entities()
        self.async_write_ha_state()

    def _calculate_time_event(
        self,
        base_date: dt.date,
        trigger_type: str,
        fixed_time: str | None,
        sun_event: str | None,
        rand_min: int,
        rand_max: int,
    ) -> dt.datetime:
        """Calculate the datetime for a schedule boundary."""
        if trigger_type == TYPE_FIXED:
            time_str = fixed_time or "18:00:00"
            time_parts = [int(x) for x in time_str.split(":")]
            time_obj = dt.time(hour=time_parts[0], minute=time_parts[1], second=time_parts[2])
            base_time = dt.datetime.combine(base_date, time_obj).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        else:
            # Sun type trigger
            event_name = sun_event or "sunset"
            try:
                event_dt = get_astral_event_date(self.hass, event_name, base_date)
                if event_dt is None:
                    raise ValueError(f"Astral calculation returned None for event '{event_name}' on date {base_date}")
                base_time = dt_util.as_local(event_dt)
            except Exception as err:
                _LOGGER.warning(
                    "Error calculating sun event %s for %s on %s. Using default fallback. Error: %s",
                    event_name,
                    self.name,
                    base_date,
                    err,
                )
                fallback_time_str = "06:00:00" if event_name == SUN_SUNRISE else "18:00:00"
                time_parts = [int(x) for x in fallback_time_str.split(":")]
                time_obj = dt.time(hour=time_parts[0], minute=time_parts[1], second=time_parts[2])
                base_time = dt.datetime.combine(base_date, time_obj).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

        # Apply random offset
        random_offset_mins = random.randint(rand_min, rand_max)
        scheduled_dt = base_time + dt.timedelta(minutes=random_offset_mins)
        return scheduled_dt

    def _calculate_window(self, base_date: dt.date) -> tuple[dt.datetime, dt.datetime]:
        """Calculate start and end times for the simulation window."""
        config = {**self.entry.data, **self.entry.options}

        start_dt = self._calculate_time_event(
            base_date,
            config.get(CONF_START_TYPE, DEFAULT_START_TYPE),
            config.get(CONF_START_TIME, DEFAULT_START_TIME),
            config.get(CONF_START_SUN_EVENT, DEFAULT_START_SUN_EVENT),
            config.get(CONF_START_RANDOM_MIN, DEFAULT_START_RANDOM_MIN),
            config.get(CONF_START_RANDOM_MAX, DEFAULT_START_RANDOM_MAX),
        )

        end_dt = self._calculate_time_event(
            base_date,
            config.get(CONF_END_TYPE, DEFAULT_END_TYPE),
            config.get(CONF_END_TIME, DEFAULT_END_TIME),
            config.get(CONF_END_SUN_EVENT, DEFAULT_END_SUN_EVENT),
            config.get(CONF_END_RANDOM_MIN, DEFAULT_END_RANDOM_MIN),
            config.get(CONF_END_RANDOM_MAX, DEFAULT_END_RANDOM_MAX),
        )

        if end_dt <= start_dt:
            next_date = base_date + dt.timedelta(days=1)
            end_dt = self._calculate_time_event(
                next_date,
                config.get(CONF_END_TYPE, DEFAULT_END_TYPE),
                config.get(CONF_END_TIME, DEFAULT_END_TIME),
                config.get(CONF_END_SUN_EVENT, DEFAULT_END_SUN_EVENT),
                config.get(CONF_END_RANDOM_MIN, DEFAULT_END_RANDOM_MIN),
                config.get(CONF_END_RANDOM_MAX, DEFAULT_END_RANDOM_MAX),
            )

        return start_dt, end_dt

    async def _async_schedule_next(self) -> None:
        """Evaluate schedule and schedule the next event."""
        self._cancel_callbacks()
        
        now = dt_util.now()
        today = now.date()
        
        # Calculate current/next window
        start_dt, end_dt = self._calculate_window(today)
        
        if now < start_dt:
            # 1. We are before start_time today
            self._start_time = start_dt
            self._end_time = end_dt
            self._is_active_window = False
            
            # Schedule start callback
            self._unsub_event = async_track_point_in_time(
                self.hass, self._async_handle_start_event, start_dt
            )
            self._next_event = f"Turn ON at {start_dt.strftime('%H:%M:%S')}"
            _LOGGER.debug("%s: Scheduled Turn ON event for %s", self.name, start_dt)
            
        elif start_dt <= now < end_dt:
            # 2. We are currently inside the active window
            self._start_time = start_dt
            self._end_time = end_dt
            self._is_active_window = True
            
            # Setup active simulation (Simple vs Replay)
            config = {**self.entry.data, **self.entry.options}
            mode = config.get(CONF_SIMULATION_MODE, DEFAULT_SIMULATION_MODE)
            
            if mode == MODE_REPLAY:
                await self._async_setup_replay_schedule()
                self._next_event = f"Replaying history. Turn OFF at {end_dt.strftime('%H:%M:%S')}"
            else:
                await self._async_turn_on_entities()
                self._next_event = f"Turn OFF at {end_dt.strftime('%H:%M:%S')}"
            
            # Schedule end callback
            self._unsub_event = async_track_point_in_time(
                self.hass, self._async_handle_end_event, end_dt
            )
            _LOGGER.debug("%s: Restoring active window. Scheduled Turn OFF event for %s", self.name, end_dt)
            
        else:
            # 3. We are past end_time today. Calculate for tomorrow.
            tomorrow = today + dt.timedelta(days=1)
            start_tomorrow, end_tomorrow = self._calculate_window(tomorrow)
            
            self._start_time = start_tomorrow
            self._end_time = end_tomorrow
            self._is_active_window = False
            
            # Schedule start callback
            self._unsub_event = async_track_point_in_time(
                self.hass, self._async_handle_start_event, start_tomorrow
            )
            self._next_event = f"Turn ON at {start_tomorrow.strftime('%H:%M:%S')}"
            _LOGGER.debug("%s: Today's window finished. Scheduled next Turn ON for %s", self.name, start_tomorrow)

    async def _async_handle_start_event(self, datetime_fired: dt.datetime) -> None:
        """Handle execution when start time callback is triggered."""
        if not self._is_on:
            return
            
        _LOGGER.info("Starting simulation active window for %s", self.name)
        self._is_active_window = True
        
        config = {**self.entry.data, **self.entry.options}
        mode = config.get(CONF_SIMULATION_MODE, DEFAULT_SIMULATION_MODE)
        
        if mode == MODE_REPLAY:
            await self._async_setup_replay_schedule()
            self._next_event = f"Replaying history. Turn OFF at {self._end_time.strftime('%H:%M:%S')}"
        else:
            # Simple mode: turn ON all entities
            await self._async_turn_on_entities()
            self._next_event = f"Turn OFF at {self._end_time.strftime('%H:%M:%S')}"
        
        # Schedule the corresponding end callback
        self._cancel_callbacks()
        self._unsub_event = async_track_point_in_time(
            self.hass, self._async_handle_end_event, self._end_time
        )
        self.async_write_ha_state()

    async def _async_handle_end_event(self, datetime_fired: dt.datetime) -> None:
        """Handle execution when end time callback is triggered."""
        if not self._is_on:
            return
            
        _LOGGER.info("Ending simulation active window for %s", self.name)
        self._is_active_window = False
        
        # Turn OFF entities
        await self._async_turn_off_entities()
        
        # Calculate new daily offsets and schedule next start
        self._cancel_callbacks()
        
        now = dt_util.now()
        tomorrow = now.date() + dt.timedelta(days=1)
        start_tomorrow, end_tomorrow = self._calculate_window(tomorrow)
        
        self._start_time = start_tomorrow
        self._end_time = end_tomorrow
        
        self._unsub_event = async_track_point_in_time(
            self.hass, self._async_handle_start_event, start_tomorrow
        )
        self._next_event = f"Turn ON at {start_tomorrow.strftime('%H:%M:%S')}"
        self.async_write_ha_state()

    async def _async_setup_replay_schedule(self) -> None:
        """Query recorder history and schedule relative replay state changes."""
        config = {**self.entry.data, **self.entry.options}
        entities = config.get(CONF_ENTITIES, [])
        
        if not entities:
            _LOGGER.warning("%s: Replay requested but no controlled entities defined", self.name)
            return

        # Check if recorder is loaded
        if "recorder" not in self.hass.config.components:
            _LOGGER.warning("%s: Recorder integration not active. Falling back to simple mode.", self.name)
            await self._async_turn_on_entities()
            return

        days_back = config.get(CONF_REPLAY_DAYS_BACK, DEFAULT_REPLAY_DAYS_BACK)
        jitter_min = config.get(CONF_REPLAY_JITTER_MIN, DEFAULT_REPLAY_JITTER_MIN)
        jitter_max = config.get(CONF_REPLAY_JITTER_MAX, DEFAULT_REPLAY_JITTER_MAX)

        # Calculate exact historical query window
        start_lookback = self._start_time - dt.timedelta(days=days_back)
        end_lookback = self._end_time - dt.timedelta(days=days_back)

        _LOGGER.info(
            "%s: Fetching history from %s ago (%s to %s)",
            self.name,
            f"{days_back} days",
            start_lookback,
            end_lookback,
        )

        from homeassistant.components.recorder.history import state_changes_during_period

        try:
            # Query history from recorder db in the executor threadpool
            history_data = await self.hass.async_add_executor_job(
                state_changes_during_period,
                self.hass,
                start_lookback,
                end_lookback,
                entities,
            )
        except Exception as err:
            _LOGGER.error(
                "%s: Failed to fetch recorder history: %s. Falling back to simple mode.",
                self.name,
                err,
            )
            await self._async_turn_on_entities()
            return

        # Fallback if no history matches
        if not history_data or all(not states for states in history_data.values()):
            _LOGGER.warning(
                "%s: No historical state changes found in recorder for lookback range. Falling back to simple mode.",
                self.name,
            )
            await self._async_turn_on_entities()
            return

        initial_on_entities: list[str] = []
        initial_off_entities: list[str] = []
        now = dt_util.now()

        # Parse history and schedule updates
        for entity_id, states in history_data.items():
            if not states:
                continue

            # First element represents the state at the start boundary
            initial_state_val = states[0].state
            other_states = states[1:]
            
            current_state_val = initial_state_val

            for state in other_states:
                state_val = state.state
                t_event = state.last_changed # UTC aware datetime
                
                # Progress offset into the lookback window
                offset = t_event - start_lookback
                t_today_est = self._start_time + offset

                if t_today_est <= now:
                    # Catch-up: This state change already happened in the relative timeline today
                    current_state_val = state_val
                else:
                    # Future event: Apply jitter and schedule it
                    jitter_mins = random.randint(jitter_min, jitter_max)
                    t_target = t_today_est + dt.timedelta(minutes=jitter_mins)
                    
                    # Clamp event within today's active window boundary
                    if t_target >= self._end_time:
                        continue
                        
                    if t_target > now:
                        # Schedule state toggle
                        unsub = async_track_point_in_time(
                            self.hass,
                            self._create_replay_callback(entity_id, state_val),
                            t_target,
                        )
                        self._replay_unsubs.append(unsub)

            # Record final caught-up initial state
            if current_state_val == "on":
                initial_on_entities.append(entity_id)
            else:
                initial_off_entities.append(entity_id)

        # Set initial catch-up states immediately
        if initial_on_entities:
            _LOGGER.debug("%s: Replay catch-up turning ON: %s", self.name, initial_on_entities)
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_on",
                    {"entity_id": initial_on_entities},
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.error("%s: Failed to set initial ON states: %s", self.name, err)

        if initial_off_entities:
            _LOGGER.debug("%s: Replay catch-up turning OFF: %s", self.name, initial_off_entities)
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": initial_off_entities},
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.error("%s: Failed to set initial OFF states: %s", self.name, err)

    def _create_replay_callback(self, entity_id: str, state_val: str) -> Callable[[dt.datetime], Any]:
        """Generate a scheduled state change callback."""
        async def _replay_callback(datetime_fired: dt.datetime) -> None:
            if not self._is_on or not self._is_active_window:
                return
            _LOGGER.info("%s: Replay toggle setting %s to %s", self.name, entity_id, state_val)
            service = "turn_on" if state_val == "on" else "turn_off"
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    service,
                    {"entity_id": entity_id},
                    blocking=True,
                )
            except Exception as err:
                _LOGGER.error("%s: Failed to execute replay callback for %s: %s", self.name, entity_id, err)
        return _replay_callback

    async def _async_turn_on_entities(self) -> None:
        """Turn on the controlled entities."""
        config = {**self.entry.data, **self.entry.options}
        entities = config.get(CONF_ENTITIES, [])
        
        if not entities:
            _LOGGER.warning("%s: No controlled entities defined to turn ON", self.name)
            return
            
        _LOGGER.info("%s: Turning ON controlled entities: %s", self.name, entities)
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
        config = {**self.entry.data, **self.entry.options}
        entities = config.get(CONF_ENTITIES, [])
        
        if not entities:
            _LOGGER.warning("%s: No controlled entities defined to turn OFF", self.name)
            return
            
        _LOGGER.info("%s: Turning OFF controlled entities: %s", self.name, entities)
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "turn_off",
                {"entity_id": entities},
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("%s: Failed to turn OFF entities: %s", self.name, err)
