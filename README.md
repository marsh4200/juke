# Juke Audio — Home Assistant Integration

A custom Home Assistant integration for [Juke Audio](https://jukeaudio.com) whole-home
audio systems, built against the local Juke REST API v3
(`https://sim.jukeaudio.com/api/v3/apidocs/`).

## What it does

- **Zones → `media_player` entities.** Each Juke zone (physical audio output) becomes a
  media player with volume, mute, on/off (zone enable/disable), and source selection
  (switches the zone's active input).
- **Devices → diagnostic `sensor` entities.** Each physical Juke device gets CPU usage,
  RAM usage, disk usage, and internal temperature sensors, grouped under its own device
  in the HA device registry (with serial number / firmware version as device attributes).
- Polls the device every 30 seconds via a `DataUpdateCoordinator` (local push isn't
  available — the API only offers polling GETs and outbound webhook subscriptions, which
  aren't wired up here).

## Installation

### Via HACS (custom repository)

1. In HACS → Integrations → the "..." menu → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Install "Juke Audio", then restart Home Assistant.

### Manual

1. Copy the `custom_components/juke` folder from this repo into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

Settings → Devices & Services → **Add Integration** → search for "Juke".

You'll be asked for:

- **Host/IP** — your Juke device's address on your local network.
- **Port** — default `80`.
- **Username / Password** — HTTP Basic Auth credentials. Juke devices ship with the
  default `Admin` / `Admin`; change these in the Juke app if you haven't already,
  since this exposes control of your audio system to anyone on your LAN.
- **Use HTTPS / Verify SSL certificate** — leave off unless you know your device is
  configured for TLS.

The config flow validates connectivity (`GET /ping`) and credentials
(`GET /zones/info`) before creating the entry.

## Notes & limitations

- The Juke API has no playback/transport state (no play/pause/track metadata) — a zone
  is fundamentally an audio *output* with volume/mute/source, not a music player, so
  the `media_player` entity only supports the subset of features that make sense
  (volume, mute, source select, on/off).
- Source names shown in Home Assistant come from `GET /inputs/info`; renaming an input
  in the Juke app will rename the corresponding HA source automatically on the next
  poll.
- This was built directly from the published API docs, not against every firmware
  revision in the field — if your device's `/api/v3` responses differ (extra/missing
  fields, different enum values), open an issue with the mismatch and it's typically a
  small fix in `api.py` / `coordinator.py`.
- Before publishing this as a real HACS repo, update `manifest.json`
  (`codeowners`, `documentation`, `issue_tracker`) with your actual GitHub handle/repo.

## File layout

```
custom_components/juke/
├── __init__.py        # entry setup/unload, forwards to platforms
├── api.py              # async REST client (zones/devices/inputs, basic auth)
├── config_flow.py       # UI config flow (host/port/credentials)
├── const.py             # domain, defaults, update interval
├── coordinator.py       # DataUpdateCoordinator polling zones+devices+inputs
├── media_player.py      # zone -> media_player entities
├── sensor.py             # device -> diagnostic sensor entities
├── manifest.json
├── strings.json
└── translations/en.json
```
