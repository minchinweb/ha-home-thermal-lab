"""Serve the drawing of the house outline for the setup form.

The form's description shows it as an image. The drawing holds only the
building outline fetched from OpenStreetMap and the compass directions, so the
address is not in it.
"""

from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from . import DOMAIN
from .orientation import outline_svg


class OutlineMapView(HomeAssistantView):
    """``/api/home_thermal_lab/outline.svg?rotation=10.4``."""

    url = "/api/home_thermal_lab/outline.svg"
    name = "api:home_thermal_lab:outline"
    requires_auth = False  # an image in the form cannot send the login token

    def __init__(self, hass) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Draw the outline found for the home with the requested rotation."""
        info = self._hass.data.get(DOMAIN, {}).get("outline")
        if not info or not info.get("points"):
            return web.Response(status=404)
        try:
            rotation = float(request.query["rotation"])
        except (KeyError, ValueError):
            rotation = info["rotation"]
        return web.Response(
            text=outline_svg(info["points"], rotation),
            content_type="image/svg+xml",
            headers={"Cache-Control": "no-store"},
        )
