# mt_vesz — Veszélyhelyzeti információs rendszer Meshtastic hálózaton

A szkript a [BM OKF](https://www.katasztrofavedelem.hu) (Belügyminisztérium Országos
Katasztrófavédelmi Főigazgatóság) veszélyhelyzeti RSS-hírcsatornáját figyeli, és az új
híreket egy [Meshtastic](https://meshtastic.org) rádión keresztül, egy dedikált csatornán
szétküldi a mesh hálózaton. Így internet nélküli területeken is elérhetők a hivatalos
riasztások.

## Hogyan működik

A vészhelyzeti csatornát **egyszer**, a `setup_channel.py` scripttel állítod be a
node-on (lásd lentebb). A rutin hírküldés (`main.py`) ezután:

1. Csatlakozik a Meshtastic node-hoz (TCP-n vagy soros porton).
2. Letölti az RSS-hírfolyamot, és a már látott híreket egy `cache.json`-ban tárolja.
3. Az új híreket egyenként kiküldi a hálózatra, beállított szünettel a küldések között.
4. (Folyamatos módban) beállított időközönként ismétli a hírlekérést.

A `main.py` szándékosan **nem** írja újra a csatorna-konfigurációt minden futáskor –
így cron-módban sem terheli feleslegesen a node flash-memóriáját.

A node kapcsolat megszakadását automatikusan kezeli: a könyvtár exponenciális
visszalépéssel (backoff) újrapróbálkozik (a próbák számát a `connect_max_retries`
korlátozza).

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

[log]
file = "mt_vesz.log"                  # a logfájl neve/útvonala
max_size_kb = 1024                    # ekkora méretnél (KB) új fájlba forgat – méretkorlát
backup_count = 3                      # ennyi régi (forgatott) logfájlt tart meg

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

### `[log]` szekció

A program a sikeresen kiküldött rádiós üzeneteket és minden hibát naplózza –
konzolra és egy **méretkorlátos** logfájlba egyaránt. A fájl a `max_size_kb`
méret elérésekor új fájlba forgat, és legfeljebb `backup_count` régi fájlt tart
meg (`mt_vesz.log.1`, `.2` …), így a naplók nem nőnek korlátlanul.

| Kulcs | Leírás |
|---|---|
| `file` | A logfájl neve/útvonala. |
| `max_size_kb` | A logfájl mérete ekkora értéknél (KB) új fájlba forgat. |
| `backup_count` | Ennyi régi (forgatott) logfájlt tart meg. A lemezhasználat felső korlátja nagyjából `(backup_count + 1) * max_size_kb` KB. |

### `[vesz]` szekció

| Kulcs | Leírás |
|---|---|
| `rss_url` | A figyelt RSS-hírcsatorna URL-je. |
| `rss_read_time_min` | Milyen gyakran (percben) kérdezze le újra a hírfolyamot. |
| `postfix_text` | Minden kiküldött hír végéhez hozzáfűzött szöveg. |
| `cache_max_entries` | Ha a `cache.json` ennél több bejegyzésre nő, új hír érkezésekor automatikusan lefut a takarítás. `0` = kikapcsolva (korlátlan növekedés). |
| `cache_clear_time_days` | Takarításkor az ennél régebbi (napban) bejegyzések törlődnek a cache-ből. |

> **Megjegyzés a csatornáról:** a `setup_channel.py` a kiválasztott csatornát a
> `psk='AQ=='` (alapértelmezett, nyilvános kulcs), `uplink_enabled=False`,
> `downlink_enabled=True` beállításokkal hozza létre. Ha titkosított, zárt csatornát
> szeretnél, módosítsd a `psk` értékét a `setup_channel.py`-ben.

## Használat

### 1. Csatorna beállítása (egyszeri)

A `config.toml` kitöltése után **egyszer** futtasd le a csatorna-beállítót. Ez
létrehozza/beállítja a vészhelyzeti csatornát a node-on, majd kilép:

```bash
python setup_channel.py
```

Ezt csak akkor kell újrafuttatni, ha a csatorna beállításait (`[meshtastic]`
szekció: index, név) módosítod.

### 2. Hírküldés

```bash
python main.py
```

A program minden esetben:

1. Csatlakozik a node-hoz (a csatornát nem állítja – azt a `setup_channel.py` tette meg).
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
*/10 * * * * cd $HOME/mt_vesz && $HOME/mt_vesz/venv/bin/python main.py >> $HOME/mt_vesz/cron.log 2>&1
```

Magyarázat:

- `*/10 * * * *` — minden 10. percben. (`*/30` = félóránként, `0 * * * *` = óránként.)
- `cd $HOME/mt_vesz` — a projekt könyvtára, hogy a relatív útvonalú fájlok (`config.toml`,
  `cache.json`) elérhetők legyenek. A `$HOME`-ot a cron a futtató felhasználó saját
  könyvtárára állítja, így nem kell beégetni a felhasználónevet (feltéve, hogy a projekt
  a home könyvtárban van; ha máshol, írj abszolút útvonalat).
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

#### Napi életjel (heartbeat.py)

A `heartbeat.py` naponta egyszer egyetlen üzenetet küld, ami azt mutatja, hogy az
eszköz működik – így a csatorna hallgatói akkor is látják, hogy a rendszer él, ha
éppen nincs új VESZ-hír. Az üzenet szövegét a `config.toml` `[heartbeat]` szekciója
adja (a `{time}` helyére a küldés ideje kerül).

Éjfélkori (napi) futtatáshoz add hozzá ezt a sort is a crontabhoz:

```cron
0 0 * * * cd $HOME/mt_vesz && $HOME/mt_vesz/venv/bin/python heartbeat.py >> $HOME/mt_vesz/cron.log 2>&1
```

- `0 0 * * *` — minden nap 0 óra 0 perckor (éjfél).
- A többi tag jelentése azonos a fenti `main.py` sorával.

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
| `setup_channel.py` | A vészhelyzeti csatorna egyszeri beállítása a node-on. |
| `list_ports.py` | Elérhető soros (USB) portok listázása (Linux/Windows). |
| `mt_lib.py` | Meshtastic kapcsolatkezelés (TCP/soros), újracsatlakozás, üzenetküldés ACK-kal. |
| `vesz_lib.py` | RSS-letöltés és cache-kezelés (`BMFeeds` osztály). |
| `log_setup.py` | A méretkorlátos, forgó logfájl + konzol naplózás beállítása. |
| `config.toml` | Konfiguráció. |
| `cache.json` | A már látott hírek (futás közben jön létre). |
| `mt_vesz.log` | Napló: sikeres küldések és hibák (futás közben jön létre, méretkorlátos). |

## Hibaelhárítás

- **Nem csatlakozik a node-hoz:** ellenőrizd a `connect_mode`-ot és a `host`/`port`
  értéket. TCP módban a node-nak elérhetőnek kell lennie a hálózaton (a Meshtastic
  WiFi/eszköz IP-jén). A `connect()` automatikusan újrapróbálkozik, így a kapcsolódás
  blokkol, amíg sikerül.
- **Nem mennek ki hírek, „Töröld a cache.json-t!”:** minden aktuális hír már a cache-ben
  van. Töröld a `cache.json`-t, ha újra ki akarod küldeni őket. A main.py újraindítása szükséges!
- **Hír nem lett kézbesítve (nincs ACK):** a node valószínűleg egyedül van, vagy nincs
  vétel. A program ilyenkor a következő hírre lép.
