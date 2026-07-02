import time
import tomllib

import mt_lib
import vesz_lib


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
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")


def job():

    try:
        news = feeds.getNews()
    except Exception as e:
        print(f"Hírek lekérése sikertelen: {e}")
        return

    print(f"Új hírek száma: {len(news)}")
    delay = cfg("meshtastic.time_between_messages_s")
    for idx, i in enumerate(news):
        if idx > 0:
            time.sleep(delay)  # szünet CSAK a hírek között, az utolsó után nem
        print("Sending news: ", repr(i))
        try:
            mt.sendMessage(i)
        except Exception as e:
            print(f"Hír küldése sikertelen: {e}")






if __name__ == "__main__":
    mt = build_handler()

    feeds = vesz_lib.BMFeeds(
        rss_url=cfg("vesz.rss_url"),
        postfix_text=cfg("vesz.postfix_text"),
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
                print("Program leállítva.")
                break
            except Exception as e:
                # A ciklus semmilyen váratlan hibától ne álljon meg.
                print(f"Hiba történt a fő ciklusban: {e}")
                time.sleep(5)

            time.sleep(1)

    try:
        mt.disconnect()
    except Exception as e:
        print(f"Lecsatlakozás sikertelen: {e}")
