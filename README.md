# Birdfy for Home Assistant

[🇬🇧 English](#english) | [🇭🇺 Magyar](#magyar)

---

## English

A Home Assistant integration for **Birdfy** bird feeder cameras (made by Netvue).
It brings **bird visits** into Home Assistant: which species visited, when, a
photo, and a daily count. There is no live video, only visits.

> **Status: early test version (0.4), tested on a Birdfy Cam 2 Pro.** The Birdfy cloud API is not public; this
> integration uses what the community has reverse-engineered. It has not yet been
> confirmed on every Birdfy model.

### What you get

For each camera on the account:

| Entity | What it shows |
|---|---|
| `event.<camera>_bird_visit` | Fires on every new bird visit. Attributes: `species` (main species), `species_en` (English name), `species_list`, `bird_count`, `confidence`, `candidates` (other possible species), `visit_time`, `event_id`. Use it as an automation trigger. |
| `sensor.<camera>_last_visitor` | Species of the last visit (same attributes as the event) |
| `sensor.<camera>_last_visit` | Time of the last visit |
| `sensor.<camera>_visits_today` | Bird visits today, with a per-species breakdown in the `species` attribute (resets at midnight) |
| `sensor.<camera>_motion_events_today` | All motion events today, birds or not (disabled by default) |
| `image.<camera>_last_visit_photo` | Photo of the last bird visit |

A **visit** is a motion event in which Birdfy's AI recognised at least one bird.
Motion events without a bird (wind, a squirrel, a cat) do not count as visits.

### How it works

- The integration polls the Birdfy cloud (every 60 s by default, adjustable in
  the integration options). A visit shows up in Home Assistant with that much delay.
- Species names come from Birdfy's own AI recognition, which may need an active
  Birdfy subscription. Birdfy sends them in English; the integration can show
  them in **Hungarian** (common garden and feeder birds). By default it follows
  the Home Assistant language; change it under the integration's **Configure**
  options. The English name is always kept in the `species_en` attribute.
- The photo of the latest visit is downloaded once and kept in memory only;
  its temporary download link is not stored or logged.
- Visits that happened before the integration started do not fire events.

### Security and privacy

- Use a **separate Birdfy account** that the camera is shared with, not your main
  account. Logging in from Home Assistant may log the mobile app out of the same account.
- The password itself is **not stored**: the Birdfy login only needs an MD5 hash
  of it, so only that hash is saved in the config entry. (MD5 is what the Birdfy
  service requires; treat the hash as sensitive anyway.)
- Session tokens are kept in memory only and are never logged.
- Diagnostics downloads redact email, serial numbers, IDs and URLs.

### Installation (HACS)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adkulik&repository=ha-birdfy&category=integration)

Click the button above, or add the repository by hand:

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/adkulik/ha-birdfy`, type **Integration**.
2. Install **Birdfy**, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **Birdfy**, and sign in, or click:

[![Open your Home Assistant instance and start setting up Birdfy.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=birdfy)

### Example automation

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

### Troubleshooting

If something does not work on your model, enable debug logging for
`custom_components.birdfy`, and download the diagnostics from the integration page.
Open an issue with both (they contain no passwords or tokens).

### Credits

The cloud protocol details come from community reverse-engineering work, in
particular [aubreybailey/birdfy](https://github.com/aubreybailey/birdfy) and
[sebsst/birdfy-rtsp](https://github.com/sebsst/birdfy-rtsp). This integration is
an independent implementation.

Not affiliated with Birdfy or Netvue.

---

## Magyar

Home Assistant integráció a **Birdfy** madáretető-kamerákhoz (gyártó: Netvue).
A **madárlátogatásokat** hozza be a Home Assistantbe: milyen madár jött, mikor,
fotóval és napi számlálóval. Élő videó nincs benne, csak a látogatások.

> **Állapot: korai tesztverzió (0.4), Birdfy Cam 2 Pro-n kipróbálva.** A Birdfy felhő API-ja nem nyilvános, az
> integráció a közösség által visszafejtett működésre épül. Még nincs minden
> Birdfy-modellen kipróbálva.

### Mit kapsz

Kamerákként:

| Entitás | Mit mutat |
|---|---|
| `event.<kamera>_bird_visit` | Minden új madárlátogatáskor jelez. Attribútumok: `species` (fő faj), `species_en` (angol név), `species_list`, `bird_count` (madarak száma), `confidence`, `candidates` (további lehetséges fajok), `visit_time`, `event_id`. Automatizálás indítására való. |
| `sensor.<kamera>_last_visitor` | Az utolsó látogató faja (ugyanazokkal az attribútumokkal) |
| `sensor.<kamera>_last_visit` | Az utolsó látogatás ideje |
| `sensor.<kamera>_visits_today` | A mai madárlátogatások száma, fajonkénti bontással a `species` attribútumban (éjfélkor nullázódik) |
| `sensor.<kamera>_motion_events_today` | Az összes mai mozgásesemény, madárral vagy anélkül (alapból kikapcsolva) |
| `image.<kamera>_last_visit_photo` | Az utolsó madárlátogatás fotója |

**Látogatásnak** az a mozgásesemény számít, amelyen a Birdfy MI-je legalább egy
madarat felismert. A madár nélküli mozgás (szél, mókus, macska) nem látogatás.

Magyar nyelvű HA-ban az entitások nevei magyarul jelennek meg.

### Hogyan működik

- Az integráció időnként lekérdezi a Birdfy felhőt (alapból 60 másodpercenként,
  ez az integráció beállításaiban módosítható). Egy látogatás ennyi késéssel
  jelenik meg a Home Assistantben.
- A fajneveket a Birdfy saját MI-felismerése adja, ehhez Birdfy-előfizetés kellhet.
  A Birdfy angolul küldi őket, az integráció **magyarul** is meg tudja jeleníteni
  (a gyakori kerti és madáretető-látogató fajokat). Alapból a Home Assistant
  nyelvét követi; ez az integráció **Konfigurálás** menüjében átállítható. Az
  angol név mindig megmarad a `species_en` attribútumban.
- Az utolsó látogatás fotója egyszer töltődik le, és csak a memóriában marad;
  az ideiglenes letöltési link nincs tárolva és naplózva.
- Az integráció indulása előtti látogatásokra nem jön esemény.

### Biztonság és adatvédelem

- Használj **külön Birdfy-fiókot**, amellyel a kamera meg van osztva, ne a fő
  fiókodat. A Home Assistantből való bejelentkezés kiléptetheti a mobilappot
  ugyanabból a fiókból.
- Maga a jelszó **nincs tárolva**: a Birdfy-bejelentkezéshez csak a jelszó MD5
  hash-e kell, ezért csak ez kerül a beállításokba. (Az MD5-öt a Birdfy szervere
  követeli meg; a hash-t ettől még bizalmasan kell kezelni.)
- A munkamenet-tokenek csak a memóriában vannak, és soha nem kerülnek a naplóba.
- A diagnosztikai letöltésből ki vannak takarva az e-mail-cím, a sorozatszámok,
  az azonosítók és a linkek.

### Telepítés (HACS)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=adkulik&repository=ha-birdfy&category=integration)

Kattints a fenti gombra, vagy add hozzá kézzel a tárolót:

1. HACS → ⋮ → **Egyéni tárolók** → `https://github.com/adkulik/ha-birdfy`, típus: **Integráció**.
2. Telepítsd a **Birdfy**-t, majd indítsd újra a Home Assistantot.
3. Beállítások → Eszközök és szolgáltatások → **Integráció hozzáadása** → **Birdfy**, és jelentkezz be, vagy kattints ide:

[![Open your Home Assistant instance and start setting up Birdfy.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=birdfy)

### Hibakeresés

Ha a modelleden valami nem működik, kapcsold be a debug naplózást a
`custom_components.birdfy`-ra, és töltsd le a diagnosztikát az integráció
oldaláról. Mindkettőt csatold egy issue-hoz (jelszót és tokent nem tartalmaznak).

Nem áll kapcsolatban a Birdfy-jal vagy a Netvue-val.
