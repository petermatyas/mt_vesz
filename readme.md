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
- `schedule` — beépített időzített futtatás
- `pyserial` — soros portok listázása (`list_ports.py`) és soros kapcsolat

## Konfiguráció

Minden beállítás a `config.toml` fájlban található.

```toml
[general]
use_scheduler = false                 # true: beépített időzítővel folyamatosan fut; false: egyszer lefut és kilép

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

### `[general]` szekció

| Kulcs | Leírás |
|---|---|
| `use_scheduler` | `true` esetén a program a beépített időzítővel folyamatosan fut (`rss_read_time_min` percenként). `false` esetén egyszer lefut (kapcsolódás → hírküldés → kilépés), így külső időzítővel (pl. crontab) hívható. |

### `[meshtastic]` szekció

| Kulcs | Leírás |
|---|---|
| `connect_mode` | `"TCP"` hálózati node-hoz, `"serial"` USB-n csatlakoztatott eszközhöz. |
| `host` | A node IP-címe vagy hostneve TCP módban. |
| `port` | A soros eszköz elérési útja (`serial` módban), pl. `/dev/ttyUSB0` Linuxon vagy `COM3` Windowson. TCP módban hagyd kikommentelve. |
| `emergency_channel_number` | A módosítandó csatorna indexe. `0` a primary csatorna, `1`–`7` a secondary csatornák. |
| `emergency_channel_name` | A vészhelyzeti csatorna neve. |
| `time_between_messages_s` | Várakozás másodpercben két hír kiküldése között (a mesh hálózat tehermentesítésére). |
| `connect_max_retries` | Hány csatlakozási próba után adja fel a program, ha a node nem elérhető. `0` = végtelen újrapróbálkozás (folyamatos/daemon módhoz). Egyszeri/cron módban **állítsd véges értékre** (pl. `10`), különben a node kiesésekor a folyamat végtelenségig lóg, és a cron újabb beragadt folyamatokat halmozna fel. |

### `[vesz]` szekció

| Kulcs | Leírás |
|---|---|
| `rss_url` | A figyelt RSS-hírcsatorna URL-je. |
| `rss_read_time_min` | Milyen gyakran (percben) kérdezze le újra a hírfolyamot. |
| `postfix_text` | Minden kiküldött hír végéhez hozzáfűzött szöveg. |
| `cache_max_entries` | Ha a `cache.json` ennél több bejegyzésre nő, új hír érkezésekor automatikusan lefut a takarítás. `0` = kikapcsolva (korlátlan növekedés). |
| `cache_clear_time_days` | Takarításkor az ennél régebbi (napban) bejegyzések törlődnek a cache-ből. |

> **Megjegyzés a csatornáról:** a szkript a kiválasztott csatornát a `psk='AQ=='`
> (alapértelmezett, nyilvános kulcs), `uplink_enabled=False`, `downlink_enabled=True`
> beállításokkal hozza létre. Ha titkosított, zárt csatornát szeretnél, módosítsd a
> `psk` értékét a `main.py` `init()` függvényében.

## Használat

A konfiguráció kitöltése után:

```bash
python main.py
```

A program minden esetben:

1. Csatlakozik a node-hoz, és beállítja a vészhelyzeti csatornát.
2. Lefuttat egy hírlekérést és -küldést.

Ezután a `[general] use_scheduler` értékétől függően:

- **`use_scheduler = true`** (folyamatos mód): `rss_read_time_min` percenként ismétli a
  lekérést, amíg le nem állítod (`Ctrl+C`). Ekkor a `schedule` csomag szükséges.
- **`use_scheduler = false`** (egyszeri mód): a hírküldés után a program szabályosan
  lecsatlakozik a node-ról és kilép. Az ismétlésről ilyenkor egy külső időzítő
  (crontab, systemd timer, Windows Feladatütemező) gondoskodik — lásd lentebb.

Leállításkor / kilépéskor a program szabályosan lecsatlakozik a node-ról.

### Soros portok felderítése

Soros (USB) kapcsolat esetén a megfelelő port neve a `list_ports.py` scripttel deríthető
fel — Linuxon és Windowson egyaránt:

```bash
python list_ports.py
```

A talált eszköz nevét (pl. `/dev/ttyUSB0` vagy `COM3`) írd be a `config.toml`
`[meshtastic] port` kulcsához.

## Ütemezett futtatás külső időzítővel

Ha a `[general] use_scheduler = false`, a `main.py` egyszer fut le és kilép, így külső
időzítővel ütemezhető. Ez robusztusabb, mint a beépített időzítő, mert minden futás
friss folyamatban, tiszta node-kapcsolattal indul.

### Linux — crontab

Nyisd meg a crontab szerkesztőt:

```bash
crontab -e
```

Add hozzá a következő sort (10 percenkénti futtatás, a projekt saját virtuális
környezetével). A crontab nem ismeri a `cd`-t, ezért abszolút útvonalakat használj, és
lépj a projekt könyvtárába, hogy a `config.toml` és a `cache.json` megtalálható legyen:

```cron
*/10 * * * * cd /home/pi/mt_vesz && /home/pi/mt_vesz/venv/bin/python main.py >> /home/pi/mt_vesz/cron.log 2>&1
```

Magyarázat:

- `*/10 * * * *` — minden 10. percben. (`*/30` = félóránként, `0 * * * *` = óránként.)
- `cd /home/pi/mt_vesz` — a projekt könyvtára, hogy a relatív útvonalú fájlok (`config.toml`,
  `cache.json`) elérhetők legyenek.
- `venv/bin/python main.py` — a virtuális környezet Pythonja (a cron környezetében nincs
  aktivált venv, ezért kell a teljes útvonal).
- `>> cron.log 2>&1` — a kimenet és a hibák naplózása (hasznos hibakereséshez).

Ellenőrzés:

```bash
crontab -l          # a beállított feladatok listája
tail -f cron.log    # a futások élő naplója
```

> **Fontos:** két futás ne fusson egyszerre (a node egyszerre egy kapcsolatot kezel jól).
> Válaszd a `*/10` intervallumot elég nagyra ahhoz, hogy egy futás (kapcsolódás +
> összes hír kiküldése `time_between_messages_s` szünetekkel) biztosan befejeződjön.

### Windows — Feladatütemező

Egyszeri módban Windowson a Feladatütemezővel (Task Scheduler) ütemezhető:

```powershell
schtasks /Create /TN "mt_vesz" /TR "cmd /c cd /d E:\mt_vesz && E:\mt_vesz\venv\Scripts\python.exe main.py >> E:\mt_vesz\cron.log 2>&1" /SC MINUTE /MO 10
```

- `/SC MINUTE /MO 10` — 10 percenként. (`/SC HOURLY` = óránként.)
- A feladat törlése: `schtasks /Delete /TN "mt_vesz" /F`.

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
| `list_ports.py` | Elérhető soros (USB) portok listázása (Linux/Windows). |
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
