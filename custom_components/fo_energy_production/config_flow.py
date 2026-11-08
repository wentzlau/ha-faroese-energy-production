"""Config flow for the Faroese energy production integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import AREAS, CONF_AREAS, DEFAULT_AREAS, DOMAIN


def _areas_schema(default: list[str]) -> vol.Schema:
    """Build the form schema with a multi-select of areas."""
    return vol.Schema(
        {
            vol.Required(CONF_AREAS, default=default): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=key, label=area["name"].strip())
                        for key, area in AREAS.items()
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                    translation_key=CONF_AREAS,
                )
            )
        }
    )


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    areas = user_input.get(CONF_AREAS) or []
    if not areas:
        errors[CONF_AREAS] = "no_areas"
    elif any(area not in AREAS for area in areas):
        errors[CONF_AREAS] = "invalid_area"
    return errors


class FoEnergyProductionConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Faroese energy production."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step started from the UI."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title="Faroese energy production",
                    data={CONF_AREAS: user_input[CONF_AREAS]},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_areas_schema(
                (user_input or {}).get(CONF_AREAS, DEFAULT_AREAS)
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import an existing configuration.yaml setup."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        areas = [a for a in import_data.get(CONF_AREAS, []) if a in AREAS]
        return self.async_create_entry(
            title="Faroese energy production",
            data={CONF_AREAS: areas or DEFAULT_AREAS},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return FoEnergyProductionOptionsFlow()


class FoEnergyProductionOptionsFlow(OptionsFlow):
    """Let the user change which areas are monitored."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(
                    data={CONF_AREAS: user_input[CONF_AREAS]}
                )

        current = self.config_entry.options.get(
            CONF_AREAS, self.config_entry.data.get(CONF_AREAS, DEFAULT_AREAS)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=_areas_schema(current),
            errors=errors,
        )
