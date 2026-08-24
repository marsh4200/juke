"""Constants for the Juke Audio integration."""
from datetime import timedelta

DOMAIN = "juke"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SSL = "ssl"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_PORT = 80
DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = False
DEFAULT_USERNAME = "Admin"
DEFAULT_PASSWORD = "Admin"

API_BASE_PATH = "/api/v3"

UPDATE_INTERVAL = timedelta(seconds=30)

MANUFACTURER = "Juke Audio"

# Juke reports volume 0-100; HA media_player expects a 0.0-1.0 float.
JUKE_VOLUME_MAX = 100

# Device model enum values returned by GET /devices/{device_id}/model
MODEL_NAMES = {
    "JUKE_PLUS": "Juke Plus",
    "JUKE_CLASSIC": "Juke Classic",
}
