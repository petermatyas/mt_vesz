"""A node-on tárolt üzenetek kiolvasása – a node memóriájának felszabadítására.

A Meshtastic firmware a rádión vett csomagokat egy belső sorban tárolja a
csatlakozó kliens (telefonos app vagy API-kliens) számára. Ha soha senki nem
olvassa ki őket, ez a sor tele fut, és a legrégebbi csomagok elvesznek. Amint
egy kliens csatlakozik, a firmware egy sorozatban kiadja neki a tárolt
csomagokat, és a sor felszabadul.

Ez a script a node-on **tárolt** (a csatlakozásunk előtt vett) üzeneteket
olvassa ki és naplózza. A protokoll nem jelöli meg, hogy egy csomag a sorból
jött-e vagy épp most érkezett, ezért a csomag ``rxTime`` mezője alapján
válogatunk: ha a node a csatlakozásunk megkezdése ELŐTT vette, akkor tárolt
üzenet; ha közben érkezett, akkor élő forgalom – azt csak megszámoljuk, de nem
naplózzuk üzenetként.

A kapcsolatot csak addig tartjuk fenn, amíg a tárolt sor ki nem ürül: a
csomagsorozat végét onnan ismerjük fel, hogy ``drain_quiet_s`` másodpercig nem
jön új csomag. A ``max_listen_time_s`` felső korlát biztosítja, hogy folyamatos
forgalom esetén se ragadjon be a futás (fontos cron alatt).

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


class StoredMessageCollector:
    """Összegyűjti a node által kiadott csomagokat, tárolt / élő bontásban.

    A meshtastic könyvtár a saját olvasó szálán hívja a callbacket, ezért a
    közös állapotot zárral védjük.
    """

    def __init__(self, connect_started_at):
        # Eddig az időpontig vett csomagok számítanak "tárolt" üzenetnek.
        self.connect_started_at = connect_started_at
        self.stored = []
        self.live_count = 0
        self.last_packet_at = None  # a legutóbbi csomag beérkezése (monoton óra)
        self._lock = threading.Lock()

    def on_receive(self, packet=None, interface=None):
        try:
            with self._lock:
                # Minden csomag (nem csak a szöveges) jelzi, hogy a sor még ürül.
                self.last_packet_at = time.monotonic()

            decoded = (packet or {}).get("decoded") or {}
            text = decoded.get("text")
            if text is None:
                return  # nem szöveges csomag (pozíció, telemetria, …)

            rx_time = packet.get("rxTime")
            # rxTime hiányában (pl. a node órája nincs beállítva) tárolt
            # üzenetnek vesszük: inkább naplózzuk feleslegesen, mint hogy
            # kimaradjon.
            is_stored = not rx_time or rx_time < self.connect_started_at

            if not is_stored:
                with self._lock:
                    self.live_count += 1
                logger.debug("Élő üzenet érkezett olvasás közben (nem tárolt): %r", text)
                return

            when = (datetime.fromtimestamp(rx_time).strftime("%Y-%m-%d %H:%M:%S")
                    if rx_time else "ismeretlen idő")
            sender = packet.get("fromId") or packet.get("from") or "ismeretlen"
            channel = packet.get("channel", 0)

            with self._lock:
                self.stored.append(text)

            logger.info("Tárolt üzenet [%s, csatorna %s, vétel: %s]: %r",
                        sender, channel, when, text)
        except Exception as e:
            # Egy hibás csomag ne akassza meg az olvasó szálat: a lényeg, hogy a
            # node sora ürüljön.
            logger.error("Vett csomag feldolgozása sikertelen: %s", e)

    def quiet_for(self):
        """Hány másodperce nem jött csomag (a csatlakozás óta számolva)."""
        with self._lock:
            last = self.last_packet_at
        return time.monotonic() - last if last is not None else None


def drain(collector, quiet_s, max_s):
    """Megvárja, amíg a node kiadja a tárolt csomagjait.

    Akkor tekintjük késznek, ha ``quiet_s`` másodpercig egyetlen csomag sem jött
    (a sorozat véget ért), de legfeljebb ``max_s`` másodpercig várunk."""
    deadline = time.monotonic() + max_s
    started = time.monotonic()

    while time.monotonic() < deadline:
        time.sleep(0.5)
        quiet = collector.quiet_for()
        if quiet is None:
            # Még egyetlen csomag sem jött: ha már quiet_s ideje kapcsolódva
            # vagyunk, akkor a sor üres volt.
            if time.monotonic() - started >= quiet_s:
                return True
        elif quiet >= quiet_s:
            return True

    logger.warning("A %d másodperces időkorlát letelt, mielőtt a node üzenetsora "
                   "kiürült volna – a maradék a következő futáskor olvasható ki.", max_s)
    return False


def main():
    quiet_s = cfg("read_messages.drain_quiet_s", 3)
    max_s = cfg("read_messages.max_listen_time_s", 30)

    # A csatlakozás megkezdése előtti időpont a határ: az ennél korábban vett
    # csomagok a node sorában álltak.
    connect_started_at = time.time()

    collector = StoredMessageCollector(connect_started_at)
    # Már a csatlakozás előtt feliratkozunk, hogy a kapcsolat felépítésekor
    # azonnal kiadott üzenetek se maradjanak le.
    pub.subscribe(collector.on_receive, "meshtastic.receive")

    mt = build_handler()

    try:
        mt.connect()
    except Exception as e:
        logger.error("Nem sikerült csatlakozni a node-hoz: %s", e)
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")

    try:
        logger.info("A node tárolt üzeneteinek kiolvasása...")
        drain(collector, quiet_s, max_s)
        logger.info("Kiolvasott tárolt üzenetek száma: %d (közben élőben érkezett: %d)",
                    len(collector.stored), collector.live_count)
    finally:
        pub.unsubscribe(collector.on_receive, "meshtastic.receive")
        try:
            mt.disconnect()
        except Exception as e:
            logger.error("Lecsatlakozás sikertelen: %s", e)


if __name__ == "__main__":
    main()
