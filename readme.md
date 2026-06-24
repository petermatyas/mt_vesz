# mt_vesz — Veszélyhelyzeti információs rendszer Meshtastic hálózaton

A szkript a [BM OKF](https://www.katasztrofavedelem.hu) (Belügyminisztérium Országos
Katasztrófavédelmi Főigazgatóság) veszélyhelyzeti RSS-hírcsatornáját figyeli, és az új
híreket egy [Meshtastic](https://meshtastic.org) rádión keresztül, egy dedikált csatornán
szétküldi a mesh hálózaton. Így internet nélküli területeken is elérhetők a hivatalos
riasztások.

## Hogyan működik

1. Csatlakozik a Meshtastic node-hoz (TCP-n vagy soros porton).
2. Beállít egy vészhelyzeti csatornát. 
3. Indító üzenetet küld a csatornára.
4. Letölti az RSS-hírfolyamot, és a már látott híreket egy `cache.json`-ban tárolja.
5. Az új híreket egyenként kiküldi a hálózatra, beállított szünettel a küldések között.
6. Beállított időközönként ismétli a hírlekérést.

A node kapcsolat megszakadását automatikusan kezeli: a könyvtár exponenciális
visszalépéssel (backoff) újrapróbálkozik, az üzenetküldés pedig opcionálisan ACK-ig
újraküldhető (lásd `mt_lib.py`).

## Telepítés

Python 3.11+ szükséges.

```bash
# Virtuális környezet (ajánlott)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Függőségek
pip install -r requirements.txt
```

Függőségek (`requirements.txt`):

- `meshtastic[cli]` — kommunikáció a Meshtastic node-dal
- `feedparser` — RSS feldolgozás
- `schedule` — időzített futtatás

## Konfiguráció

Minden beállítás a `config.toml` fájlban található.

```toml
[meshtastic]
connect_mode = "TCP"                  # "TCP" vagy "serial"
host = "192.168.0.182"                # TCP kapcsolat esetén a node IP-címe
#port = "/dev/ttyUSB0"                # soros kapcsolat esetén a port
emergency_channel_number = 1          # a vészhelyzeti csatorna indexe (0 = primary)
emergency_channel_name = "vesz_teszt" # a csatorna neve
time_between_messages_s = 30          # szünet (mp) az egyes hírek küldése között

[vesz]
rss_url = "https://www.katasztrofavedelem.hu/10466/RSS_VESZ"
rss_read_time_min = 10                # hírlekérés gyakorisága (perc)
postfix_text = "hírforrás: BM OKF"    # minden hír végére fűzött szöveg
```

### `[meshtastic]` szekció

| Kulcs | Leírás |
|---|---|
| `connect_mode` | `"TCP"` hálózati node-hoz, `"serial"` USB-n csatlakoztatott eszközhöz. |
| `host` | A node IP-címe vagy hostneve TCP módban. |
| `port` | A soros eszköz elérési útja (`serial` módban), pl. `/dev/ttyUSB0` Linuxon vagy `COM3` Windowson. TCP módban hagyd kikommentelve. |
| `emergency_channel_number` | A módosítandó csatorna indexe. `0` a primary csatorna, `1`–`7` a secondary csatornák. |
| `emergency_channel_name` | A vészhelyzeti csatorna neve. |
| `time_between_messages_s` | Várakozás másodpercben két hír kiküldése között (a mesh hálózat tehermentesítésére). |

### `[vesz]` szekció

| Kulcs | Leírás |
|---|---|
| `rss_url` | A figyelt RSS-hírcsatorna URL-je. |
| `rss_read_time_min` | Milyen gyakran (percben) kérdezze le újra a hírfolyamot. |
| `postfix_text` | Minden kiküldött hír végéhez hozzáfűzött szöveg. |

> **Megjegyzés a csatornáról:** a szkript a kiválasztott csatornát a `psk='AQ=='`
> (alapértelmezett, nyilvános kulcs), `uplink_enabled=False`, `downlink_enabled=True`
> beállításokkal hozza létre. Ha titkosított, zárt csatornát szeretnél, módosítsd a
> `psk` értékét a `main.py` `init()` függvényében.

## Használat

A konfiguráció kitöltése után:

```bash
python main.py
```

A program:

1. Csatlakozik a node-hoz, és beállítja a vészhelyzeti csatornát.
2. Azonnal lefuttat egy első hírlekérést és -küldést.
3. Ezután `rss_read_time_min` percenként ismétli a lekérést, amíg le nem állítod
   (`Ctrl+C`).

Leállításkor a program szabályosan lecsatlakozik a node-ról.

## Cache

A már feldolgozott hírek a `cache.json` fájlba kerülnek (link és időbélyeg alapján),
hogy ugyanaz a hír ne menjen ki kétszer. A fájl a `.gitignore`-ban szerepel.

- Ha **újra szeretnéd küldeni** az összes aktuális hírt, töröld a `cache.json`-t.
- A `BMFeeds.clear_cache(clear_time_s)` metódussal megadott kornál régebbi
  bejegyzések törölhetők a cache-ből.

## Fájlok

| Fájl | Szerep |
|---|---|
| `main.py` | Belépési pont: kapcsolódás, ütemezés, hírküldés. |
| `mt_lib.py` | Meshtastic kapcsolatkezelés (TCP/soros), újracsatlakozás, üzenetküldés ACK-kal. |
| `vesz_lib.py` | RSS-letöltés és cache-kezelés (`BMFeeds` osztály). |
| `config.toml` | Konfiguráció. |
| `cache.json` | A már látott hírek (futás közben jön létre). |

## Hibaelhárítás

- **Nem csatlakozik a node-hoz:** ellenőrizd a `connect_mode`-ot és a `host`/`port`
  értéket. TCP módban a node-nak elérhetőnek kell lennie a hálózaton (a Meshtastic
  WiFi/eszköz IP-jén). A `connect()` automatikusan újrapróbálkozik, így a kapcsolódás
  blokkol, amíg sikerül.
- **Nem mennek ki hírek, „Töröld a cache.json-t!”:** minden aktuális hír már a cache-ben
  van. Töröld a `cache.json`-t, ha újra ki akarod küldeni őket. A main.py újraindítása szükséges!
- **Hír nem lett kézbesítve (nincs ACK):** a node valószínűleg egyedül van, vagy nincs
  vétel. A program ilyenkor a következő hírre lép.
