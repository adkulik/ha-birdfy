"""Hungarian names for the bird species Birdfy reports (in English).

Covers the usual garden and feeder visitors in Central Europe. Names that are
not in the list stay in English.
"""

from __future__ import annotations

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


def hungarian_name(name: str) -> str | None:
    """Return the Hungarian name, or None if it is not known."""
    key = name.strip().lower()
    if key in HU_NAMES:
        return HU_NAMES[key]
    for prefix in _PREFIXES:
        if key.startswith(prefix) and key[len(prefix):] in HU_NAMES:
            return HU_NAMES[key[len(prefix):]]
    return None


def translate(name: str | None, language: str) -> str | None:
    """Translate one species name to the chosen language (en keeps it)."""
    if not name or language != "hu":
        return name
    return hungarian_name(name) or name
