"""A node-on várakozó üzenetek kiolvasása – a node memóriájának felszabadítására.

A Meshtastic firmware a rádión vett csomagokat egy belső sorban tárolja a
csatlakozó kliens (telefonos app vagy API-kliens) számára. Ha soha senki nem
olvassa ki őket, ez a sor tele fut, és a node memóriája fogy – a legrégebbi
csomagok elvesznek. Amint egy kliens csatlakozik, a firmware kiadja neki a
tárolt csomagokat, és a sor felszabadul.

Ez a script pontosan ezt teszi: csatlakozik a node-hoz, a beállított ideig
(``[read_messages] listen_time_s``) fogadja a node által kiadott csomagokat,
naplózza a szöveges üzeneteket, majd lecsatlakozik. Crontabból hívva a node
üzenetsora rendszeresen ürül.

A csatornát NEM állítja (azt a setup_channel.py végzi egyszer), és nem is küld
üzenetet – csak olvas.

Használat:
    python read_messages.py
"""

import logging
import threading
import time
from datetime import datetime

from pubsub import pub

from main import cfg, build_handler


logger = logging.getLogger(__name__)


class MessageCollector:
    """Összegyűjti a node által kiadott szöveges üzeneteket.

    A meshtastic könyvtár a saját olvasó szálán hívja a callbacket, ezért a
    számlálót zárral védjük.
    """

    def __init__(self):
        self.count = 0
        self._lock = threading.Lock()

    def on_receive(self, packet=None, interface=None):
        try:
            decoded = (packet or {}).get("decoded") or {}
            text = decoded.get("text")
            if text is None:
                return  # nem szöveges csomag (pozíció, telemetria, …)

            sender = packet.get("fromId") or packet.get("from") or "ismeretlen"
            channel = packet.get("channel", 0)
            rx_time = packet.get("rxTime")
            when = (datetime.fromtimestamp(rx_time).strftime("%Y-%m-%d %H:%M:%S")
                    if rx_time else "ismeretlen idő")

            with self._lock:
                self.count += 1

            logger.info("Vett üzenet [%s, csatorna %s, %s]: %r",
                        sender, channel, when, text)
        except Exception as e:
            # Egy hibás csomag ne akassza meg az olvasó szálat: a lényeg, hogy a
            # node sora ürüljön.
            logger.error("Vett csomag feldolgozása sikertelen: %s", e)


def main():
    listen_time = cfg("read_messages.listen_time_s", 15)

    collector = MessageCollector()
    # Már a csatlakozás előtt feliratkozunk, hogy a kapcsolat felépítésekor
    # azonnal kiadott (sorban álló) üzenetek se maradjanak le.
    pub.subscribe(collector.on_receive, "meshtastic.receive.text")

    mt = build_handler()

    try:
        mt.connect()
    except Exception as e:
        logger.error("Nem sikerült csatlakozni a node-hoz: %s", e)
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")

    try:
        # A csatlakozáskor a firmware kiadja a tárolt csomagokat; a könyvtár
        # olvasó szála dolgozza fel őket. Itt csak megvárjuk, hogy a sor
        # kiürüljön.
        logger.info("Üzenetek olvasása %d másodpercig...", listen_time)
        time.sleep(listen_time)
        logger.info("Kiolvasott üzenetek száma: %d", collector.count)
    finally:
        pub.unsubscribe(collector.on_receive, "meshtastic.receive.text")
        try:
            mt.disconnect()
        except Exception as e:
            logger.error("Lecsatlakozás sikertelen: %s", e)


if __name__ == "__main__":
    main()
