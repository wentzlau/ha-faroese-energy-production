"""Platform for sensor integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
import re

import aiohttp
import async_timeout

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from homeassistant.helpers.typing import HomeAssistantType, ConfigType
from homeassistant.components import sensor
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_MONITORED_CONDITIONS, CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE,
    TEMP_FAHRENHEIT, TEMP_CELSIUS, LENGTH_INCHES,
    LENGTH_FEET, LENGTH_MILLIMETERS, LENGTH_METERS, SPEED_MILES_PER_HOUR, SPEED_KILOMETERS_PER_HOUR,
    PERCENTAGE, PRESSURE_INHG, PRESSURE_MBAR, PRECIPITATION_INCHES_PER_HOUR, PRECIPITATION_MILLIMETERS_PER_HOUR,
    ATTR_ATTRIBUTION)
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import Throttle
import homeassistant.helpers.config_validation as cv
from homeassistant.util.unit_system import METRIC_SYSTEM

import voluptuous as vol
import json

_LOGGER = logging.getLogger("foenergy")

SEV_URL = "https://www.sev.fo/api/realtimemap/now"
CONF_AREAS= "areas"

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)
CONF_ATTRIBUTION = "Data provided by the sev (sev.fo)"
TEMPUNIT = 0
LENGTHUNIT = 1
ALTITUDEUNIT = 2
SPEEDUNIT = 3
PRESSUREUNIT = 4
RATE = 5
PERCENTAGEUNIT = 6


class EnergySensorConfig:
    """Sensor Configuration.
    defines basic HA properties of the energy sensor and
    stores callbacks that can parse sensor values out of
    the json data received by WU API.
    """

    def __init__(self, friendly_name, feature, value,
                 unit_of_measurement=None, entity_picture=None,
                 icon="mdi:gauge", device_state_attributes=None,
                 device_class=None):
        """Constructor.
        Args:
            friendly_name (string|func): Friendly name
            feature (string): WU feature. See:
                https://docs.google.com/document/d/1eKCnKXI9xnoMGRRzOL1xPCBihNV2rOet08qpE_gArAY/edit
            value (function(WUndergroundData)): callback that
                extracts desired value from WUndergroundData object
            unit_of_measurement (string): unit of measurement
            entity_picture (string): value or callback returning
                URL of entity picture
            icon (string): icon name
            device_state_attributes (dict): dictionary of attributes,
                or callable that returns it
        """
        self.friendly_name = friendly_name
        self.unit_of_measurement = unit_of_measurement
        self.feature = feature
        self.value = value
        self.entity_picture = entity_picture
        self.icon = icon
        self.device_state_attributes = device_state_attributes or {}
        self.device_class = device_class
        


class EnergyCurrentConditionsSensorConfig(EnergySensorConfig):
    """Helper for defining sensor configurations for current conditions."""

    def __init__(self, friendly_name, area_id, field, field_type , icon="mdi:gauge",
                 unit_of_measurement=None, device_class=None):
        """Constructor.
        Args:
            friendly_name (string|func): Friendly name of sensor
            field (string): Field name in the "observations[0][unit_system]"
                            dictionary.
            icon (string): icon name , if None sensor
                           will use current weather symbol
            unit_of_measurement (string): unit of measurement
        """
        super().__init__(
            friendly_name,
            "conditions",
            value=lambda wu: wu.data['areas'][area_id][field][field_type],
            icon=icon,
            unit_of_measurement= unit_of_measurement,
            device_state_attributes={
                'date': lambda wu: wu.data['time']
            },
            device_class=device_class
        )



#

SENSOR_TYPES = {
    # current
    'oil_p': {
        'name': 'energy production by Oil (percentage)',
        'unit_of_measurement': '%',
        'icon': "mdi:barrel",
        'device_class': "power_factor",
        'state_class': "measurement"
    },
    'wind_p': {
        'name': 'energy production by wind (percentage)',
        'unit_of_measurement': '%',
        'icon':"mdi:wind-turbine",
        'device_class': "power_factor",
        'state_class': "measurement"
    },
    'hydro_p': {
        'name': 'energy production from hydro (percentage)',
        'unit_of_measurement': '%',
        'icon': "mdi:water",
        'device_class': "power_factor",
        'state_class': "measurement"
    },
    'solar_p': {
        'name': 'energy production from solar (percentage)',
        'icon': 'mdi:solar-power',
        'unit_of_measurement': '%',
        'device_class': "power_factor",
        'state_class': "measurement"
    },
    'tidal_p': {
        'name': 'energy production from tidal (percentage)',
        'icon': "mdi:gauge",
        'unit_of_measurement': "%",
        'device_class': "power_factor",
        'state_class': "measurement"
    },
    'biogas_p':{
        'name': 'energy production from biogas (percentage)', 
        'icon': "mdi:gauge",
        'unit_of_measurement': "%",
        'device_class': "power_factor",
        'state_class': "measurement"
    },
    'fossilFree_p':{
        'name': 'energy production from fossil free sources (percentage)', 
        'icon': "mdi:leaf-circle",
        'unit_of_measurement': "%",
        'device_class': "power_factor",
        'state_class': "measurement"
    },
    'oil_e': {
        'name': 'energy production by Oil',
        'unit_of_measurement': 'MW',
        'icon': "mdi:barrel",
        'device_class': "power",
        'state_class': "measurement"
    },
    'wind_e': {
        'name': 'energy production by wind',
        'unit_of_measurement': 'MW',
        'icon':"mdi:wind-turbine",
        'device_class': "power",
        'state_class': "measurement"
    },
    'hydro_e': {
        'name': 'energy production from hydro',
        'unit_of_measurement': 'MW',
        'icon': "mdi:water",
        'device_class': "power",
        'state_class': "measurement"
    },
    'solar_e': {
        'name': 'energy production from solar',
        'icon': 'mdi:solar-power',
        'unit_of_measurement': 'MW',
        'device_class': "power",
        'state_class': "measurement"
    },
    'tidal_e': {
        'name': 'energy production from tidal',
        'icon': "mdi:gauge",
        'unit_of_measurement': "MW",
        'device_class': "power",
        'state_class': "measurement"
    },
    'biogas_e':{
        'name': 'energy production from biogas', 
        'icon': "mdi:gauge",
        'unit_of_measurement': "MW",
        'device_class': "power",
        'state_class': "measurement"
    },
    'fossilFree_e':{
        'name': 'energy production from fossil free sources', 
        'icon': "mdi:leaf-circle",
        'unit_of_measurement': "MW",
        'device_class': "power",
        'state_class': "measurement"
    }
}



AREAS = {
    'suduroy': { 'name': 'Suðuroy', 'source': 'sev', 'station_id': 'suduroy' },
    'main': { 'name': 'Main area', 'source': 'sev', 'station_id': 'main' },
    'total': { 'name': 'All production ', 'source': 'sev', 'station_id': 'total' },
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_AREAS): vol.All(cv.ensure_list, vol.Length(min=1), [vol.In(AREAS)])
})

async def async_setup_platform(hass: HomeAssistantType, config: ConfigType,
                               async_add_entities, discovery_info=None):
    
    if hass.config.units is METRIC_SYSTEM:
        unit_system_api = 'm'
        unit_system = 'metric'
    else:
        unit_system_api = 'e'
        unit_system = 'imperial'

    areas = config.get(CONF_AREAS)
    _LOGGER.info("areas in config: %s", areas )
    sensors = []
    for area_id in areas:
        area = AREAS[area_id]
        _LOGGER.info("Start monitor area: %s", area['name'] )
        rest = SEVData(hass)
        await rest.async_update()
        
           
            
        sensors.append(EnergySensor(hass, rest, 'oil_e', area_id, area['name'], 'oil', 'e'))
        sensors.append(EnergySensor(hass, rest, 'oil_p', area_id, area['name'], 'oil', 'p'))
        
        sensors.append(EnergySensor(hass, rest, 'wind_e', area_id, area['name'], 'wind', 'e'))
        sensors.append(EnergySensor(hass, rest, 'wind_p', area_id, area['name'], 'wind', 'p'))

        sensors.append(EnergySensor(hass, rest, 'solar_e', area_id, area['name'], 'solar', 'e'))
        sensors.append(EnergySensor(hass, rest, 'solar_p', area_id, area['name'], 'solar', 'p'))
        
        sensors.append(EnergySensor(hass, rest, 'hydro_e', area_id, area['name'], 'hydro', 'e'))
        sensors.append(EnergySensor(hass, rest, 'hydro_p', area_id, area['name'], 'hydro', 'p'))

        sensors.append(EnergySensor(hass, rest, 'biogas_e', area_id, area['name'], 'biogas', 'e'))
        sensors.append(EnergySensor(hass, rest, 'biogas_p', area_id, area['name'], 'biogas', 'p'))

        sensors.append(EnergySensor(hass, rest, 'tidal_e', area_id, area['name'], 'tidal', 'e'))
        sensors.append(EnergySensor(hass, rest, 'tidal_p', area_id, area['name'], 'tidal', 'p'))

        sensors.append(EnergySensor(hass, rest, 'fossilFree_e', area_id, area['name'], 'fossilFree', 'e'))
        sensors.append(EnergySensor(hass, rest, 'fossilFree_p', area_id, area['name'], 'fossilFree', 'p'))

    async_add_entities(sensors, True)



class EnergySensor(SensorEntity):
    """Implementing the sev sensor."""

    def __init__(self, hass: HomeAssistantType, rest, sensor_type, area_id, area_name, data_field, data_type):
        """Initialize the sensor."""
        self.data_field = data_field
        self.data_type = data_type
        self.area_id = area_id
        self.area_name = area_name
        self.rest = rest
        self._sensor_type = sensor_type
        self._state_class = "measurement"
        self._attributes = {
            ATTR_ATTRIBUTION: CONF_ATTRIBUTION,
        }
        self._icon = None
        self._entity_picture = None
        self._unit_of_measurement = self._cfg_expand("unit_of_measurement")
        # This is only the suggested entity id, it might get changed by
        # the entity registry later.
        unique_id = 'c_fo_energy_production_' + area_id + '_' + data_type + '_' + sensor_type
        self.entity_id = sensor.ENTITY_ID_FORMAT.format('fo_energy_production_' + area_id + '_' + data_type)
        self._unique_id = unique_id
        self._device_class = self._cfg_expand("device_class")

    def _cfg_expand(self, what, default=None):
        """Parse and return sensor data."""
        sensor_info = SENSOR_TYPES[self._sensor_type]
        cfg = EnergyCurrentConditionsSensorConfig(
            self.area_name + ", " + sensor_info['name'],
            area_id = self.area_id,
            field= self.data_field,
            field_type= self.data_type,
            icon = sensor_info['icon'],
            unit_of_measurement=sensor_info['unit_of_measurement'],
            device_class= sensor_info['device_class']
        )
        #SENSOR_TYPES[self._condition]
        val = getattr(cfg, what)
        if not callable(val):
            return val
        try:
            val = val(self.rest)
        except (KeyError, IndexError, TypeError, ValueError) as err:
            _LOGGER.warning("Failed to expand cfg from WU API."
                            " Condition: %s Attr: %s Error: %s",
                            self._sensor_type, what, repr(err))
            val = default

        return val

    def _update_attrs(self):
        """Parse and update device state attributes."""
        attrs = self._cfg_expand("device_state_attributes", {})

        for (attr, callback) in attrs.items():
            if callable(callback):
                try:
                    self._attributes[attr] = callback(self.rest)
                except (KeyError, IndexError, TypeError, ValueError) as err:
                    _LOGGER.warning("Failed to update attrs from WU API."
                                    " Condition: %s Attr: %s Error: %s",
                                    self._sensor_type, attr, repr(err))
            else:
                self._attributes[attr] = callback

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._cfg_expand("friendly_name")

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def icon(self):
        """Return icon."""
        return self._icon

    @property
    def entity_picture(self):
        """Return the entity picture."""
        return self._entity_picture

    @property
    def unit_of_measurement(self):
        """Return the units of measurement."""
        return self._unit_of_measurement

    @property
    def device_class(self):
        """Return the units of measurement."""
        return self._device_class

    @property
    def state_class(self):
        return self._state_class
    
    async def async_update(self):
        """Update current conditions."""
        await self.rest.async_update()

        if not self.rest.data:
            # no data, return
            return

        self._state = self._cfg_expand("value")
        self._update_attrs()
        self._icon = self._cfg_expand("icon", super().icon)
        url = self._cfg_expand("entity_picture")
        if isinstance(url, str):
            self._entity_picture = re.sub(r'^http://', 'https://',
                                          url, flags=re.IGNORECASE)

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

class SEVData:
    """Get data from sev.fo"""
    def __init__(self, hass):
        """Initialize the data object."""
        self._hass = hass
        self._features = set()
        self.data = None
        self._session = async_get_clientsession(self._hass)
    

    def tofloat(self, sval):
        return float(sval.replace(",", "."))


    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        headers = {'Accept-Encoding': 'gzip'}
        current_date = datetime.today()
        sev_data = None
        try:
            with async_timeout.timeout(10):
                sev_data = await self._session.get(SEV_URL)
                if sev_data is None:
                    raise ValueError('NO CURRENT RESULT')
                                   
                
        except ValueError as err:
            _LOGGER.error("Check sev energy API %s", err.args)
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Error fetching energy data: %s", repr(err))
        
        if sev_data:       
            byte_data = bytearray()
            while not sev_data.content.at_eof():
                chunk = await sev_data.content.read(1024)
                byte_data += chunk   
            
            json_str =byte_data.decode('utf8')
            sev_data = json.loads(json_str)
            data = {
                "time": sev_data["tiden"],
                "areas": { 
                    "suduroy": {
                        "wind": { "p": self.tofloat(sev_data["VindS_P"]), "e": self.tofloat(sev_data["VindS_E"])},
                        "oil": { "p": self.tofloat(sev_data["OlieS_P"]), "e": self.tofloat(sev_data["OlieS_E"])},
                        "hydro": { "p": self.tofloat(sev_data["VandS_P"]), "e": self.tofloat(sev_data["VandS_E"])},
                        "solar": { "p": self.tofloat(sev_data["SolS_P"]), "e": self.tofloat(sev_data["SolS_E"])},
                        "biogas": { "p": 0, "e": 0},
                        "tidal": { "p": 0, "e": 0},
                        "fossilFree": { "p": self.tofloat(sev_data["VindS_P"]) + self.tofloat(sev_data["VandS_P"]) + self.tofloat(sev_data["SolS_P"]), "e": self.tofloat(sev_data["VindS_E"]) + self.tofloat(sev_data["VandS_E"]) + self.tofloat(sev_data["SolS_E"])}
                    },
                    "main": {
                        "wind": { "p": self.tofloat(sev_data["VindH_P"]), "e": self.tofloat(sev_data["VindH_E"])},
                        "oil": { "p": self.tofloat(sev_data["OlieH_P"]), "e": self.tofloat(sev_data["OlieH_E"])},
                        "hydro": { "p": self.tofloat(sev_data["VandH_P"]), "e": self.tofloat(sev_data["VandH_E"])},
                        "solar": { "p": 0, "e": 0},
                        "biogas": { "p": self.tofloat(sev_data["BiogasH_P"]), "e": self.tofloat(sev_data["BiogasH_E"])},
                        "tidal": { "p": self.tofloat(sev_data["TidalH_P"]), "e": self.tofloat(sev_data["TidalH_E"])},
                        "fossilFree": { "p": self.tofloat(sev_data["TidalH_P"]) + self.tofloat(sev_data["BiogasH_P"]) + self.tofloat(sev_data["VindH_P"]) + self.tofloat(sev_data["VandH_P"]) , "e": self.tofloat(sev_data["TidalH_E"]) + self.tofloat(sev_data["BiogasH_E"]) +  self.tofloat(sev_data["VindH_E"]) + self.tofloat(sev_data["VandH_E"]) }
                    },
                    "total": {
                        "wind": { "p": self.tofloat(sev_data["VindSev_P"]), "e": self.tofloat(sev_data["VindSev_E"])},
                        "oil": { "p": self.tofloat(sev_data["OlieSev_P"]), "e": self.tofloat(sev_data["OlieSev_E"])},
                        "hydro": { "p": self.tofloat(sev_data["VandSev_P"]), "e": self.tofloat(sev_data["VandSev_E"])},
                        "solar": { "p": self.tofloat(sev_data["SolSev_P"]), "e": self.tofloat(sev_data["SolSev_E"])},
                        "biogas": { "p": self.tofloat(sev_data["BiogasSev_P"]), "e": self.tofloat(sev_data["BiogasSev_E"])},
                        "tidal": { "p": self.tofloat(sev_data["TidalSev_P"]), "e": self.tofloat(sev_data["TidalSev_E"])},
                        "fossilFree": { "p": self.tofloat(sev_data["TidalSev_P"]) + self.tofloat(sev_data["BiogasSev_P"]) + self.tofloat(sev_data["VindSev_P"]) + self.tofloat(sev_data["VandSev_P"]) + self.tofloat(sev_data["SolSev_P"]), "e": self.tofloat(sev_data["TidalSev_E"]) + self.tofloat(sev_data["BiogasSev_E"]) +  self.tofloat(sev_data["VindSev_E"]) + self.tofloat(sev_data["VandSev_E"]) + self.tofloat(sev_data["SolSev_E"])}
                    }
                }
            }
            self.data = data
        