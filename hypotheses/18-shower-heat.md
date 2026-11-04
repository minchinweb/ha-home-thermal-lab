# 18 Shower heat from bathroom humidity

**Status:** first run; showers detected, heat into the house not measurable yet; one logged shower (4 November) shows the sensor reports too rarely to time the fan or the door

**Claim:** Showers can be logged from the bathroom's humidity (water use is not metered), and the heat and moisture they release into the house can be estimated, as an input term for the other hypotheses (it is part of the "unexplained" heat in a room's balance).

**Data:** Bathroom temperature and humidity sensors: `sensor.upstairs_bathroom_temp_humidity_sensor_*` and `sensor.main_floor_bathroom_temp_humidity_*` (the latter unavailable since 29 October 2026, probably its battery). Neighbouring rooms' temperatures.

**Method:** An event starts when relative humidity rises by 8+ points within 15 minutes. Per event: peak humidity, the rise in absolute humidity (g/m3), the bathroom temperature rise in the next hour, the time for humidity to fall halfway back, and the neighbours' temperature rise.

**Feeds:** 15 (occupancy: a shower is a person), 16 and the contribution chart (as a known heat event), 10 (moisture moving between rooms).

## Results

First run (`scripts/shower_heat.py --days 14`, to 2026-11-02, 5-minute statistics):

- Upstairs bath: 15 showers in 14 days (mornings 06:30-08:45, afternoons and evenings). Humidity 49-53% rises to 61-80%; absolute humidity +2.3 to +5.6 g/m3; the bathroom warms +0.5 to +1.7 C (median +0.9 C) and peaks 25-45 minutes after the start; humidity halves again in 10-30 minutes (one 175).
- Main floor bath: 11 showers in 7 days before the sensor dropped out; larger rises (+2.3 to +11 g/m3, median +6.3; +0.5 to +2.7 C).
- Neighbours: the N bedroom and the master bedroom rise 0 to +0.7 C in the hour after an upstairs shower, the kitchen 0 to +1.4 C after a main-floor one, but these are the largest rise in the hour against no control, and include furnace calls and the sun.
- Size: for a median shower, the moisture added to the bathroom air is worth only about 15 Wh of latent heat upstairs (7.9 m3 of air) and 41 Wh on the main floor (9.6 m3). The air's warming is worth about 2-4 Wh. (These were 25-50 Wh and 5 Wh when both rooms were taken as 12 m3; corrected 4 November.) The hot water carries about 8 kWh per shower, most of it down the drain; how much warms the house is not measurable from these sensors.

### A logged shower, 4 November 2026

This is the first shower with the sequence written down. The occupant gave this order for the upstairs bath: door closed, shower on, fan on (the fan is switched by its own humidity sensor and is not in Home Assistant), shower off at about 13:20, door opened. The fan stopped at about 13:37. The raw sensor states (not the 5-minute statistics) are:

| Time | Temp °C | RH % | Reading |
|---|---|---|---|
| 12:47:21 | 20.91 | 53.1 | before the shower |
| 13:00:49 | 21.12 | 55.6 | the whole upstairs was warming too (Z3 20.5 to 21.1 °C), so this is not the start |
| 13:16:49 | 21.60 | 54.7 | shower already running: temperature up about 0.5 °C, humidity not yet |
| 13:17:30 | 21.64 | 55.0 | |
| 13:19:21 | 21.74 | 66.2 | +11 points in 2 minutes |
| 13:26:46 | 22.01 | 59.7 | drying (door open, fan on); no further report up to 13:38 |

- **The sensor reports too rarely to time the sequence.** It reports when a value changes enough, with gaps of 7 to 16 minutes. It has no regular heartbeat, and it sent nothing during the slow decay. The start can only be placed between 13:01 and 13:16. The end fits 13:19-13:20. The true humidity peak fell in the 7-minute gap, so it was above 66%. The fan switching on and the decay slowing when it switched off cannot be seen.
- **Temperature leads humidity.** At 13:16:49 the shower was running, and the room was already 0.5 °C warmer, but the humidity had not moved. It jumped 2.5 minutes later. Warm air seems to reach the sensor before the moisture does, and the fan was probably holding the humidity down.
- **Door versus fan.** No reading came close enough to the door opening on 4 November. An event earlier that morning looked like a door opening: humidity rose from 50.7% to 62.9% in one minute at 09:38, reached 69.0% at 09:49:23, then fell to 62.9% by 09:50:54, about 6 points in 90 seconds. That is too fast for the fan alone. **That event was the bathroom being cleaned, not a shower.** So cleaning (hot water, spraying) also passes the 8-point detection rule, and the shower log will include some false positives.
- **The fan is not visible in the house power.** `sensor.eagle_00bb9c_power_demand` reads every 30 seconds. With no zone calling (12:50-12:56 and 13:36-13:38), it still varies by 30-100 W between readings. Zone calls change the furnace blower draw by 250-400 W, and they switched 30+ times in the hour. A step of -40 W came at 13:36:38, close to when the fan stopped, but steps that size are common. A bathroom fan (about 20-80 W) is below this noise.
- `shower_heat.py` took both bathrooms as 12 m3 of air. Their areas in Home Assistant give 7.9 m3 (upstairs) and 9.6 m3 (main floor), so the script now uses those volumes and the size figures above are updated.
- The main-floor sensor's last reading was at 18:21 on 31 October (local time), so the shower on the main floor at about 07:00 on 4 November was not recorded. The upstairs sensor's CR2032 battery is at 36%.

To time the fan and the door:

- Set the upstairs sensor to report more often: a 1% humidity or 0.1 °C change, a 10 s minimum and a 5 min maximum interval. This costs battery.
- Put a contact sensor on the bathroom door.
- Fit a switch or relay that reports power on the fan, or switch the fan by hand (2 minutes on, 2 minutes off, several times) while no zone calls, note the times, and average the steps in the house power.

**Next:** a control comparison (the same hours on days without a shower) for the neighbours; replace the main-floor sensor's battery; use the shower log as an event input in 15 and the contribution chart.
