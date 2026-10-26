"""A vészhelyzeti csatorna és NodeInfo-időköz beállítása a node-on.

A rutin hírküldés (main.py) NEM állítja a csatornát, hogy ne írjon feleslegesen
a node flash-ébe minden futáskor (különösen cron-módban). Ezt a scriptet elég
egyszer lefuttatni – illetve akkor, ha a csatorna beállításait (`config.toml`
[meshtastic] szekció) módosítod.

Minden beállítást a config.toml-ból olvas.

Használat:
    python setup_channel.py
"""

import logging

from main import cfg, build_handler
from mt_lib import MAX_NODE_INFO_BROADCAST_SECS, MIN_NODE_INFO_BROADCAST_SECS


logger = logging.getLogger(__name__)


def main():
    node_info_interval_s = cfg(
        "meshtastic.node_info_broadcast_secs",
        MAX_NODE_INFO_BROADCAST_SECS,
    )
    if type(node_info_interval_s) is not int or not (
        MIN_NODE_INFO_BROADCAST_SECS
        <= node_info_interval_s
        <= MAX_NODE_INFO_BROADCAST_SECS
    ):
        raise SystemExit(
            "Hiba: a meshtastic.node_info_broadcast_secs értéke 3600 és "
            f"{MAX_NODE_INFO_BROADCAST_SECS} közötti egész szám legyen."
        )

    mt = build_handler()

    try:
        mt.connect()
    except Exception as e:
        logger.error("Nem sikerült csatlakozni a node-hoz: %s", e)
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")

    try:
        mt.setChannel(
            edit_channel=cfg("meshtastic.emergency_channel_number"),
            new_settings={
                'psk': 'AQ==',
                'name': cfg("meshtastic.emergency_channel_name"),
                'uplink_enabled': False,
                'downlink_enabled': True,
                'position_precision': 13,
            },
        )
        mt.setNodeInfoBroadcastInterval(node_info_interval_s)
        logger.info(
            "Vészhelyzeti csatorna beállítva; NodeInfo küldési időköz: %d másodperc.",
            node_info_interval_s,
        )
    except Exception as e:
        logger.error("Csatorna vagy NodeInfo beállítása sikertelen: %s", e)
        raise SystemExit(f"Hiba: csatorna vagy NodeInfo beállítása sikertelen: {e}") from e
    finally:
        try:
            mt.disconnect()
        except Exception as e:
            logger.error("Lecsatlakozás sikertelen: %s", e)


if __name__ == "__main__":
    main()
