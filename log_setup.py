"""Központi naplózás beállítása: méretkorlátos, forgó logfájl + konzol.

A modulok a szokásos ``logging.getLogger(__name__)`` loggereken keresztül
naplóznak; a tényleges kimenetet (fájl + konzol) egyszer, itt konfiguráljuk a
gyökér loggeren.
"""

import logging
from logging.handlers import RotatingFileHandler


def setup_logging(log_file="mt_vesz.log", max_size_kb=1024, backup_count=3,
                  level=logging.INFO):
    """Beállítja a gyökér loggert: forgó (méretkorlátos) fájl + konzol.

    A logfájl mérete korlátos: amikor eléri a ``max_size_kb`` kilobájtot, a
    logging egy új fájlba forgat, és legfeljebb ``backup_count`` régi fájlt tart
    meg (``mt_vesz.log.1``, ``.2`` …). A lemezhasználat felső korlátja így
    nagyjából ``(backup_count + 1) * max_size_kb`` kilobájt.

    Ha a logfájl nem nyitható meg (pl. jogosultsági/lemez hiba), nem állítjuk le
    a programot – csak konzolra naplózunk, és jelezzük az okot.
    """
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Ismételt hívásnál (pl. setup_channel + main együtt) ne duplikálódjanak
    # a handlerek.
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max(0, int(max_size_kb)) * 1024,
            backupCount=max(0, int(backup_count)),
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as e:
        root.error("A logfájl nem nyitható meg (%s): %s – csak konzolra naplózunk.",
                   log_file, e)

    return root
