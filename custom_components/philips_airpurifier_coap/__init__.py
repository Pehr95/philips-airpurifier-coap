"""Support for Philips AirPurifier with CoAP."""
from __future__ import annotations
import asyncio

import logging

from aioairctrl import CoAPClient

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.config_entries import ConfigEntry

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http.view import HomeAssistantView

import json
from os import walk, path

from .philips import Coordinator

from .const import (
    DATA_KEY_CLIENT,
    DATA_KEY_COORDINATOR,
    DOMAIN,
    ICONLIST_URL,
    ICONS,
    ICONS_PATH,
    ICONS_URL,
    LOADER_PATH,
    LOADER_URL,
    PAP,
)

_LOGGER = logging.getLogger(__name__)


PLATFORMS = ["fan", "sensor", "switch", "light", "select"]


# icons code thanks to Thomas Loven:
# https://github.com/thomasloven/hass-fontawesome/blob/master/custom_components/fontawesome/__init__.py


class ListingView(HomeAssistantView):

    requires_auth = False

    def __init__(self, hass, url):
        self._hass = hass
        self.url = url
        self.name = "Icon Listing"

    async def get(self, request):
        return json.dumps(self._hass.data[DOMAIN][ICONS])


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Set up the icons for the Philips AirPurifier integration."""
    _LOGGER.debug("async_setup called")

    hass.http.register_static_path(LOADER_URL, hass.config.path(LOADER_PATH), True)
    add_extra_js_url(hass, LOADER_URL)

    iset = PAP
    iconpath = hass.config.path(ICONS_PATH + "/" + iset)

    # walk the directory to get the icons
    icons = []
    for (dirpath, dirnames, filenames) in walk(iconpath):
        icons.extend(
            [
                {"name": path.join(dirpath[len(iconpath) :], fn[:-4])}
                for fn in filenames
                if fn.endswith(".svg")
            ]
        )

    # store icons
    data = hass.data.get(DOMAIN)
    if data is None:
        hass.data[DOMAIN] = {}

    hass.data[DOMAIN][ICONS] = icons

    # register path and view
    hass.http.register_static_path(ICONS_URL + "/" + iset, iconpath, True)
    hass.http.register_view(ListingView(hass, ICONLIST_URL + "/" + iset))

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Philips AirPurifier integration."""
    host = entry.data[CONF_HOST]

    _LOGGER.debug("async_setup_entry called for host %s", host)

    try:
        future_client = CoAPClient.create(host)
        client = await asyncio.wait_for(future_client, timeout=180)
        _LOGGER.debug("got a valid client for host %s", host)
    except Exception as ex:
        _LOGGER.warning(r"Failed to connect to host %s: %s", host, ex)
        raise ConfigEntryNotReady from ex

    coordinator = Coordinator(client, host)
    _LOGGER.debug("got a valid coordinator for host %s", host)

    data = hass.data.get(DOMAIN)
    if data is None:
        hass.data[DOMAIN] = {}

    hass.data[DOMAIN][host] = {
        DATA_KEY_CLIENT: client,
        DATA_KEY_COORDINATOR: coordinator,
    }

    await coordinator.async_first_refresh()
    _LOGGER.debug("coordinator did first refresh for host %s", host)

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    for p in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, p)

    coord: Coordinator = hass.data[DOMAIN][entry.data[CONF_HOST]][DATA_KEY_COORDINATOR]
    await coord.shutdown()

    hass.data[DOMAIN].pop(entry.data[CONF_HOST])

    return True
