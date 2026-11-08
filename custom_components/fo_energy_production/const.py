"""Constants for the Faroese energy production integration."""
from __future__ import annotations

DOMAIN = "fo_energy_production"

CONF_AREAS = "areas"

AREAS = {
    "suduroy": {"name": "Suðuroy", "source": "sev", "station_id": "suduroy"},
    "main": {"name": "Main area", "source": "sev", "station_id": "main"},
    "total": {"name": "All production ", "source": "sev", "station_id": "total"},
}

DEFAULT_AREAS = list(AREAS)
