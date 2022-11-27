# ha-faroese-energy-production
Integration for Home Assistant that fetches energy production information from the faroese power provider SEV.

![Home assistant dashboard](https://github.com/wentzlau/ha-faroese-energy-production/blob/d1f3f4e466f208bb9738a671f310cae541bc6c39/images/ha-dashboard.png)

## installation
1) Create a subfolder called ha-faroese-energy-production in the .homeassistant/custom_components. 
2) Copy the contents of the repository/custom_components folder into the newly created subfolder.
3) in configuration.yaml enter this:
under area enter one or more areas to integrate into home assistant.
A set of sensors are created for each area.
    ```
    sensor:    
      - platform: fo_energy_production    
        area:    
          - suduroy    
          - main
          - total

