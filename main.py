import time
import tomllib

import mt_lib
import vesz_lib



with open("config.toml", "rb") as f:
    config = tomllib.load(f)




def init():
    """Kapcsolódás és csatorna beállítása. A mt.connect() magától újrapróbálkozik,
    így ez addig blokkol, amíg sikerül csatlakozni."""
    mt.connect()
    try:
        mt.setChannel(edit_channel=config["meshtastic"]["emergency_channel_number"], 
                      new_settings={
                        'psk': 'AQ==',
                        'name': config["meshtastic"]["emergency_channel_name"],
                        'uplink_enabled': False,
                        'downlink_enabled': True,
                        'position_precision': 13
                    })
    except Exception as e:
        print(f"Csatorna beállítása sikertelen: {e}")


def job():

    try:
        news = feeds.getNews()
    except Exception as e:
        print(f"Hírek lekérése sikertelen: {e}")
        return

    print(f"Új hírek száma: {len(news)}")
    for i in news:
        print("Sending news: ", repr(i))
        try:
            mt.sendMessage(i)
        except TimeoutError as e:
            # Nem érkezett ACK az újraküldések után sem – a node valószínűleg
            # egyedül van, vagy nincs vétel. Lépjünk a következő hírre.
            print(f"Hír nem lett kézbesítve (nincs ACK): {e}")
        except Exception as e:
            print(f"Hír küldése sikertelen: {e}")

        time.sleep(config["meshtastic"]["time_between_messages_s"])






if __name__ == "__main__":
    connect_mode = config["meshtastic"]["connect_mode"].lower()
    if connect_mode == "tcp":
        mt = mt_lib.MtTcpHandler(host=config["meshtastic"]["host"])
    elif connect_mode == "serial":
        mt = mt_lib.MtSerialHandler(port=config["meshtastic"]["port"])
    else:
        raise TypeError("Érvényetelen connect_mode a config fájlban. TCP / serial")


    feeds = vesz_lib.BMFeeds(rss_url=config["vesz"]["rss_url"], postfix_text=config["vesz"]["postfix_text"])


    init()
    job()

    if config["general"].get("use_scheduler", True):
        # Beépített időzítővel folyamatosan fut.
        import schedule

        schedule.every(config["vesz"]["rss_read_time_min"]).minutes.do(job)

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
