"""House Thermal Lab: experiments on house thermal behaviour, run inside Home Assistant.

Configured in YAML through its ``sensor`` platform (see ``sensor.py`` and the
README). See ``hypotheses/`` at the repository root for the experiments.

The modules other than ``sensor.py`` use only the standard library, so the
scripts and tests can import them without Home Assistant installed; that is why
this file defines no ``async_setup`` (Home Assistant does not need one for a
platform-only integration).
"""

DOMAIN = "house_thermal_lab"
