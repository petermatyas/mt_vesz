"""A vészhelyzeti csatorna egyszeri beállítása a Meshtastic node-on.

A rutin hírküldés (main.py) NEM állítja a csatornát, hogy ne írjon feleslegesen
a node flash-ébe minden futáskor (különösen cron-módban). Ezt a scriptet elég
egyszer lefuttatni – illetve akkor, ha a csatorna beállításait (`config.toml`
[meshtastic] szekció) módosítod.

Minden beállítást a config.toml-ból olvas.

Használat:
    python setup_channel.py
"""

from main import cfg, build_handler


def main():
    mt = build_handler()

    try:
        mt.connect()
    except Exception as e:
        raise SystemExit(f"Hiba: nem sikerült csatlakozni a node-hoz: {e}")

    try:
        mt.setChannel(
            edit_channel=cfg("meshtastic.emergency_channel_number"),
            new_settings={
                'psk': 'AQ==',
                'name': cfg("meshtastic.emergency_channel_name"),
                'uplink_enabled': False,
                'downlink_enabled': True,
                'position_precision': 13,
            },
        )
        print("Vészhelyzeti csatorna beállítva.")
    except Exception as e:
        print(f"Csatorna beállítása sikertelen: {e}")
    finally:
        try:
            mt.disconnect()
        except Exception as e:
            print(f"Lecsatlakozás sikertelen: {e}")


if __name__ == "__main__":
    main()
