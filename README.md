# Birdfy for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adkulik&repository=ha-birdfy&category=integration)
[![GitHub release](https://img.shields.io/github/v/release/adkulik/ha-birdfy)](https://github.com/adkulik/ha-birdfy/releases)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/adkulik)

A Home Assistant integration for **Birdfy** bird feeder cameras (made by Netvue).
It brings **bird visits** into Home Assistant: which species visited, when, a
photo, a daily count, and a **live view** of the camera.

> **Status: early test version (0.7), tested on a Birdfy Cam 2 Pro.** The Birdfy cloud API is not public; this
> integration uses what the community has reverse-engineered. It has not yet been
> confirmed on every Birdfy model.

## What you get

For each camera on the account:

| Entity | What it shows |
|---|---|
| `event.<camera>_bird_visit` | Fires on every new bird visit. Attributes: `species` (main species), `species_en` (English name), `species_list`, `bird_count`, `confidence`, `candidates` (other possible species), `visit_time`, `event_id`. Use it as an automation trigger. |
| `sensor.<camera>_last_visitor` | Species of the last visit (same attributes as the event) |
| `sensor.<camera>_last_visit` | Time of the last visit |
| `sensor.<camera>_visits_today` | Bird visits today, with a per-species breakdown in the `species` attribute (resets at midnight) |
| `sensor.<camera>_motion_events_today` | All motion events today, birds or not (disabled by default) |
| `image.<camera>_last_visit_photo` | Photo of the last bird visit |
| `camera.<camera>_live_view` | Live view (main lens). Its still image is the last visit photo |
| `camera.<camera>_live_view_second_lens` | Live view of the second lens (dual-lens models) |

A **visit** is a motion event in which Birdfy's AI recognised at least one bird.
Motion events without a bird (wind, a squirrel, a cat) do not count as visits.

## How it works

- The integration polls the Birdfy cloud (every 60 s by default, adjustable in
  the integration options). A visit shows up in Home Assistant with that much delay.
- Species names come from Birdfy's own AI recognition, which may need an active
  Birdfy subscription. Birdfy sends them in English; the integration shows
  them in your language (see [Species names](#species-names)).
- The photo of the latest visit is downloaded once and kept in memory only;
  its temporary download link is not stored or logged.
- Visits that happened before the integration started do not fire events.

## Species names

Birdfy names the species in English. The integration translates them with the
[IOC World Bird List](https://www.worldbirdnames.org/) multilingual names, which
cover every bird species of the world in 40+ languages, including German,
French, Spanish, Italian, Dutch, Polish, Czech, Swedish, Japanese and Chinese.

- By default the names follow the Home Assistant language. To pick another one,
  open the integration → **Configure** → **Language of species names**. Choose
  **English** to keep Birdfy's own names.
- The English name is always kept in the `species_en` attribute, so automations
  can rely on it whatever the language.
- If a name can't be matched (Birdfy sometimes uses short or regional names), it
  stays in English. Spotted one? Please
  [open an issue](https://github.com/adkulik/ha-birdfy/issues) with the English name.

## Live view

The camera entities use Home Assistant's built-in WebRTC support, so any camera
card (or the more-info dialog) shows the live picture, also in the Home
Assistant app. The video goes from the Birdfy relay server straight to your
browser; Home Assistant only passes the connection setup through, so it does no
video processing. The camera wakes up only while you are watching, and a live
session is closed after 10 minutes to save the battery.

## Security and privacy

- Use a **separate Birdfy account** that the camera is shared with, not your main
  account. Logging in from Home Assistant may log the mobile app out of the same account.
- The password itself is **not stored**: the Birdfy login only needs an MD5 hash
  of it, so only that hash is saved in the config entry. (MD5 is what the Birdfy
  service requires; treat the hash as sensitive anyway.)
- Session tokens are kept in memory only and are never logged.
- Diagnostics downloads redact email, serial numbers, IDs and URLs.

## Installation (HACS)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adkulik&repository=ha-birdfy&category=integration)

Birdfy is in the HACS default catalog, so you don't need to add anything by hand:

1. Open HACS and search for **Birdfy** (or click the button above). Two
   integrations share the name — pick the one by **adkulik** (`adkulik/ha-birdfy`).
2. Download it, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **Birdfy**, and sign in, or click:

[![Open your Home Assistant instance and start setting up Birdfy.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=birdfy_connect)

**If Birdfy doesn't show up in the search** (e.g. HACS hasn't refreshed its
catalog yet), add it as a custom repository instead: HACS → ⋮ → **Custom
repositories** → add `https://github.com/adkulik/ha-birdfy`, type
**Integration**, then continue from step 2.

**Upgrading from 0.5.x or earlier:** from 0.6.0 the integration's domain is
`birdfy_connect` (it was `birdfy`, which clashed with another integration in HACS).
Home Assistant treats it as a new integration, so: delete the Birdfy entry under
Settings → Devices & services, update in HACS and restart, delete the old
`custom_components/birdfy` folder if it is still there, then add **Birdfy** again
and sign in. Entity IDs come from the camera and entity names, so they normally
stay the same.

## Example automation

```yaml
triggers:
  - trigger: state
    entity_id: event.feeder_bird_visit
actions:
  - action: notify.mobile_app_iphone
    data:
      message: "{{ state_attr('event.feeder_bird_visit', 'species') or 'A bird' }} is at the feeder"
      data:
        image: /api/image_proxy/image.feeder_last_visit_photo
```

## Troubleshooting

If something does not work on your model, enable debug logging for
`custom_components.birdfy_connect`, and download the diagnostics from the integration page.
Open an issue with both (they contain no passwords or tokens).

## Support

This integration is free and will stay free. If you find it useful, you can support further development:

<a href="https://buymeacoffee.com/adkulik"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="50"></a>

Recurring support is available through [GitHub Sponsors](https://github.com/sponsors/adkulik).

## Credits

The cloud protocol details come from community reverse-engineering work, in
particular [aubreybailey/birdfy](https://github.com/aubreybailey/birdfy) and
[sebsst/birdfy-rtsp](https://github.com/sebsst/birdfy-rtsp). This integration is
an independent implementation.

Species names: Gill F, D Donsker & P Rasmussen (Eds), IOC World Bird List,
multilingual version compiled by Peter Kovalik —
[worldbirdnames.org](https://www.worldbirdnames.org/), licensed under a
Creative Commons Attribution (CC BY) licence.

Not affiliated with Birdfy or Netvue.

