"""Constants for the Home Not Alone integration."""

DOMAIN = "nothomealone"

# Configuration keys
CONF_ENTITIES = "entities"

CONF_START_TYPE = "start_type"
CONF_START_TIME = "start_time"
CONF_START_SUN_EVENT = "start_sun_event"
CONF_START_RANDOM_MIN = "start_random_min"
CONF_START_RANDOM_MAX = "start_random_max"

CONF_END_TYPE = "end_type"
CONF_END_TIME = "end_time"
CONF_END_SUN_EVENT = "end_sun_event"
CONF_END_RANDOM_MIN = "end_random_min"
CONF_END_RANDOM_MAX = "end_random_max"

# Replay Mode configuration keys
CONF_SIMULATION_MODE = "simulation_mode"
CONF_REPLAY_DAYS_BACK = "replay_days_back"
CONF_REPLAY_JITTER_MIN = "replay_jitter_min"
CONF_REPLAY_JITTER_MAX = "replay_jitter_max"

# Option values
TYPE_FIXED = "fixed"
TYPE_SUN = "sun"

SUN_SUNSET = "sunset"
SUN_SUNRISE = "sunrise"

MODE_SIMPLE = "simple"
MODE_REPLAY = "replay"

# Defaults
DEFAULT_START_TYPE = TYPE_SUN
DEFAULT_START_TIME = "18:00:00"
DEFAULT_START_SUN_EVENT = SUN_SUNSET
DEFAULT_START_RANDOM_MIN = -60
DEFAULT_START_RANDOM_MAX = 0

DEFAULT_END_TYPE = TYPE_FIXED
DEFAULT_END_TIME = "23:00:00"
DEFAULT_END_SUN_EVENT = SUN_SUNRISE
DEFAULT_END_RANDOM_MIN = 0
DEFAULT_END_RANDOM_MAX = 30

DEFAULT_SIMULATION_MODE = MODE_SIMPLE
DEFAULT_REPLAY_DAYS_BACK = 7
DEFAULT_REPLAY_JITTER_MIN = -15
DEFAULT_REPLAY_JITTER_MAX = 15
