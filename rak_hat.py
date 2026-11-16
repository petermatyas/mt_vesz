"""RAK6421 WisMesh Pi HAT támogatás (Raspberry Pi + meshtasticd).

A HAT-ra szerelt LoRa modul (RAK13300 / RAK13302, SX1262 chip) önmagában csak
egy rádió – a Meshtastic protokollt a Pi-n futó ``meshtasticd`` szolgáltatás
(a Meshtastic firmware Linux-os változata) valósítja meg: SPI buszon vezérli a
rádiót, és a szokásos Meshtastic API-t nyújtja TCP-n (alapból
``127.0.0.1:4403``). A program tehát ugyanazzal a ``meshtastic`` Python
könyvtárral, TCP-n beszél vele, mint egy hálózati node-dal.

Ez a modul a meshtasticd rádió-beállításának (``config.d`` preset) kiválasztását
és ellenőrzését végzi a ``config.toml`` ``[rak_hat]`` szekciója alapján:

- ``lora_module = "auto"``: a meshtasticd a HAT EEPROM-ja alapján maga ismeri
  fel a hardvert; ilyenkor a ``config.d``-ben NEM lehet lora preset (az
  felülírná / letiltaná a felismerést).
- ``lora_module = "RAK13300"`` / ``"RAK13302"`` + ``slot = 1`` / ``2``: a
  meshtasticd csomag ``available.d`` könyvtárából a megfelelő preset
  (pl. ``lora-RAK6421-13300-slot1.yaml``) kerül a ``config.d``-be.
- ``preset_file``: tetszőleges ``available.d``-beli fájlnév, ha a csomagban
  más néven szerepel a preset.

Csak a Python standard könyvtárát használja.
"""

import logging
import shutil
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_TCP_PORT = 4403
DEFAULT_MESHTASTICD_DIR = "/etc/meshtasticd"

AUTO = "AUTO"
SUPPORTED_MODULES = ("RAK13300", "RAK13302")
SUPPORTED_SLOTS = (1, 2)

# A config.d-ben ilyen nevű fájlok írják le a rádiót.
LORA_PRESET_PREFIX = "lora-"
# Ide kerülnek a config.d-ből kivett (letiltott) lora presetek – nem töröljük őket.
DISABLED_DIR_NAME = "config.d.disabled-by-mt_vesz"


class RakHatConfigError(ValueError):
    """Hibás [rak_hat] beállítás a config.toml-ban."""


def preset_filename(lora_module="auto", slot=1, preset_file=""):
    """A configban megadott modulhoz tartozó preset fájl neve.

    ``None``-t ad vissza ``auto`` módban (EEPROM-os felismerés, nincs preset)."""
    if preset_file:
        name = Path(str(preset_file)).name
        if not name.endswith(".yaml"):
            raise RakHatConfigError(
                f"A rak_hat.preset_file értéke .yaml fájl legyen (most: {preset_file!r})."
            )
        return name

    module = str(lora_module).strip().upper()
    if module == AUTO:
        return None
    if module not in SUPPORTED_MODULES:
        raise RakHatConfigError(
            f"Ismeretlen rak_hat.lora_module: {lora_module!r}. "
            f"Lehetséges értékek: \"auto\", {', '.join(repr(m) for m in SUPPORTED_MODULES)}."
        )
    if type(slot) is not int or slot not in SUPPORTED_SLOTS:
        raise RakHatConfigError(
            f"A rak_hat.slot értéke 1 vagy 2 legyen (most: {slot!r})."
        )
    return f"lora-RAK6421-{module[3:]}-slot{slot}.yaml"


def _dirs(base_dir):
    base = Path(base_dir)
    return base / "available.d", base / "config.d", base / DISABLED_DIR_NAME


def active_lora_presets(base_dir=DEFAULT_MESHTASTICD_DIR):
    """A config.d-ben jelenleg aktív lora preset fájlok nevei."""
    _, config_d, _ = _dirs(base_dir)
    if not config_d.is_dir():
        return []
    return sorted(p.name for p in config_d.iterdir()
                  if p.is_file() and p.name.startswith(LORA_PRESET_PREFIX)
                  and p.name.endswith(".yaml"))


def available_rak_presets(base_dir=DEFAULT_MESHTASTICD_DIR):
    """Az available.d-ben található RAK6421 presetek nevei."""
    available_d, _, _ = _dirs(base_dir)
    if not available_d.is_dir():
        return []
    return sorted(p.name for p in available_d.glob("lora-RAK6421*.yaml"))


def check_preset(filename, base_dir=DEFAULT_MESHTASTICD_DIR):
    """Ellenőrzi, hogy a meshtasticd rádió-beállítása megfelel-e a confignak.

    ``filename`` a ``preset_filename()`` eredménye (``None`` = auto mód).
    A talált problémák listáját adja vissza (üres lista = rendben)."""
    _, config_d, _ = _dirs(base_dir)
    if not config_d.is_dir():
        return [f"Nem található a {config_d} könyvtár – telepítve van a meshtasticd?"]

    problems = []
    active = active_lora_presets(base_dir)
    if filename is None:
        if active:
            problems.append(
                "lora_module = \"auto\", de a config.d-ben lora preset van "
                f"({', '.join(active)}), ami felülírja a HAT EEPROM-os felismerését."
            )
    else:
        if filename not in active:
            problems.append(f"A(z) {filename} preset nincs a {config_d} könyvtárban.")
        others = [a for a in active if a != filename]
        if others:
            problems.append(
                f"A config.d-ben más lora preset is aktív: {', '.join(others)}."
            )
    return problems


def install_preset(filename, base_dir=DEFAULT_MESHTASTICD_DIR):
    """A config.d-t a confignak megfelelő állapotba hozza (root jog kell).

    - A nem kívánt lora preseteket átmozgatja a ``config.d.disabled-by-mt_vesz``
      könyvtárba (nem törli őket).
    - ``filename`` megadásakor bemásolja az available.d-ből a presetet.

    Visszaadja a változtatások leírásának listáját (üres = nem kellett változtatni)."""
    available_d, config_d, disabled_d = _dirs(base_dir)
    if not config_d.is_dir():
        raise FileNotFoundError(
            f"Nem található a {config_d} könyvtár – előbb telepítsd a meshtasticd-t."
        )

    src = None
    if filename is not None:
        src = available_d / filename
        if not src.is_file():
            found = available_rak_presets(base_dir)
            hint = (f" Elérhető RAK6421 presetek: {', '.join(found)}." if found
                    else " Az available.d-ben nincs RAK6421 preset – frissítsd a meshtasticd-t.")
            raise FileNotFoundError(f"Nem található a preset: {src}.{hint}")

    changes = []
    for name in active_lora_presets(base_dir):
        if name == filename:
            continue
        disabled_d.mkdir(exist_ok=True)
        shutil.move(str(config_d / name), str(disabled_d / name))
        changes.append(f"letiltva: {name} (áthelyezve ide: {disabled_d})")

    if src is not None:
        dst = config_d / filename
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            shutil.copy2(src, dst)
            changes.append(f"bemásolva: {src} -> {dst}")

    return changes


def restart_meshtasticd():
    """A meshtasticd szolgáltatás újraindítása (root jog kell)."""
    subprocess.run(["systemctl", "restart", "meshtasticd"], check=True)


def is_meshtasticd_active():
    """Fut-e a meshtasticd szolgáltatás (None, ha nem állapítható meg)."""
    try:
        res = subprocess.run(["systemctl", "is-active", "meshtasticd"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() == "active"
