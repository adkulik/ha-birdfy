"""Build the species name data from the Multilingual IOC World Bird List.

Usage:
    python scripts/build_species_names.py "Multiling IOC 15.2.xlsx"

Download the spreadsheet from https://www.worldbirdnames.org/ioc-lists/master-list-2
(IOC World Bird List, CC BY licence; multilingual names compiled by Peter Kovalik).

It writes custom_components/birdfy_connect/species_names/:
- index.json.gz: English-name lookup keys -> species number
- <language>.json.gz: one name per species number for that language
- languages.json: the languages that were built, with their native names
Run it again whenever a new IOC version comes out.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent.parent / "custom_components/birdfy_connect/species_names"

# IOC column header -> (Home Assistant language code, native language name).
LANGUAGES: dict[str, tuple[str, str]] = {
    "afrikaans": ("af", "Afrikaans"),
    "arabic": ("ar", "العربية"),
    "belarusian": ("be", "Беларуская"),
    "bulgarian": ("bg", "Български"),
    "catalan": ("ca", "Català"),
    "chinese": ("zh-Hans", "简体中文"),
    "chinese (traditional)": ("zh-Hant", "繁體中文"),
    "croatian": ("hr", "Hrvatski"),
    "czech": ("cs", "Čeština"),
    "danish": ("da", "Dansk"),
    "dutch": ("nl", "Nederlands"),
    "estonian": ("et", "Eesti"),
    "finnish": ("fi", "Suomi"),
    "french": ("fr", "Français"),
    "german": ("de", "Deutsch"),
    "greek": ("el", "Ελληνικά"),
    "hebrew": ("he", "עברית"),
    "hungarian": ("hu", "Magyar"),
    "icelandic": ("is", "Íslenska"),
    "indonesian": ("id", "Bahasa Indonesia"),
    "italian": ("it", "Italiano"),
    "japanese": ("ja", "日本語"),
    "korean": ("ko", "한국어"),
    "latvian": ("lv", "Latviešu"),
    "lithuanian": ("lt", "Lietuvių"),
    "macedonian": ("mk", "Македонски"),
    "norwegian": ("nb", "Norsk"),
    "persian": ("fa", "فارسی"),
    "polish": ("pl", "Polski"),
    "portuguese": ("pt", "Português"),
    "portuguese (lisbon)": ("pt", "Português"),
    "portuguese (portugal)": ("pt", "Português"),
    "portuguese (brazil)": ("pt-BR", "Português (Brasil)"),
    "portuguese (lusophone)": ("pt-BR", "Português (Brasil)"),
    "portuguese (portuguese)": ("pt", "Português"),
    "esperanto": ("eo", "Esperanto"),
    "malayalam": ("ml", "മലയാളം"),
    "northern sami": ("se", "Davvisámegiella"),
    "romanian": ("ro", "Română"),
    "russian": ("ru", "Русский"),
    "serbian": ("sr", "Српски"),
    "slovak": ("sk", "Slovenčina"),
    "slovenian": ("sl", "Slovenščina"),
    "spanish": ("es", "Español"),
    "swedish": ("sv", "Svenska"),
    "thai": ("th", "ไทย"),
    "turkish": ("tr", "Türkçe"),
    "ukrainian": ("uk", "Українська"),
}

# Short forms Birdfy uses ("Blue Tit" for IOC's "Eurasian Blue Tit").
PREFIXES = ("eurasian ", "european ", "common ", "western ", "northern ")


# Names Birdfy (or the eBird/Clements list) uses that differ from IOC's.
ALIASES = {
    "long-tailed bushtit": "long-tailed tit",
    "waxwing": "bohemian waxwing",
    "rock pigeon": "rock dove",
    "feral pigeon": "rock dove",
    "domestic pigeon": "rock dove",
    "gray-headed woodpecker": "grey-headed woodpecker",
}


def normalize(name: str) -> str:
    name = name.strip().lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", name)


def lookup_keys(english: str) -> list[str]:
    """The exact key first, then looser variants (US spelling, no prefix)."""
    key = normalize(english)
    keys = [key]
    if "grey" in key:
        keys.append(key.replace("grey", "gray"))
    for prefix in PREFIXES:
        if key.startswith(prefix):
            short = key[len(prefix):]
            keys.append(short)
            if "grey" in short:
                keys.append(short.replace("grey", "gray"))
    return keys


def find_header(ws) -> tuple[int, list[str]]:
    for idx, row in enumerate(ws.iter_rows(max_row=10, values_only=True), start=1):
        cells = [normalize(str(c)) if c is not None else "" for c in row]
        if "english" in cells:
            return idx, cells
    raise SystemExit("Could not find a header row with an 'English' column")


def main(path: str) -> None:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[wb.sheetnames[0]]
    header_row, header = find_header(ws)
    english_col = header.index("english")

    columns: dict[str, int] = {}
    skipped = []
    for col, title in enumerate(header):
        if not title or col == english_col:
            continue
        if title in LANGUAGES:
            code = LANGUAGES[title][0]
            columns.setdefault(code, col)
        elif col > english_col:
            skipped.append(title)

    species: list[list[str]] = []
    index: dict[str, int] = {}
    loose: dict[str, set[int]] = {}
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        english = row[english_col] if english_col < len(row) else None
        if not isinstance(english, str) or not english.strip():
            continue
        number = len(species)
        species.append([_display(row[c] if c < len(row) else None) for c in columns.values()])
        keys = lookup_keys(english)
        index.setdefault(keys[0], number)
        for key in keys[1:]:
            loose.setdefault(key, set()).add(number)
    # A loose key is only used when it points to a single species and is not
    # itself the full name of another one.
    for key, numbers in loose.items():
        if len(numbers) == 1 and key not in index:
            index[key] = next(iter(numbers))

    for alias, target in ALIASES.items():
        if target in index:
            index.setdefault(alias, index[target])
        else:
            print(f"Alias target not found: {target}")

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json.gz"):
        old.unlink()
    _write(OUT / "index.json.gz", index)
    built = {}
    for pos, code in enumerate(columns):
        names = [row[pos] for row in species]
        if sum(1 for n in names if n) < 100:
            continue  # nearly empty column
        _write(OUT / f"{code}.json.gz", names)
        native = next(n for t, (c, n) in LANGUAGES.items() if c == code)
        built[code] = native
    (OUT / "languages.json").write_text(
        json.dumps(dict(sorted(built.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{len(species)} species, {len(index)} lookup keys, {len(built)} languages: {', '.join(sorted(built))}")
    if skipped:
        print("Columns not used:", ", ".join(skipped))


def _display(value) -> str:
    """IOC writes some languages in lower case; show names capitalised."""
    name = " ".join(str(value).split()) if value else ""
    return name[:1].upper() + name[1:]


def _write(path: Path, data) -> None:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    path.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
