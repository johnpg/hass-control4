"""Platform for Control4 Sensors."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfEnergy, UnitOfPower

from .const import CONF_DIRECTOR_ALL_ITEMS, CONTROL4_ENTITY_TYPE, DOMAIN, CONF_CONTROLLER_UNIQUE_ID
from .director_utils import director_get_entry_variables

_LOGGER = logging.getLogger(__name__)

# This is a mapping of Control4 sensor attributes to Home Assistant sensor properties.
# Based on the proxies array and the key name it will match attributes on a Control4
# device and create the appropriate sensor entity for Home Assistant.
# I've only tested this with the power monitoring attributes on a Light but
# in theory it should work with others.
CONTROL4_SENSOR_ATTRIBUTES = {
    "CURRENT_POWER": {
        "name": "Power",
        "device_class": SensorDeviceClass.POWER,
        "unit": UnitOfPower.WATT,
        "state_class": SensorStateClass.MEASUREMENT,
        "proxies": {"light_v2"},
    },
    "ENERGY_USED": {
        "name": "Energy",
        "device_class": SensorDeviceClass.ENERGY,
        "unit": UnitOfEnergy.WATT_HOUR,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "proxies": {"light_v2"},
    },
}




async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Control4 sensors from a config entry."""

    entry_data = hass.data[DOMAIN][entry.entry_id]
    director_all_items = entry_data[CONF_DIRECTOR_ALL_ITEMS]
    
    entity_list = []

    # Iterate through all items and not just lights, so we can theoretically support any attribute as a sensor
    for item in director_all_items:
        try:
            if item["type"] == CONTROL4_ENTITY_TYPE and item["id"]:
                item_id = item["id"]
                item_parent_id = item["parentId"]
                item_area = item["roomName"]
                item_manufacturer = item.get("manufacturer")
                item_device_name = item.get("name")
                item_model = item.get("model")
                item_proxy = item.get("proxy")
            else:
                continue
        except KeyError:
            _LOGGER.exception(
                "Unknown device properties received from Control4: %s",
                item,
            )
            continue

        item_attributes = await director_get_entry_variables(hass, entry, item_id)

        # Now let's create sensors for each configured attribute that exists on the device
        for attr_name, attr_config in CONTROL4_SENSOR_ATTRIBUTES.items():
            if attr_name in item_attributes:
                # Only do this if the proxy type matches the config 
                supported_proxies = attr_config.get("proxies")
                if supported_proxies and item_proxy not in supported_proxies:
                    continue

                entity_list.append(
                    Control4SensorEntity(
                        hass,
                        entry,
                        entry_data,
                        item_id,
                        item_device_name,
                        item_manufacturer,
                        item_model,
                        item_parent_id,
                        item_area,
                        item_attributes,
                        attr_name,
                        attr_config,
                        f"{entry.entry_id}_{item_id}_{attr_name.lower()}",
                    )
                )

    async_add_entities(entity_list, True)


class Control4SensorEntity(SensorEntity):
    """Generic Control4 sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        entry_data: dict,
        item_id: int,
        item_device_name: str | None,
        item_manufacturer: str | None,
        item_model: str | None,
        item_parent_id: int,
        item_area: str,
        device_attributes: dict,
        attr_name: str,
        attr_config: dict,
        unique_id: str,
    ) -> None:
        """Initialize Control4 sensor entity."""
        self.hass = hass
        self.entry = entry
        self.entry_data = entry_data
        self._item_id = item_id
        self._parent_id = item_parent_id
        self._area = item_area
        self._device_name = item_device_name
        self._manufacturer = item_manufacturer
        self._model = item_model
        self._attr_name_str = attr_name
        self._attr_unique_id = unique_id
        self._attr_has_entity_name = True
        self._attr_name = attr_config["name"]
        self._attr_device_class = attr_config["device_class"]
        self._attr_native_unit_of_measurement = attr_config["unit"]
        self._attr_state_class = attr_config["state_class"]
        self._attr_available = True
        self._attr_should_poll = True
        
        if attr_name in device_attributes:
            self._attr_native_value = device_attributes[attr_name]

    @property
    def suggested_object_id(self) -> str | None:
        return self._attr_name.lower().replace(" ", "_")

    # Using polling because I could never get the websocket updates to work without
    # causing the light power state to stop working. I'm sure there's a way to fix this
    # but for now I figured polling was better than nothing.
    async def async_update(self) -> None:
        """Update sensor value via polling."""
        try:
            attrs = await director_get_entry_variables(self.hass, self.entry, self._item_id)
            self._attr_available = True
            self._attr_native_value = attrs.get(self._attr_name_str)
        except Exception:
            self._attr_available = False

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._parent_id))},
            manufacturer=self._manufacturer,
            model=self._model,
            name=self._device_name,
            via_device=(DOMAIN, self.entry_data[CONF_CONTROLLER_UNIQUE_ID]),
            suggested_area=self._area,
        )
