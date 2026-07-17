import logging
import time
import tomllib

import log_setup
import mt_lib
import vesz_lib


logger = logging.getLogger(__name__)

CONFIG_FILE = "config.toml"

try:
    with open(CONFIG_FILE, "rb") as f:
        config = tomllib.load(f)
except FileNotFoundError:
    raise SystemExit(f"Hiba: a konfigurációs fájl nem található: {CONFIG_FILE}")
except tomllib.TOMLDecodeError as e:
    raise SystemExit(f"Hiba: a konfigurációs fájl ({CONFIG_FILE}) hibás formátumú: {e}")


_MISSING = object()


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


# A naplózást a config betöltése után, minden más előtt beállítjuk, hogy a
# sikeres rádiós üzenetek és minden hiba méretkorlátos logfájlba is kerüljön.
log_setup.setup_logging(
    log_file=cfg("log.file", "mt_vesz.log"),
    max_size_kb=cfg("log.max_size_kb", 1024),
    backup_count=cfg("log.backup_count", 3),
)


def build_handler():
    """A configból létrehozza a megfelelő Meshtastic handlert (TCP / serial).

    A csatlakozás még nem történik meg – azt a hívó ``mt.connect()``-tel indítja."""
    connect_mode = cfg("meshtastic.connect_mode").lower()
    # 0 (vagy hiányzó) => végtelen újrapróbálkozás; >0 => ennyi próba után feladja.
    max_retries = cfg("meshtastic.connect_max_retries", 0) or None
    if connect_mode == "tcp":
        return mt_lib.MtTcpHandler(host=cfg("meshtastic.host"), max_retries=max_retries)
    elif connect_mode == "serial":
        return mt_lib.MtSerialHandler(port=cfg("meshtastic.port"), max_retries=max_retries)
    raise SystemExit("Hiba: érvénytelen connect_mode a config fájlban (TCP / serial).")


def init():
    """Kapcsolódás a node-hoz. A mt.connect() a beállított darabszámig
    (connect_max_retries) újrapróbálkozik; ha nem sikerül, hibával kilépünk.

    A csatorna beállítását NEM itt végezzük – azt a setup_channel.py külön,
    egyszeri lépésként teszi meg, hogy a rutin futások ne írjanak feleslegesen
    a node flash-ébe."""
    try:
        mt.connect()
    except Exception as e:
        logger.error("Nem sikerült csatlakozni a node-hoz: %s", e)
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")


def job():

    try:
        news = feeds.getNews()
    except Exception as e:
        logger.error("Hírek lekérése sikertelen: %s", e)
        return

    logger.info("Új hírek száma: %d", len(news))
    delay = cfg("meshtastic.time_between_messages_s")
    want_ack = cfg("meshtastic.want_ack", False)
    ack_timeout_s = cfg("meshtastic.ack_timeout_s", 30)
    ack_max_retries = cfg("meshtastic.ack_max_retries", 2)
    for idx, i in enumerate(news):
        if idx > 0:
            time.sleep(delay)  # szünet CSAK a hírek között, az utolsó után nem
        logger.info("Hír küldése: %r", i)
        try:
            mt.sendMessage(i, want_ack=want_ack, ack_timeout_s=ack_timeout_s,
                           ack_max_retries=ack_max_retries)
        except Exception as e:
            logger.error("Hír küldése sikertelen: %s", e)






if __name__ == "__main__":
    mt = build_handler()

    feeds = vesz_lib.BMFeeds(
        rss_url=cfg("vesz.rss_url"),
        postfix_text=cfg("vesz.postfix_text"),
        max_message_length=cfg("vesz.max_message_length", 0),
        max_cache_entries=cfg("vesz.cache_max_entries", 0),
        clear_time_s=cfg("vesz.cache_clear_time_days", 30) * 24 * 3600,
    )


    init()
    job()

    if cfg("general.use_scheduler", True):
        # Beépített időzítővel folyamatosan fut.
        import schedule

        schedule.every(cfg("vesz.rss_read_time_min")).minutes.do(job)

        while True:
            try:
                schedule.run_pending()
            except KeyboardInterrupt:
                logger.info("Program leállítva.")
                break
            except Exception as e:
                # A ciklus semmilyen váratlan hibától ne álljon meg.
                logger.exception("Hiba történt a fő ciklusban: %s", e)
                time.sleep(5)

            time.sleep(1)

    try:
        mt.disconnect()
    except Exception as e:
        logger.error("Lecsatlakozás sikertelen: %s", e)
