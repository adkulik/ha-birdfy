# Birdfy for Home Assistant

[🇬🇧 English](#english) | [🇭🇺 Magyar](#magyar)

---

## English

A Home Assistant integration for **Birdfy** bird feeder cameras (made by Netvue).
It brings **bird visits** into Home Assistant: who visited, when, a photo, and a
daily count. There is no live video, only visits.

> **Status: early test version (0.1).** The Birdfy cloud API is not public; this
> integration uses what the community has reverse-engineered. It has not yet been
> confirmed on every Birdfy model.

### What you get

For each camera on the account:

| Entity | What it shows |
|---|---|
| `event.<camera>_bird_visit` | Fires on every new visit, with `species`, `visit_time` and `event_id` attributes. Use it as an automation trigger. |
| `sensor.<camera>_last_visitor` | The label Birdfy gave the last visit (the species when AI recognition identified it) |
| `sensor.<camera>_last_visit` | Time of the last visit |
| `sensor.<camera>_visits_today` | Number of visits today (resets at midnight) |
| `image.<camera>_last_visit_photo` | Snapshot of the last visit |

### How it works

- The integration polls the Birdfy cloud (every 60 s by default, adjustable in
  the integration options). A visit shows up in Home Assistant with that much delay.
- Species names come from Birdfy's own AI recognition, which may need an active
  Birdfy subscription.
- Visits that happened before the integration started do not fire events.

### Security and privacy

- Use a **separate Birdfy account** that the camera is shared with, not your main
  account. Logging in from Home Assistant may log the mobile app out of the same account.
- The password itself is **not stored**: the Birdfy login only needs an MD5 hash
  of it, so only that hash is saved in the config entry. (MD5 is what the Birdfy
  service requires; treat the hash as sensitive anyway.)
- Session tokens are kept in memory only and are never logged.
- Snapshots are downloaded once per visit and kept in memory; their temporary
  download links are not stored.
- Diagnostics downloads redact email, serial numbers, IDs and URLs.

### Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/adkulik/ha-birdfy`, type **Integration**.
2. Install **Birdfy**, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **Birdfy**, and sign in.

### Example automation

```yaml
triggers:
  - trigger: state
    entity_id: event.feeder_bird_visit
actions:
  - action: notify.mobile_app_iphone
    data:
      message: "{{ state_attr('event.feeder_bird_visit', 'species') or 'A bird' }} is at the feeder"
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
A **madárlátogatásokat** hozza be a Home Assistantbe: ki jött, mikor, fotóval, és
napi számlálóval. Élő videó nincs benne, csak a látogatások.

> **Állapot: korai tesztverzió (0.1).** A Birdfy felhő API-ja nem nyilvános, az
> integráció a közösség által visszafejtett működésre épül. Még nincs minden
> Birdfy-modellen kipróbálva.

### Mit kapsz

Kamerákként:

| Entitás | Mit mutat |
|---|---|
| `event.<kamera>_bird_visit` | Minden új látogatáskor jelez, `species` (faj), `visit_time` és `event_id` attribútummal. Automatizálás indítására való. |
| `sensor.<kamera>_last_visitor` | Az utolsó látogatás Birdfy-címkéje (a madárfaj, ha az MI felismerte) |
| `sensor.<kamera>_last_visit` | Az utolsó látogatás ideje |
| `sensor.<kamera>_visits_today` | A mai látogatások száma (éjfélkor nullázódik) |
| `image.<kamera>_last_visit_photo` | Az utolsó látogatás fotója |

Magyar nyelvű HA-ban az entitások nevei magyarul jelennek meg.

### Hogyan működik

- Az integráció időnként lekérdezi a Birdfy felhőt (alapból 60 másodpercenként,
  ez az integráció beállításaiban módosítható). Egy látogatás ennyi késéssel
  jelenik meg a Home Assistantben.
- A fajneveket a Birdfy saját MI-felismerése adja, ehhez Birdfy-előfizetés kellhet.
- Az integráció indulása előtti látogatásokra nem jön esemény.

### Biztonság és adatvédelem

- Használj **külön Birdfy-fiókot**, amellyel a kamera meg van osztva, ne a fő
  fiókodat. A Home Assistantből való bejelentkezés kiléptetheti a mobilappot
  ugyanabból a fiókból.
- Maga a jelszó **nincs tárolva**: a Birdfy-bejelentkezéshez csak a jelszó MD5
  hash-e kell, ezért csak ez kerül a beállításokba. (Az MD5-öt a Birdfy szervere
  követeli meg; a hash-t ettől még bizalmasan kell kezelni.)
- A munkamenet-tokenek csak a memóriában vannak, és soha nem kerülnek a naplóba.
- A fotók látogatásonként egyszer töltődnek le, és a memóriában maradnak; az
  ideiglenes letöltési linkek nincsenek tárolva.
- A diagnosztikai letöltésből ki vannak takarva az e-mail-cím, a sorozatszámok,
  az azonosítók és a linkek.

### Telepítés (HACS)

1. HACS → ⋮ → **Egyéni tárolók** → `https://github.com/adkulik/ha-birdfy`, típus: **Integráció**.
2. Telepítsd a **Birdfy**-t, majd indítsd újra a Home Assistantot.
3. Beállítások → Eszközök és szolgáltatások → **Integráció hozzáadása** → **Birdfy**, és jelentkezz be.

### Hibakeresés

Ha a modelleden valami nem működik, kapcsold be a debug naplózást a
`custom_components.birdfy`-ra, és töltsd le a diagnosztikát az integráció
oldaláról. Mindkettőt csatold egy issue-hoz (jelszót és tokent nem tartalmaznak).

Nem áll kapcsolatban a Birdfy-jal vagy a Netvue-val.
