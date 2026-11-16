# mt_vesz — Veszélyhelyzeti információs rendszer Meshtastic hálózaton

A szkript a [BM OKF](https://www.katasztrofavedelem.hu) (Belügyminisztérium Országos
Katasztrófavédelmi Főigazgatóság) veszélyhelyzeti RSS-hírcsatornáját figyeli, és az új
híreket egy [Meshtastic](https://meshtastic.org) rádión keresztül, egy dedikált csatornán
szétküldi a mesh hálózaton. Így internet nélküli területeken is elérhetők a hivatalos
riasztások.

## Hogyan működik

A vészhelyzeti csatornát **egyszer**, a `setup_channel.py` scripttel állítod be a
node-on (lásd lentebb). A rutin hírküldés (`main.py`) ezután:

1. Csatlakozik a Meshtastic node-hoz (TCP-n, soros porton, vagy Raspberry Pi-n a
   RAK6421 HAT-ot kezelő `meshtasticd`-hez – lásd [Kapcsolódási módok](#kapcsolódási-módok)).
2. Letölti az RSS-hírfolyamot, és a már látott híreket egy `cache.json`-ban tárolja.
3. Az új híreket egyenként kiküldi a hálózatra, beállított szünettel a küldések között.
4. (Folyamatos módban) beállított időközönként ismétli a hírlekérést.

A `main.py` szándékosan **nem** írja újra a csatorna-konfigurációt minden futáskor –
így cron-módban sem terheli feleslegesen a node flash-memóriáját.

A node kapcsolat megszakadását automatikusan kezeli: a könyvtár exponenciális
visszalépéssel (backoff) újrapróbálkozik (a próbák számát a `connect_max_retries`
korlátozza).

## Kapcsolódási módok

A program a `meshtastic` Python könyvtáron keresztül egy Meshtastic node API-jával
beszél. A node háromféleképpen érhető el (`config.toml` → `[meshtastic] connect_mode`):

| `connect_mode` | Hardver | Kapcsolat |
|---|---|---|
| `"serial"` | USB-n csatlakoztatott Meshtastic eszköz (saját firmware-rel) | soros port (`/dev/ttyUSB0`, `COM3` …) |
| `"TCP"` | WiFi/Ethernet-es Meshtastic node a hálózaton | TCP, `host:tcp_port` (alapból 4403) |
| `"rak_hat"` | Raspberry Pi 5 + **RAK6421 WisMesh Pi HAT** + **RAK13300** (vagy RAK13302) LoRa modul | TCP a gépen belül a `meshtasticd`-hez (`127.0.0.1:4403`) |

**Hogyan működik a `rak_hat` mód?** A RAK13300 modul (SX1262 chip) önmagában csak egy
rádió, nem Meshtastic node. A Meshtastic protokollt (titkosítás, mesh routing, nyugták)
a Pi-n futó **`meshtasticd`** szolgáltatás valósítja meg – ez a Meshtastic firmware
Linux-os változata. SPI buszon vezérli a rádiót, és ugyanazt az API-t nyújtja TCP-n,
mint egy hálózati node:

```
main.py → meshtastic lib → TCP 127.0.0.1:4403 → meshtasticd → SPI → RAK13300 → LoRa
```

Ezért a program összes funkciója (hírküldés, nyugták, életjel, tárolt üzenetek
kiolvasása, csatorna-beállítás) változatlanul működik, és a Python függőségek sem
változnak. A `rak_hat` mód a TCP módhoz képest annyit tud többet, hogy a
`[rak_hat]` szekcióban megadható, melyik LoRa modult (és melyik slotban) használja
a meshtasticd, ezt a `setup_rak_hat.py` beállítja, a program pedig induláskor ellenőrzi.

## Telepítés

Python 3.11+ szükséges. Raspberry Pi + RAK6421 HAT esetén a teljes, lépésenkénti
leírás lentebb található: [Telepítés Raspberry Pi 5 + RAK6421 HAT-ra](#telepítés-raspberry-pi-5--rak6421-hat-ra-lépésről-lépésre).

### Általános telepítés (Windows / Linux, USB-s vagy TCP-s node)

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

Ezután másold le a mintakonfigurációt, és töltsd ki (lásd [Konfiguráció](#konfiguráció)):

```bash
cp sample_config.toml config.toml
```

### Telepítés Raspberry Pi 5 + RAK6421 HAT-ra (lépésről lépésre)

Szükséges hardver:

- Raspberry Pi 5 (Pi 4 is működik) hivatalos 5 V / 5 A tápegységgel, microSD kártyával
- RAK6421 WisMesh Pi HAT
- RAK13300 LoRa modul (vagy RAK13302, 1 W-os változat)
- 868 MHz-es LoRa antenna (EU)

> A RAKwireless kínál előre telepített meshtasticd-s Pi image-et is
> ([meshtastic-rak6421-guide](https://github.com/RAKWireless/meshtastic-rak6421-guide)).
> Az alábbi lépések a sima Raspberry Pi OS-re telepítést írják le; a RAK image
> esetén a 3–5. lépés már készen van, a 6. lépéstől folytasd.

#### 1. A hardver összeszerelése

1. A RAK13300 modult tedd a HAT **IO slot 1**-ébe (ha a slot 2-be teszed, a
   `config.toml`-ban `slot = 2` kell majd).
2. Csatlakoztasd a LoRa antennát a modul antenna-csatlakozójára.
   > **Fontos:** antenna nélkül soha ne kapcsold be az eszközt – az adó
   > tönkreteheti a rádiós chipet.
3. Kikapcsolt állapotban dugd a HAT-ot a Pi 40 tűs GPIO csatlakozójára.

#### 2. Az operációs rendszer telepítése

1. A [Raspberry Pi Imager](https://www.raspberrypi.com/software/) programmal írd fel a
   **Raspberry Pi OS (64-bit)** (Lite elég) image-et az SD kártyára.
2. Az Imager beállításainál (fogaskerék / „Edit settings”) add meg: hostnév,
   felhasználó (a leírás `pi`-t feltételez), WiFi, időzóna, és kapcsold be az SSH-t.
3. Indítsd el a Pi-t, és lépj be SSH-n: `ssh pi@<hostnév>.local`
4. Frissítsd a rendszert, és telepítsd a szükséges csomagokat:

   ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y git python3-venv python3-pip curl gpg
   ```

#### 3. Az SPI és I2C busz bekapcsolása

A rádió SPI-n, a HAT azonosító EEPROM-ja I2C-n kommunikál.

```bash
sudo raspi-config nonint do_spi 0     # SPI bekapcsolása (0 = bekapcsolva)
sudo raspi-config nonint do_i2c 0     # I2C bekapcsolása
```

A HAT EEPROM-jának (automatikus hardverfelismerés) olvasásához add hozzá a
`/boot/firmware/config.txt` végéhez:

```bash
sudo nano /boot/firmware/config.txt
```

```ini
# Enable I2C-0 bus for HAT EEPROM
dtparam=i2c_vc=on
dtoverlay=i2c0
```

Indítsd újra: `sudo reboot`. Ellenőrzés újraindítás után: `ls /dev/spidev* /dev/i2c-*`
– látszania kell a `/dev/spidev0.0` eszköznek.

#### 4. A meshtasticd telepítése

A meshtasticd a Meshtastic hivatalos csomagtárából telepíthető
([leírás](https://meshtastic.org/docs/meshtasticd/installation/debian/)). Először
nézd meg a Debian verziót:

```bash
grep VERSION_CODENAME /etc/os-release    # bookworm = Debian 12, trixie = Debian 13
```

Bookworm esetén (trixie-n a `Debian_12` helyett `Debian_13`-at írj mindkét sorba):

```bash
echo 'deb http://download.opensuse.org/repositories/network:/Meshtastic:/beta/Debian_12/ /' | sudo tee /etc/apt/sources.list.d/network:Meshtastic:beta.list
curl -fsSL https://download.opensuse.org/repositories/network:Meshtastic:beta/Debian_12/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/network_Meshtastic_beta.gpg > /dev/null
sudo apt update
sudo apt install -y meshtasticd
```

> A 64 bites Raspberry Pi OS-hez a **Debian** csomagtárat kell használni (a
> `Raspbian_*` tár csak a 32 bites rendszerhez való).

A telepítés után létrejön az `/etc/meshtasticd/` könyvtár:

| Útvonal | Tartalom |
|---|---|
| `/etc/meshtasticd/config.yaml` | a meshtasticd fő konfigurációja |
| `/etc/meshtasticd/available.d/` | a gyártott hardverekhez tartozó kész presetek (pl. `lora-RAK6421-13300-slot1.yaml`) |
| `/etc/meshtasticd/config.d/` | az **aktív** kiegészítő beállítások – ide kerül a rádió presetje |

#### 5. A meshtasticd alapbeállítása (`config.yaml`)

```bash
sudo nano /etc/meshtasticd/config.yaml
```

Keresd meg és (ha ki van kommentelve) kapcsold be az alábbi kulcsokat:

```yaml
I2C:
  I2CDevice: /dev/i2c-1

Webserver:
  Port: 9443          # opcionális: webes felület https://<Pi-IP>:9443

General:
  MACAddressSource: eth0   # a node ID ebből a hálózati kártyából képződik – így stabil marad
```

> A `Lora:` szekciót itt **ne** állítsd – azt a 8. lépésben a `setup_rak_hat.py`
> a `config.d`-be tett presettel intézi.

Kapcsold be a szolgáltatás automatikus indulását:

```bash
sudo systemctl enable meshtasticd
```

#### 6. A projekt letöltése és a Python környezet

```bash
cd ~
git clone <a projekt git URL-je> mt_vesz     # vagy másold fel a fájlokat (scp / USB)
cd ~/mt_vesz
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 7. A `config.toml` kitöltése

```bash
cp sample_config.toml config.toml
nano config.toml
```

A RAK HAT-hoz szükséges kulcsok (a többit lásd a [Konfiguráció](#konfiguráció) fejezetben):

```toml
[meshtastic]
connect_mode = "rak_hat"
lora_region = "EU_868"        # új node-on kötelező!

[rak_hat]
lora_module = "RAK13300"      # vagy "RAK13302", vagy "auto"
slot = 1                      # ahova az 1. lépésben a modult tetted
host = "127.0.0.1"
tcp_port = 4403
```

#### 8. A rádió-preset beállítása (`setup_rak_hat.py`)

A script a `[rak_hat]` beállítás alapján a megfelelő presetet bemásolja az
`available.d`-ből a `config.d`-be (a `config.d`-ben lévő többi lora presetet
áthelyezi a `/etc/meshtasticd/config.d.disabled-by-mt_vesz/` könyvtárba – nem törli),
majd újraindítja a meshtasticd-t. Root jog kell hozzá:

```bash
sudo venv/bin/python setup_rak_hat.py
```

| `lora_module` / `slot` | Aktivált preset |
|---|---|
| `"RAK13300"`, `slot = 1` | `lora-RAK6421-13300-slot1.yaml` |
| `"RAK13300"`, `slot = 2` | `lora-RAK6421-13300-slot2.yaml` |
| `"RAK13302"`, `slot = 1` / `2` | `lora-RAK6421-13302-slot1.yaml` / `-slot2.yaml` |
| `"auto"` | nincs preset – a meshtasticd a HAT EEPROM-ja alapján ismeri fel a hardvert (a 3. lépés `config.txt` sorai szükségesek) |
| `preset_file = "…yaml"` | a megadott `available.d`-beli fájl (ha a csomagban más néven szerepel) |

Ha a kért preset nincs az `available.d`-ben, a script kiírja, milyen RAK6421
presetek érhetők el – ilyenkor a `preset_file` kulccsal add meg a pontos nevet.

Csak ellenőrzés, módosítás nélkül (root sem kell):

```bash
venv/bin/python setup_rak_hat.py --check
```

#### 9. A meshtasticd ellenőrzése

```bash
systemctl status meshtasticd           # "active (running)" legyen
journalctl -u meshtasticd -n 50        # a naplóban a rádió (SX1262) sikeres indulása látszik
venv/bin/meshtastic --host 127.0.0.1 --info
```

Az utolsó parancs a node adatait (owner, node ID, csatornák, `lora.region`)
listázza – ha válaszol, a program is tud csatlakozni.

#### 10. A régi node beállításainak átvétele (opcionális)

Ha eddig USB-s eszközzel ment a rendszer, a beállításai átvihetők:

```bash
# a régi eszközről (amikor még USB-n csatlakozik):
venv/bin/meshtastic --port /dev/ttyUSB0 --export-config > old_node.yaml
# az új (RAK HAT-os) node-ra:
venv/bin/meshtastic --host 127.0.0.1 --configure old_node.yaml
```

> Az új node **új node ID-t** kap (más a hardver), a hálózat hallgatói új node-ként látják.

#### 11. Csatorna és régió beállítása

```bash
venv/bin/python setup_channel.py
```

Beállítja a vészhelyzeti csatornát, a NodeInfo-időközt, és – ha a
`lora_region` meg van adva és eltér – a LoRa régiót. **Régió nélkül a rádió nem
ad!** A régió beállítása után a meshtasticd újraindulhat; várj néhány másodpercet,
és ellenőrizd: `venv/bin/meshtastic --host 127.0.0.1 --get lora.region`.

#### 12. Próbaküldés

```bash
venv/bin/python heartbeat.py     # egy életjel üzenet
venv/bin/python main.py          # use_scheduler = false esetén egy hírlekérés + küldés
```

Egy másik Meshtastic eszközön (pl. telefonos app) a vészhelyzeti csatornán meg kell
jelennie az üzenetnek; `want_ack = true` esetén a `mt_vesz.log`-ban az implicit
nyugta is látszik, ha egy szomszéd node továbbadta.

#### 13. Üzemszerű futtatás

Két lehetőség közül választhatsz:

- **Egyszeri mód + crontab** (`use_scheduler = false`) – lásd
  [Ütemezett futtatás külső időzítővel](#ütemezett-futtatás-külső-időzítővel).
  A crontab sorai a Pi-n is ugyanazok.
- **Folyamatos mód + systemd** (`use_scheduler = true`) – lásd
  [systemd szolgáltatás](#linux--systemd-szolgáltatás-folyamatos-mód).

A Pi újraindulása után a meshtasticd magától elindul, a program pedig a
`connect_max_retries` szerint addig próbálkozik, amíg a meshtasticd el nem érhető.

## Konfiguráció

Minden beállítás a `config.toml` fájlban található (a `.gitignore` miatt nincs
verziókezelve). Kiindulásnak másold le a `sample_config.toml`-t:

```bash
cp sample_config.toml config.toml
```

A hiányzó, alapértékkel rendelkező kulcsokat a program az alábbi táblázatokban
megadott alapértékkel használja; a kötelező (alapérték nélküli) kulcs hiányakor
érthető hibaüzenettel kilép.

A teljes mintakonfiguráció (`sample_config.toml`):

```toml
[general]
use_scheduler = false                  # true: beépített időzítővel fut folyamatosan; false: egyszer lefut és kilép (külső időzítőhöz)


[meshtastic]
connect_mode = "TCP"                  # "TCP": hálózati node | "serial": USB-s node | "rak_hat": Raspberry Pi + RAK6421 HAT (meshtasticd), lásd [rak_hat]
host = "192.168.0.182"                # TCP módban: a node IP-címe / hostneve
tcp_port = 4403                       # TCP módban: a node API portja (Meshtastic alapértelmezés: 4403)
port = "/dev/ttyUSB0"                 # serial módban: a soros port (Windows: pl. "COM3"); a list_ports.py kilistázza
lora_region = ""                      # pl. "EU_868": a setup_channel.py beállítja a node-on, ha eltér; "" = nem nyúl hozzá. Új (RAK HAT-os) node-on KÖTELEZŐ, különben a rádió nem ad!
emergency_channel_number = 1
emergency_channel_name = "EMERGENCY"
time_between_messages_s = 30
node_info_broadcast_secs = 4294967295  # NodeInfo-ismétlési időköz másodpercben; minimum 3600, maximum 4294967295
connect_max_retries = 10              # csatlakozási próbák száma feladás előtt; 0 = végtelen (folyamatos módhoz), >0 ajánlott egyszeri/cron módban
want_ack = true                       # true: wantAck jelzővel küld, megvárja a nyugtát, és nyugta híján újraküld (lásd ack_timeout_s / ack_max_retries); false: "tűzd ki és felejtsd el"
ack_timeout_s = 30                    # ennyi másodpercig várja a nyugtát (ACK/NAK) egy küldés után
ack_max_retries = 2                   # nyugta híján ennyiszer küldi újra (0 = nincs újraküldés, csak naplózás); összesen max. 1 + ack_max_retries küldés
                                      # FIGYELEM: az újraküldés új packet ID-t kap, amit a vevők NEM deduplikálnak – ha csak a nyugta veszett el, a hallgatóknál duplikátum jelenhet meg. Tartsd alacsonyan!
hop_limit = 3                         # az üzenet hányszor mehet tovább más node-okon keresztül (Meshtastic alapértelmezés: 3)


[rak_hat]
# Csak connect_mode = "rak_hat" esetén számít. A RAK6421 WisMesh Pi HAT LoRa
# modulját a Pi-n futó meshtasticd kezeli SPI-n; a program TCP-n csatlakozik hozzá.
lora_module = "RAK13300"              # "auto": a meshtasticd a HAT EEPROM-ja alapján ismeri fel | "RAK13300" | "RAK13302" (1 W-os)
slot = 1                              # melyik IO slotban van a modul: 1 / 2 (auto módban nem számít)
preset_file = ""                      # opcionális: az /etc/meshtasticd/available.d-beli preset fájlneve, ha eltér a szokásostól (felülírja a lora_module/slot párost)
host = "127.0.0.1"                    # a meshtasticd címe (ugyanazon a gépen: 127.0.0.1)
tcp_port = 4403                       # a meshtasticd API portja
meshtasticd_dir = "/etc/meshtasticd"  # a meshtasticd konfigurációs könyvtára
check_preset = true                   # true: induláskor ellenőrzi, hogy a meshtasticd presetje egyezik-e a fenti beállítással (eltérésnél figyelmeztet)


[heartbeat]
# Naponta egyszer (éjfélkor, külső cron időzítővel) küldött "életjel" üzenet,
# ami azt mutatja, hogy az eszköz működik. A {time} helyére a küldés ideje kerül.
message = "Az eszköz működik. Időpont: {time}"
time_format = "%Y-%m-%d %H:%M"


[read_messages]
# A node-on tárolt üzenetek kiolvasása (read_messages.py), hogy a node
# üzenetsora ne fusson tele. A kapcsolat csak addig áll fenn, amíg a node kiadja
# a tárolt csomagjait.
drain_quiet_s = 3                      # ennyi másodpercnyi csend után tekintjük kiürültnek a node üzenetsorát
max_listen_time_s = 30                 # felső időkorlát: folyamatos forgalom esetén se ragadjon be a futás


[log]
file = "mt_vesz.log"                   # a logfájl neve/útvonala
max_size_kb = 1024                     # a logfájl ekkora méretnél (KB) új fájlba forgat – méretkorlát
backup_count = 3                       # ennyi régi (forgatott) logfájlt tart meg; lemezhasználat felső korlátja ~ (backup_count + 1) * max_size_kb


[vesz]
rss_url = "https://www.katasztrofavedelem.hu/10466/RSS_VESZ"
rss_read_time_min = 10                 # csak use_scheduler = true esetén számít
postfix_text = "hírforrás: BM OKF"
max_message_length = 200               # a kiküldött üzenet max. hossza UTF-8 bájtban (0 = nincs korlát; ékezetes betű = 2 bájt); túllépéskor a cím végét levágja, "..."-t tesz, és a link + postfix_text kerül a végére
include_link = true                    # true: a hír oldalának linkje (rövidítve) bekerül az üzenetbe a cím és a postfix_text közé
url_shortener = "is.gd"                # ingyenes, kulcs nélküli rövidítő: "is.gd" / "v.gd" / "tinyurl"; "" = rövidítés nélkül, a teljes linket küldi
cache_max_entries = 500               # ha a cache ennél több bejegyzésre nő, lefut a takarítás (0 = kikapcsolva)
cache_clear_time_days = 30             # takarításkor az ennél régebbi bejegyzések törlődnek
```

A táblázatok „Alapérték” oszlopa azt mutatja, mit használ a program, ha a kulcs
hiányzik a `config.toml`-ból; a **kötelező** kulcs hiányakor a program hibával kilép.

### `[general]` szekció

| Kulcs | Alapérték | Leírás |
|---|---|---|
| `use_scheduler` | `true` | `true` esetén a program a beépített időzítővel folyamatosan fut (`rss_read_time_min` percenként). `false` esetén egyszer lefut (kapcsolódás → hírküldés → kilépés), így külső időzítővel (pl. crontab) hívható. |

### `[meshtastic]` szekció

| Kulcs | Alapérték | Leírás |
|---|---|---|
| `connect_mode` | **kötelező** | A kapcsolódás módja: `"TCP"` hálózati node-hoz, `"serial"` USB-n csatlakoztatott eszközhöz, `"rak_hat"` Raspberry Pi + RAK6421 HAT-hoz (ilyenkor a `[rak_hat]` szekció számít). Kis- és nagybetű mindegy. Lásd [Kapcsolódási módok](#kapcsolódási-módok). |
| `host` | TCP módban **kötelező** | A node IP-címe vagy hostneve `TCP` módban. (`rak_hat` módban a `[rak_hat] host` számít.) |
| `tcp_port` | `4403` | A node Meshtastic API portja `TCP` módban. Csak akkor kell megadni, ha a node nem az alapértelmezett porton figyel. |
| `port` | serial módban **kötelező** | A soros eszköz elérési útja (`serial` módban), pl. `/dev/ttyUSB0` Linuxon vagy `COM3` Windowson. A `list_ports.py` kilistázza a lehetőségeket. Más módban nem számít. |
| `lora_region` | `""` | A LoRa frekvenciasáv/régió, pl. `"EU_868"` (Magyarország). Ha meg van adva és eltér a node jelenlegi értékétől, a `setup_channel.py` beállítja a node-on (más script nem nyúl hozzá). `""` = nem módosítja. **Új node-on (pl. friss meshtasticd) a régió nincs beállítva, és amíg nincs, a rádió nem ad** – ilyenkor kötelező megadni. Hibás név esetén a script kiírja a lehetséges értékeket. |
| `emergency_channel_number` | `setup_channel.py`-hoz **kötelező** | A vészhelyzeti csatorna indexe. `0` a primary csatorna, `1`–`7` a secondary csatornák. |
| `emergency_channel_name` | `setup_channel.py`-hoz **kötelező** | A vészhelyzeti csatorna neve. |
| `time_between_messages_s` | **kötelező** | Várakozás másodpercben két hír kiküldése között (a mesh hálózat tehermentesítésére). |
| `node_info_broadcast_secs` | `4294967295` | A node saját NodeInfo-adatainak periodikus hirdetési időköze másodpercben. Minimum `3600` (1 óra), maximum `4294967295`; az alapérték a maximum, így alapértelmezés szerint a lehető legritkábban hirdet. A beállítást a `setup_channel.py` menti a node-ra. |
| `connect_max_retries` | `0` | Hány csatlakozási próba után adja fel a program, ha a node nem elérhető. `0` = végtelen újrapróbálkozás (folyamatos/daemon módhoz). Egyszeri/cron módban **állítsd véges értékre** (pl. `10`), különben a node kiesésekor a folyamat végtelenségig lóg, és a cron újabb beragadt folyamatokat halmozna fel. A próbák között exponenciálisan nő a várakozás (5 mp-től max. 60 mp-ig). |
| `want_ack` | `false` | `true` esetén a program `wantAck` jelzővel küldi az üzenetet, **megvárja a nyugtát**, és annak hiányában újraküld (lásd lentebb). `false` = „tűzd ki és felejtsd el”: a küldés után azonnal továbblép, és nem tudja meg, kiment-e az üzenet. |
| `ack_timeout_s` | `30` | Egy küldés után ennyi másodpercig várja a nyugtát (ACK/NAK). |
| `ack_max_retries` | `2` | Nyugta híján ennyiszer küldi újra az üzenetet (összesen max. `1 + ack_max_retries` küldés). `0` = nincs újraküldés, a program csak naplózza a nyugta hiányát. |
| `hop_limit` | `3` | Az üzenet legfeljebb hányszor adható tovább más node-okon keresztül (Meshtastic alapértelmezés: 3, maximum 7). Nagyobb érték nagyobb lefedettséget, de több rádióforgalmat jelent. |

### `[rak_hat]` szekció

Csak `connect_mode = "rak_hat"` esetén számít. A RAK6421 WisMesh Pi HAT LoRa
modulját a Pi-n futó `meshtasticd` kezeli SPI-n; a program TCP-n csatlakozik hozzá.
A `lora_module` / `slot` / `preset_file` kulcsok azt határozzák meg, melyik
rádió-presetet használja a meshtasticd – ezt a `setup_rak_hat.py` állítja be
(lásd [8. lépés](#8-a-rádió-preset-beállítása-setup_rak_hatpy)), a program pedig
minden induláskor ellenőrzi.

| Kulcs | Alapérték | Leírás |
|---|---|---|
| `lora_module` | `"auto"` | A HAT-ra szerelt LoRa modul: `"RAK13300"`, `"RAK13302"` (1 W-os változat), vagy `"auto"` – ekkor nincs preset, a meshtasticd a HAT EEPROM-ja alapján maga ismeri fel a hardvert. Ha `auto` módban a rádió nem indul el (lásd `journalctl -u meshtasticd`), add meg a modult és a slotot. |
| `slot` | `1` | Melyik IO slotban van a modul: `1` vagy `2`. `auto` módban nem számít. |
| `preset_file` | `""` | Opcionális: az `/etc/meshtasticd/available.d/` könyvtárbeli preset pontos fájlneve (pl. `"lora-RAK6421-13300-slot1.yaml"`). Ha meg van adva, felülírja a `lora_module` / `slot` párost – akkor hasznos, ha a meshtasticd csomag más néven szállítja a presetet. |
| `host` | `"127.0.0.1"` | A meshtasticd címe. Ugyanazon a gépen `127.0.0.1`. |
| `tcp_port` | `4403` | A meshtasticd Meshtastic API portja. |
| `meshtasticd_dir` | `"/etc/meshtasticd"` | A meshtasticd konfigurációs könyvtára (ebben van az `available.d` és a `config.d`). |
| `check_preset` | `true` | `true` esetén minden induláskor (main, heartbeat, setup_channel, read_messages) ellenőrzi, hogy a `config.d`-ben a fenti beállításnak megfelelő preset aktív-e. Eltérés esetén csak figyelmeztet a naplóban, a futást nem állítja meg. A `[rak_hat]` érvénytelen értékénél (pl. `slot = 3`) viszont hibával kilép. |

### `[heartbeat]` szekció

A napi „életjel” üzenet (`heartbeat.py`) beállításai.

| Kulcs | Alapérték | Leírás |
|---|---|---|
| `message` | `"Az eszköz működik. Időpont: {time}"` | Az üzenet szövege. A `{time}` helyére a küldés időpontja kerül. |
| `time_format` | `"%Y-%m-%d %H:%M"` | A `{time}` formátuma ([strftime](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes) szintaxis). |

Az életjel a `[meshtastic]` szekció `want_ack`, `ack_timeout_s`, `ack_max_retries`
beállításait használja.

### `[read_messages]` szekció

| Kulcs | Alapérték | Leírás |
|---|---|---|
| `drain_quiet_s` | `3` | A node a tárolt csomagokat egy sorozatban adja ki. Ha ennyi másodpercig nem jön újabb csomag, a sorozatot befejezettnek tekintjük (a sor kiürült), és a program lecsatlakozik. |
| `max_listen_time_s` | `30` | Felső időkorlát az olvasásra. Folyamatos rádióforgalom esetén a „csend” sosem állna be, ezért ennyi másodperc után a program mindenképp lecsatlakozik — így cron alatt nem ragad be a futás. A ki nem olvasott maradék a következő futáskor jön. |

### `[log]` szekció

A program a sikeresen kiküldött rádiós üzeneteket és minden hibát naplózza –
konzolra és egy **méretkorlátos** logfájlba egyaránt. A fájl a `max_size_kb`
méret elérésekor új fájlba forgat, és legfeljebb `backup_count` régi fájlt tart
meg (`mt_vesz.log.1`, `.2` …), így a naplók nem nőnek korlátlanul.

| Kulcs | Alapérték | Leírás |
|---|---|---|
| `file` | `"mt_vesz.log"` | A logfájl neve/útvonala. |
| `max_size_kb` | `1024` | A logfájl mérete ekkora értéknél (KB) új fájlba forgat. |
| `backup_count` | `3` | Ennyi régi (forgatott) logfájlt tart meg. A lemezhasználat felső korlátja nagyjából `(backup_count + 1) * max_size_kb` KB. |

### `[vesz]` szekció

| Kulcs | Alapérték | Leírás |
|---|---|---|
| `rss_url` | **kötelező** | A figyelt RSS-hírcsatorna URL-je. |
| `rss_read_time_min` | `use_scheduler = true` esetén **kötelező** | Milyen gyakran (percben) kérdezze le újra a hírfolyamot. Egyszeri módban nem számít. |
| `postfix_text` | **kötelező** | Minden kiküldött hír végéhez hozzáfűzött szöveg. |
| `max_message_length` | `0` | A kiküldött üzenet maximális hossza **UTF-8 bájtban** (a Meshtastic is bájtban korlátozza a csomagot; egy ékezetes betű 2 bájt). `0` = nincs korlát. Ha a teljes üzenet (cím + link + `postfix_text`) hosszabb a korlátnál, a cím végét levágja, `...`-t tesz a helyére, majd a link és a `postfix_text` következik – így az üzenet legfeljebb a beállított korlát hosszú lesz (karaktert nem vág ketté, ezért 1-3 bájttal rövidebb is lehet). A link és a `postfix_text` mindig az üzenet végén marad. |
| `include_link` | `false` | `true` esetén a hír weboldalának (az RSS `<link>` mezője, „Esemény részletei” oldal) linkje is bekerül az üzenetbe: `cím link postfix_text`. Hosszkorlát túllépésekor csak a cím rövidül, a link és a `postfix_text` megmarad. |
| `url_shortener` | `"is.gd"` | A linket lerövidítő ingyenes, regisztráció nélküli szolgáltatás: `is.gd`, `v.gd` vagy `tinyurl`. `""` = rövidítés nélkül, a teljes link kerül az üzenetbe. Ha a rövidítés nem sikerül (pl. nincs internet), a teljes linkkel megy ki a hír. |
| `cache_max_entries` | `0` | Ha a `cache.json` ennél több bejegyzésre nő, új hír érkezésekor automatikusan lefut a takarítás. `0` = kikapcsolva (korlátlan növekedés). |
| `cache_clear_time_days` | `30` | Takarításkor az ennél régebbi (napban) bejegyzések törlődnek a cache-ből. |

#### Visszajelzés a küldésről (nyugta / ACK)

`want_ack = true` esetén a program megvárja, hogy a küldött csomag packet ID-jára
érkezzen visszajelzés, és az eredményt naplózza. Háromféle nyugta lehetséges:

| Nyugta | Mit jelent | Napló |
|---|---|---|
| **Implicit ACK** | A node hallotta, hogy egy szomszéd node továbbadta (rebroadcast) a csomagot. **Broadcastnál — vagyis a hírküldésnél — ez az egyetlen elérhető pozitív jelzés.** Azt bizonyítja, hogy az üzenet kijutott a mesh-be; azt nem, hogy egy konkrét hallgató megkapta. | `Implicit nyugta: egy szomszéd node továbbadta az üzenetet` |
| **ACK** | Egy másik node visszaigazolta a vételt. Ez csak **címzett** (egy adott node-nak küldött) üzenetnél fordul elő, a csatornára szórt híreknél nem. | `Nyugta megérkezett (ACK)` |
| **NAK** | A firmware feladta a kézbesítést (az `errorReason` adja az okot, pl. nincs útvonal). | `A hálózat elutasította az üzenetet (NAK, ok: …)` |

Ha `ack_timeout_s` alatt egyik sem érkezik (vagy NAK jön), a program újraküldi az
üzenetet, legfeljebb `ack_max_retries` alkalommal. Ha az összes próba elfogy, ezt
naplózza, és a következő hírre lép — a futás nem áll meg.

> **Figyelem a duplikátumokról:** az újraküldött üzenet **új packet ID-t** kap, amit a
> vevő node-ok **nem** deduplikálnak. Ha az eredeti üzenet valójában megérkezett, és
> csak a nyugta veszett el, a hallgatóknál ugyanaz a hír kétszer jelenik meg. Ezért
> tartsd az `ack_max_retries` értékét alacsonyan (`2` vagy kevesebb). A firmware saját
> újraadása ettől független: az **ugyanazzal a packet ID-val** megy ki, amit a vevők
> kiszűrnek, tehát az sosem okoz duplikátumot.

> **Figyelem az időzítésre:** `want_ack = true` mellett egy üzenet küldése a
> legrosszabb esetben `(1 + ack_max_retries) × ack_timeout_s` másodpercig tart (az
> alapértékekkel 90 mp). Több hír esetén ehhez jön a `time_between_messages_s` szünet
> is. Cron alatt ügyelj rá, hogy ez beleférjen a futások közti időbe.

> **Megjegyzés a csatornáról:** a `setup_channel.py` a kiválasztott csatornát a
> `psk='AQ=='` (alapértelmezett, nyilvános kulcs), `uplink_enabled=False`,
> `downlink_enabled=True` beállításokkal hozza létre, és a NodeInfo periodikus
> küldési időközét a `node_info_broadcast_secs` konfigurációs értékre állítja.
> Ha titkosított, zárt csatornát szeretnél, módosítsd a `psk` értékét a
> `setup_channel.py`-ben.

## Használat

### 1. Csatorna beállítása (egyszeri)

A `config.toml` kitöltése után **egyszer** futtasd le a csatorna-beállítót. Ez
létrehozza/beállítja a vészhelyzeti csatornát a node-on, majd kilép:

```bash
python setup_channel.py
```

Ezt akkor futtasd újra, ha a csatorna beállításait (`[meshtastic]`
szekció: index, név) vagy a NodeInfo küldési időközét módosítanád.

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

#### A node tárolt üzeneteinek kiolvasása (read_messages.py)

A Meshtastic firmware a rádión vett csomagokat egy belső sorban tárolja a
csatlakozó kliens (telefonos app vagy API-kliens) számára. Ha soha senki nem
olvassa ki őket — márpedig ez a rendszer alapesetben csak *küld* —, a sor tele
fut, és a legrégebbi csomagok elvesznek. Amint egy kliens csatlakozik, a firmware
egy sorozatban kiadja neki a tárolt csomagokat, és a sor felszabadul.

A `read_messages.py` ezt végzi: csatlakozik, kiolvassa és a logfájlba írja a
node-on **tárolt** üzeneteket, majd — amint a sor kiürült — lecsatlakozik. Nem
küld semmit, és a csatorna-konfigurációt sem írja.

A protokoll nem jelöli meg, hogy egy csomag a sorból jött-e vagy épp most
érkezett, ezért a program a csomag `rxTime` (vételi idő) mezője alapján válogat:
a csatlakozás megkezdése **előtt** vett csomagok a tárolt üzenetek — ezek kerülnek
a naplóba. Ami olvasás közben, élőben érkezik, az nem tárolt üzenet: azt a program
csak megszámolja (a napló összegző sorában látszik).

> **Megjegyzés:** ha a node órája nincs beállítva (nincs GPS/idő-szinkron), az
> `rxTime` hiányozhat. Ilyenkor a program tárolt üzenetként naplózza a csomagot —
> inkább jelenjen meg feleslegesen, mint hogy kimaradjon. A node memóriája
> ettől függetlenül felszabadul, mert a sort a csatlakozás üríti.

```bash
python read_messages.py
```

Óránkénti futtatáshoz a crontabba:

```cron
30 * * * * cd $HOME/mt_vesz && $HOME/mt_vesz/venv/bin/python read_messages.py >> $HOME/mt_vesz/cron.log 2>&1
```

- `30 * * * *` — minden óra 30. percében. Az eltolás szándékos: így nem esik egybe
  a `main.py` (`*/10`) futásaival — a node egyszerre egy kapcsolatot kezel jól.
- A kiolvasott üzenetek a `[log] file` szerinti logfájlba (`mt_vesz.log`) kerülnek.

### Linux — systemd szolgáltatás (folyamatos mód)

`use_scheduler = true` esetén a `main.py` folyamatosan fut; ilyenkor crontab helyett
systemd szolgáltatásként érdemes futtatni, így a gép indulásakor magától elindul, és
hiba esetén újraindul. A minta a `systemd/mt_vesz.service` fájlban található – a
`User`, `WorkingDirectory` és `ExecStart` sorokat igazítsd a saját felhasználódhoz
és útvonaladhoz.

```bash
sudo cp systemd/mt_vesz.service /etc/systemd/system/
sudo nano /etc/systemd/system/mt_vesz.service   # felhasználó, útvonalak ellenőrzése
sudo systemctl daemon-reload
sudo systemctl enable --now mt_vesz
```

- `After=… meshtasticd.service` — RAK HAT esetén a meshtasticd után indul. Ha a
  meshtasticd később újraindul, a program magától újracsatlakozik.
- `Restart=on-failure` — hibás kilépés után 30 mp-cel újraindul.
- Állapot és napló: `systemctl status mt_vesz`, `journalctl -u mt_vesz -f`
  (a részletes napló a `mt_vesz.log`-ban is megvan).

A heartbeat és a read_messages ilyenkor is crontabból fut (lásd fent).

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
| `setup_channel.py` | A vészhelyzeti csatorna, a NodeInfo-időköz és a LoRa régió egyszeri beállítása a node-on. |
| `setup_rak_hat.py` | RAK6421 HAT: a meshtasticd rádió-presetjének beállítása / ellenőrzése a `[rak_hat]` szerint (root jog kell). |
| `heartbeat.py` | Napi „életjel” üzenet küldése a csatornára. |
| `read_messages.py` | A node-on tárolt üzenetek kiolvasása (naplózás), a node memóriájának felszabadítására. |
| `list_ports.py` | Elérhető soros (USB) portok listázása (Linux/Windows). |
| `mt_lib.py` | Meshtastic kapcsolatkezelés (TCP / soros / RAK HAT), újracsatlakozás, üzenetküldés ACK-kal. |
| `rak_hat.py` | RAK6421 HAT segédfüggvények: preset kiválasztása, ellenőrzése, telepítése. |
| `app_config.py` | A `config.toml` betöltése és a `cfg()` kiolvasó függvény. |
| `sample_config.toml` | Mintakonfiguráció – ebből készül a `config.toml`. |
| `systemd/mt_vesz.service` | Minta systemd unit a folyamatos (`use_scheduler = true`) futtatáshoz. |
| `vesz_lib.py` | RSS-letöltés és cache-kezelés (`BMFeeds` osztály). |
| `log_setup.py` | A méretkorlátos, forgó logfájl + konzol naplózás beállítása. |
| `config.toml` | Konfiguráció. |
| `cache.json` | A már látott hírek (futás közben jön létre). |
| `mt_vesz.log` | Napló: sikeres küldések és hibák (futás közben jön létre, méretkorlátos). |

## Hibaelhárítás

- **Nem csatlakozik a node-hoz:** ellenőrizd a `connect_mode`-ot és a `host`/`port`
  (RAK HAT esetén a `[rak_hat] host` / `tcp_port`) értéket. TCP módban a node-nak elérhetőnek kell lennie a hálózaton (a Meshtastic
  WiFi/eszköz IP-jén). A `connect()` automatikusan újrapróbálkozik, így a kapcsolódás
  blokkol, amíg sikerül.
- **RAK HAT: „fut a meshtasticd szolgáltatás?” hiba:** a program nem éri el a
  meshtasticd-t a `127.0.0.1:4403` címen. Ellenőrizd: `systemctl status meshtasticd`.
  Ha nem fut vagy újraindulgat, nézd meg a naplóját: `journalctl -u meshtasticd -n 100`.
- **RAK HAT: a meshtasticd fut, de nem találja a rádiót** (a naplóban SX1262 / LoRa
  hiba): ellenőrizd, hogy be van-e kapcsolva az SPI (`ls /dev/spidev0.0`), hogy a modul
  abban a slotban van-e, amit a `[rak_hat] slot` mond, és hogy a preset aktív-e:
  `venv/bin/python setup_rak_hat.py --check`. `lora_module = "auto"` esetén próbáld
  meg kifejezetten megadni a modult és a slotot, majd futtasd újra a
  `sudo venv/bin/python setup_rak_hat.py`-t.
- **RAK HAT: „RAK HAT: … preset nincs a config.d könyvtárban” figyelmeztetés a
  naplóban:** a meshtasticd beállítása eltér a `config.toml`-tól (pl. a `slot`-ot
  módosítottad). Futtasd: `sudo venv/bin/python setup_rak_hat.py`.
- **RAK HAT: „Nem található a preset” a `setup_rak_hat.py`-ban:** a telepített
  meshtasticd más néven (vagy nem) szállítja a presetet. A hibaüzenet kiírja az
  elérhető RAK6421 preseteket (`ls /etc/meshtasticd/available.d/`); a megfelelőt add
  meg a `[rak_hat] preset_file` kulcsban, vagy frissítsd a meshtasticd-t
  (`sudo apt update && sudo apt upgrade meshtasticd`).
- **RAK HAT: a node csatlakozik, de nem ad / senki nem hallja:** valószínűleg nincs
  beállítva a LoRa régió. Állítsd be a `lora_region = "EU_868"` értéket, és futtasd a
  `setup_channel.py`-t; ellenőrzés: `venv/bin/meshtastic --host 127.0.0.1 --get lora.region`.
  Ellenőrizd az antennát is.
- **Nem mennek ki hírek, „Töröld a cache.json-t!”:** minden aktuális hír már a cache-ben
  van. Töröld a `cache.json`-t, ha újra ki akarod küldeni őket. A main.py újraindítása szükséges!
- **„Nem érkezett nyugta … próba” a naplóban:** a node nem hallotta, hogy bármelyik
  szomszéd továbbadta volna a csomagot – valószínűleg egyedül van a hatótávolságában,
  vagy nincs vétel. A program a beállított `ack_max_retries`-ig újrapróbálja, majd a
  következő hírre lép. Ha a node tényleg magában van, `want_ack = false`-szal
  gyorsabban lefut a küldés (visszajelzés nélkül).
- **Ugyanaz a hír kétszer jelenik meg a hallgatóknál:** az újraküldés új packet ID-t kap,
  amit a vevők nem szűrnek ki. Csökkentsd az `ack_max_retries` értékét (vagy `0`-ra
  állítva csak naplózza a nyugta hiányát, újraküldés nélkül).
