import logging
import sys
import time

import log_setup
import mt_lib
import rak_hat
import vesz_lib
# A config betöltése az app_config modulban történik; a cfg / config / CONFIG_FILE
# nevek innen is elérhetők maradnak (a heartbeat.py, setup_channel.py,
# read_messages.py a main-ből importálja őket).
from app_config import CONFIG_FILE, cfg, config  # noqa: F401


logger = logging.getLogger(__name__)


# A naplózást a config betöltése után, minden más előtt beállítjuk, hogy a
# sikeres rádiós üzenetek és minden hiba méretkorlátos logfájlba is kerüljön.
log_setup.setup_logging(
    log_file=cfg("log.file", "mt_vesz.log"),
    max_size_kb=cfg("log.max_size_kb", 1024),
    backup_count=cfg("log.backup_count", 3),
)


def check_rak_hat_setup():
    """rak_hat módban ellenőrzi a [rak_hat] beállításokat és a meshtasticd
    rádió-presetjét. Hibás config esetén kilép; eltérés esetén csak figyelmeztet
    (a csatlakozást nem akadályozza meg)."""
    try:
        filename = rak_hat.preset_filename(
            lora_module=cfg("rak_hat.lora_module", "auto"),
            slot=cfg("rak_hat.slot", 1),
            preset_file=cfg("rak_hat.preset_file", ""),
        )
    except rak_hat.RakHatConfigError as e:
        raise SystemExit(f"Hiba a {CONFIG_FILE} [rak_hat] szekciójában: {e}")

    if not cfg("rak_hat.check_preset", True) or not sys.platform.startswith("linux"):
        return
    base_dir = cfg("rak_hat.meshtasticd_dir", rak_hat.DEFAULT_MESHTASTICD_DIR)
    for problem in rak_hat.check_preset(filename, base_dir):
        logger.warning("RAK HAT: %s Javítás: sudo venv/bin/python setup_rak_hat.py", problem)


def build_handler():
    """A configból létrehozza a megfelelő Meshtastic handlert (TCP / serial / rak_hat).

    A csatlakozás még nem történik meg – azt a hívó ``mt.connect()``-tel indítja."""
    connect_mode = cfg("meshtastic.connect_mode").lower()
    # 0 (vagy hiányzó) => végtelen újrapróbálkozás; >0 => ennyi próba után feladja.
    max_retries = cfg("meshtastic.connect_max_retries", 0) or None
    if connect_mode == "tcp":
        return mt_lib.MtTcpHandler(
            host=cfg("meshtastic.host"),
            tcp_port=cfg("meshtastic.tcp_port", mt_lib.DEFAULT_TCP_PORT),
            max_retries=max_retries,
        )
    elif connect_mode == "serial":
        return mt_lib.MtSerialHandler(port=cfg("meshtastic.port"), max_retries=max_retries)
    elif connect_mode == "rak_hat":
        check_rak_hat_setup()
        return mt_lib.MtRakHatHandler(
            host=cfg("rak_hat.host", rak_hat.DEFAULT_HOST),
            tcp_port=cfg("rak_hat.tcp_port", rak_hat.DEFAULT_TCP_PORT),
            max_retries=max_retries,
        )
    raise SystemExit("Hiba: érvénytelen connect_mode a config fájlban (TCP / serial / rak_hat).")


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
    hop_limit = cfg("meshtastic.hop_limit", 3)
    for idx, i in enumerate(news):
        if idx > 0:
            time.sleep(delay)  # szünet CSAK a hírek között, az utolsó után nem
        logger.info("Hír küldése: %r", i)
        try:
            mt.sendMessage(i, hopLimit=hop_limit, want_ack=want_ack, ack_timeout_s=ack_timeout_s,
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
        include_link=cfg("vesz.include_link", False),
        url_shortener=cfg("vesz.url_shortener", "is.gd"),
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
