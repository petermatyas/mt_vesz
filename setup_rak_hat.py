"""A RAK6421 Pi HAT rádió-beállításának telepítése a meshtasticd számára.

A config.toml ``[rak_hat]`` szekciója alapján (``lora_module``, ``slot``,
``preset_file``) a meshtasticd ``config.d`` könyvtárába a megfelelő lora
preset kerül (vagy ``auto`` módban onnan minden lora preset kikerül, hogy a HAT
EEPROM-os felismerése működjön), majd a meshtasticd újraindul.

Root jogot igényel (a /etc/meshtasticd írása és a szolgáltatás újraindítása
miatt), ezért a venv Pythonjával, sudo-val futtasd. A logfájlt szándékosan nem
írja (csak konzolra naplóz), hogy a root ne hozza létre a mt_vesz.log-ot.

Használat:
    sudo venv/bin/python setup_rak_hat.py            # beállítás + újraindítás
    sudo venv/bin/python setup_rak_hat.py --no-restart
    venv/bin/python setup_rak_hat.py --check         # csak ellenőrzés (root nélkül is)
"""

import argparse
import logging
import os
import sys

import rak_hat
from app_config import cfg


logger = logging.getLogger("setup_rak_hat")


def main():
    parser = argparse.ArgumentParser(description="RAK6421 Pi HAT preset beállítása a meshtasticd-hez.")
    parser.add_argument("--check", action="store_true",
                        help="csak ellenőrzi a beállítást, nem módosít")
    parser.add_argument("--no-restart", action="store_true",
                        help="a módosítás után ne indítsa újra a meshtasticd-t")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not sys.platform.startswith("linux"):
        raise SystemExit("Hiba: a RAK HAT beállítása csak Linuxon (Raspberry Pi) futtatható.")

    base_dir = cfg("rak_hat.meshtasticd_dir", rak_hat.DEFAULT_MESHTASTICD_DIR)
    try:
        filename = rak_hat.preset_filename(
            lora_module=cfg("rak_hat.lora_module", "auto"),
            slot=cfg("rak_hat.slot", 1),
            preset_file=cfg("rak_hat.preset_file", ""),
        )
    except rak_hat.RakHatConfigError as e:
        raise SystemExit(f"Hiba a config.toml [rak_hat] szekciójában: {e}")

    wanted = filename or "auto (HAT EEPROM felismerés, nincs preset)"
    logger.info("Kívánt rádió-beállítás: %s", wanted)

    if args.check:
        problems = rak_hat.check_preset(filename, base_dir)
        for p in problems:
            logger.warning(p)
        active = rak_hat.is_meshtasticd_active()
        if active is False:
            logger.warning("A meshtasticd szolgáltatás nem fut (systemctl status meshtasticd).")
        if problems:
            raise SystemExit(1)
        logger.info("A meshtasticd beállítása megfelel a config.toml-nak.")
        return

    if os.geteuid() != 0:
        raise SystemExit("Hiba: root jog szükséges. Futtasd így: sudo venv/bin/python setup_rak_hat.py")

    try:
        changes = rak_hat.install_preset(filename, base_dir)
    except (OSError, FileNotFoundError) as e:
        raise SystemExit(f"Hiba: {e}")

    if not changes:
        logger.info("Nem kellett módosítani – a config.d már megfelelő.")
    for c in changes:
        logger.info(c)

    if changes and not args.no_restart:
        logger.info("A meshtasticd újraindítása...")
        try:
            rak_hat.restart_meshtasticd()
        except Exception as e:
            raise SystemExit(f"Hiba: a meshtasticd újraindítása sikertelen: {e}")
        logger.info("Kész. Napló: journalctl -u meshtasticd -f")


if __name__ == "__main__":
    main()
