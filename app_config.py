"""A config.toml betöltése és a beállítások kiolvasása.

Külön modulban van, hogy olyan scriptek is használhassák, amelyek nem
akarják a ``main`` modul mellékhatásait (pl. a logfájl létrehozását) –
ilyen a root jogokkal futó ``setup_rak_hat.py``.
"""

import tomllib


CONFIG_FILE = "config.toml"

_MISSING = object()


def _load(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Hiba: a konfigurációs fájl nem található: {path}")
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"Hiba: a konfigurációs fájl ({path}) hibás formátumú: {e}")


config = _load(CONFIG_FILE)


def cfg(path, default=_MISSING):
    """Beolvas egy értéket a configból 'szekcio.kulcs' útvonal alapján.

    Ha a kulcs hiányzik és nincs megadva ``default``, érthető hibaüzenettel
    kilép a program (a nyers KeyError helyett)."""
    node = config
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            if default is not _MISSING:
                return default
            raise SystemExit(
                f"Hiba: hiányzó vagy olvashatatlan beállítás a {CONFIG_FILE} fájlban: '{path}'"
            )
        node = node[part]
    return node
