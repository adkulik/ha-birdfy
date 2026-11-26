"""Species names in the user's language.

Birdfy reports species in English. They are translated with the Multilingual
IOC World Bird List (see scripts/build_species_names.py), loaded one language
at a time from species_names/. The hand-picked Hungarian names below take
precedence over the IOC ones. Names that can't be matched stay in English.
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "species_names"

# Curated Hungarian names for common Central European feeder visitors.
HU_NAMES: dict[str, str] = {
    # Tits
    "great tit": "Széncinege",
    "blue tit": "Kék cinege",
    "coal tit": "Fenyvescinege",
    "marsh tit": "Barátcinege",
    "willow tit": "Kormosfejű cinege",
    "crested tit": "Búbos cinege",
    "long-tailed tit": "Őszapó",
    "long-tailed bushtit": "Őszapó",
    "penduline tit": "Függőcinege",
    # Nuthatch, treecreepers, wren, crests
    "nuthatch": "Csuszka",
    "treecreeper": "Hegyi fakusz",
    "short-toed treecreeper": "Rövidkarmú fakusz",
    "wren": "Ökörszem",
    "goldcrest": "Sárgafejű királyka",
    "firecrest": "Tüzesfejű királyka",
    # Sparrows, finches, buntings
    "house sparrow": "Házi veréb",
    "tree sparrow": "Mezei veréb",
    "chaffinch": "Erdei pinty",
    "brambling": "Fenyőpinty",
    "greenfinch": "Zöldike",
    "goldfinch": "Tengelic",
    "siskin": "Csíz",
    "linnet": "Kenderike",
    "bullfinch": "Süvöltő",
    "hawfinch": "Meggyvágó",
    "serin": "Csicsörke",
    "yellowhammer": "Citromsármány",
    "reed bunting": "Nádi sármány",
    # Thrushes, robins, chats
    "blackbird": "Fekete rigó",
    "song thrush": "Énekes rigó",
    "fieldfare": "Fenyőrigó",
    "mistle thrush": "Léprigó",
    "redwing": "Szőlőrigó",
    "robin": "Vörösbegy",
    "black redstart": "Házi rozsdafarkú",
    "redstart": "Kerti rozsdafarkú",
    "dunnock": "Erdei szürkebegy",
    # Warblers, flycatchers, others
    "blackcap": "Barátposzáta",
    "chiffchaff": "Csilpcsalpfüzike",
    "spotted flycatcher": "Szürke légykapó",
    "waxwing": "Csonttollú",
    "bohemian waxwing": "Csonttollú",
    "starling": "Seregély",
    "white wagtail": "Barázdabillegető",
    "barn swallow": "Füsti fecske",
    "hoopoe": "Búbos banka",
    "golden oriole": "Sárgarigó",
    "red-backed shrike": "Tövisszúró gébics",
    "crested lark": "Búbos pacsirta",
    # Woodpeckers
    "great spotted woodpecker": "Nagy fakopáncs",
    "syrian woodpecker": "Balkáni fakopáncs",
    "middle spotted woodpecker": "Közép fakopáncs",
    "lesser spotted woodpecker": "Kis fakopáncs",
    "green woodpecker": "Zöld küllő",
    # Crows, jays
    "jay": "Szajkó",
    "magpie": "Szarka",
    "hooded crow": "Dolmányos varjú",
    "jackdaw": "Csóka",
    "rook": "Vetési varjú",
    # Pigeons, doves
    "collared dove": "Balkáni gerle",
    "wood pigeon": "Örvös galamb",
    "rock pigeon": "Házi galamb",
    "feral pigeon": "Házi galamb",
    "rock dove": "Szirti galamb",
    "turtle dove": "Vadgerle",
    # Raptors
    "sparrowhawk": "Karvaly",
    "kestrel": "Vörös vércse",
}

_PREFIXES = ("eurasian ", "european ", "common ", "western ", "northern ")

_index: dict[str, int] | None = None
_names: dict[str, list[str]] = {}


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().replace("\u2019", "'").split())


def _keys(name: str) -> list[str]:
    key = _normalize(name)
    keys = [key]
    for prefix in _PREFIXES:
        if key.startswith(prefix):
            keys.append(key[len(prefix):])
    return keys


def _read(path: Path):
    return json.loads(gzip.decompress(path.read_bytes()))


def available_languages() -> dict[str, str]:
    """Language codes with species names, mapped to their native names (blocking)."""
    try:
        return json.loads((DATA_DIR / "languages.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"hu": "Magyar"}


def load_language(language: str) -> None:
    """Load the names for one language into memory (blocking: run in an executor)."""
    global _index
    if language == "en" or language in _names:
        return
    path = DATA_DIR / f"{language}.json.gz"
    if not path.exists():
        return
    try:
        if _index is None:
            _index = _read(DATA_DIR / "index.json.gz")
        _names[language] = _read(path)
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not load species names for %s: %s", language, err)


def resolve_language(choice: str, ha_language: str | None, available: dict[str, str]) -> str:
    """Turn the option ("auto" or a code) into a language that has names."""
    if choice != "auto":
        return choice if choice == "en" or choice in available else "en"
    lang = ha_language or "en"
    candidates = [lang, lang.split("-")[0]]
    if lang in ("nn", "no"):
        candidates.append("nb")
    if lang.startswith("zh"):
        traditional = lang in ("zh-Hant", "zh-TW", "zh-HK")
        candidates += ["zh-Hant", "zh-Hans"] if traditional else ["zh-Hans", "zh-Hant"]
    for code in candidates:
        if code in available:
            return code
    return "en"


def hungarian_name(name: str) -> str | None:
    """Return the curated Hungarian name, or None if it is not known."""
    for key in _keys(name):
        if key in HU_NAMES:
            return HU_NAMES[key]
    return None


def localized_name(name: str, language: str) -> str | None:
    """Return the name in the given language, or None if it is not known."""
    if language == "hu" and (curated := hungarian_name(name)):
        return curated
    names = _names.get(language)
    if not names or _index is None:
        return None
    for key in _keys(name):
        number = _index.get(key)
        if number is not None and number < len(names) and names[number]:
            return names[number]
    return None


def translate(name: str | None, language: str) -> str | None:
    """Translate one species name to the chosen language (en keeps it)."""
    if not name or language == "en":
        return name
    return localized_name(name, language) or name
