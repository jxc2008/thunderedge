"""
backend/team_names.py

Maps full team names (as used in Kalshi market titles and VLR.gg match pages)
to the abbreviations stored in half_win_rates.json.

Used by TheoEngine and the main loop to normalise team names before rate lookups.
"""

# Full name / common alias → abbreviation in half_win_rates.json
_TEAM_MAP = {
    # Americas
    "sentinels": "SEN",
    "nrg": "NRG",
    "nrg esports": "NRG",
    "cloud9": "C9",
    "c9": "C9",
    "100 thieves": "100T",
    "100thieves": "100T",
    "evil geniuses": "EG",
    "eg": "EG",
    "loud": "LOUD",
    "leviatan": "LEV",
    "leviatán": "LEV",
    "furia": "FUR",
    "mibr": "MIBR",
    "kr esports": "KR",
    "envy": "ENVY",
    "2game esports": "2G",
    "2g": "2G",

    # EMEA
    "fnatic": "FNC",
    "team liquid": "TL",
    "team liquid brasil": "TLN",
    "natus vincere": "NAVI",
    "navi": "NAVI",
    "futbolist": "FUT",
    "fut esports": "FUT",
    "bbl esports": "BBL",
    "bbl": "BBL",
    "karmine corp": "KC",
    "kc": "KC",
    "gentle mates": "M8",
    "m8": "M8",
    "g2 esports": "G2",
    "g2": "G2",
    "vitality": "VIT",
    "team vitality": "VIT",
    "ulfast": "ULF",
    "ulf": "ULF",
    "team secret": "TS",
    "apeks": "APK",
    "fokus": "FS",
    "fokus esports": "FS",

    # Pacific
    "paper rex": "PRX",
    "prx": "PRX",
    "t1": "T1",
    "gen.g": "GEN",
    "gen g": "GEN",
    "drx": "DRX",
    "detonation focusme": "DFM",
    "talon esports": "TH",
    "talon": "TH",
    "rex regum qeon": "RRQ",
    "rrq": "RRQ",
    "zeta division": "ZETA",
    "zeta": "ZETA",
    "ns redforce": "NS",
    "ns": "NS",
    "global esports": "GE",
    "ge": "GE",
    "bleed esports": "BME",
    "bleed": "BME",
    "varrel": "VL",
    "made in korea": "MKOI",
    "pacific": "PCF",

    # China
    "edward gaming": "EG",  # note: shares abbrev with Evil Geniuses in different region
    "edg": "EG",
    "xi lai gaming": "GX",
    "xlg": "GX",
    "tyloo": "TLN",
    "all gamers": "APK",
    "team effortless": "EF",
}


def normalise(name: str) -> str:
    """
    Return the abbreviation for a team name, or the original name if not found.

    Case-insensitive. Strips common suffixes like 'esports', 'gaming'.
    """
    key = name.strip().lower()
    if key in _TEAM_MAP:
        return _TEAM_MAP[key]

    # Try stripping trailing 'esports' / 'gaming' / 'e-sports'
    for suffix in (' esports', ' gaming', ' e-sports', ' esport'):
        if key.endswith(suffix):
            stripped = key[: -len(suffix)].strip()
            if stripped in _TEAM_MAP:
                return _TEAM_MAP[stripped]

    # Return original (will fall back to league average in TheoEngine)
    return name
