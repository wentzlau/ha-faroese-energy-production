# ha-faroese-energy-production
Integration for Home Assistant that fetches energy production information from the faroese power provider SEV.
Creates a set of sensors that may be used in dashboards or used in automations.

![Home assistant dashboard](https://github.com/wentzlau/ha-faroese-energy-production/blob/d1f3f4e466f208bb9738a671f310cae541bc6c39/images/ha-dashboard.png)

## Installation
### Via the Home Assistant Marketplace (recommended)
Requires Home Assistant 2026.11 or newer.

1. Go to **Settings → Marketplace**.
2. Search for **Faroese energy production** and install it.
   If it is not listed yet, add `https://github.com/wentzlau/ha-faroese-energy-production`
   as a custom repository (type **Integration**) and install it from there.
3. Restart Home Assistant.

### Via HACS (Home Assistant before 2026.11)
Add `https://github.com/wentzlau/ha-faroese-energy-production` as a custom repository
(type **Integration**) in HACS, install it and restart Home Assistant.

### Manual installation
1. Download `ha-faroese-energy-production.zip` from the
   [latest release](https://github.com/wentzlau/ha-faroese-energy-production/releases/latest).
2. Extract it into `<config>/custom_components/fo_energy_production/`.
   The folder name must be exactly `fo_energy_production`.
3. Restart Home Assistant.

## Configuration
Go to **Settings → Devices & services → Add integration**, search for
**Faroese energy production** and select one or more areas.
A set of sensors is created for each selected area.

To change the areas later, click **Configure** on the integration entry.

### Legacy YAML configuration (deprecated)
An existing `configuration.yaml` setup like the one below is imported into the UI
automatically on startup. After that, remove it from `configuration.yaml`.
```
sensor:    
  - platform: fo_energy_production    
    areas:    
      - suduroy    
      - main
      - total
```
