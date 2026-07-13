"""Napi "életjel" üzenet küldése a Meshtastic csatornára.

Ez a script naponta egyszer (a crontab bejegyzés szerint éjfélkor) fut le, és
egyetlen üzenetet küld, ami azt mutatja, hogy az eszköz működik. Így a csatorna
hallgatói akkor is látják, hogy a rendszer él, ha éppen nincs új VESZ-hír.

A rutin hírküldéstől (main.py) függetlenül, külön futtatható – a config.toml
[meshtastic] és [heartbeat] szekcióit használja. A csatornát NEM állítja
(azt a setup_channel.py végzi egyszer), így nem ír feleslegesen a node flash-ébe.

Használat:
    python heartbeat.py
"""

import logging
from datetime import datetime

from main import cfg, build_handler


logger = logging.getLogger(__name__)


def build_message():
    """Összeállítja az életjel üzenetet a config alapján, a {time} helyére a
    küldés aktuális idejét helyettesítve."""
    template = cfg("heartbeat.message", "Az eszköz működik. Időpont: {time}")
    time_format = cfg("heartbeat.time_format", "%Y-%m-%d %H:%M")
    now = datetime.now().strftime(time_format)
    return template.format(time=now)


def main():
    mt = build_handler()

    try:
        mt.connect()
    except Exception as e:
        logger.error("Nem sikerült csatlakozni a node-hoz: %s", e)
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")

    try:
        message = build_message()
        logger.info("Életjel küldése: %r", message)
        mt.sendMessage(message, want_ack=cfg("meshtastic.want_ack", False))
    except Exception as e:
        logger.error("Életjel küldése sikertelen: %s", e)
    finally:
        try:
            mt.disconnect()
        except Exception as e:
            logger.error("Lecsatlakozás sikertelen: %s", e)


if __name__ == "__main__":
    main()
