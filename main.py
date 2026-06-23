import time

import schedule

import mt_lib
import vesz_lib


def init():
    """Kapcsolódás és csatorna beállítása. A mt.connect() magától újrapróbálkozik,
    így ez addig blokkol, amíg sikerül csatlakozni."""
    mt.connect()
    try:
        mt.setChannel(edit_channel=1, new_settings={
            'psk': 'AQ==',
            'name': 'vesz_teszt',
            'uplink_enabled': False,
            'downlink_enabled': True,
            'position_precision': 13
        })
    except Exception as e:
        print(f"Csatorna beállítása sikertelen: {e}")

    try:
        mt.sendMessage("Veszélyhelyzet információs rendszer elindult.")
    except Exception as e:
        print(f"Indító üzenet küldése sikertelen: {e}")


def job():
    print("I'm working...")

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
        time.sleep(30)
    print(news)


mt = mt_lib.MtTcpHandler(host='192.168.0.182')
feeds = vesz_lib.BMFeeds()


if __name__ == "__main__":
    init()

    schedule.every(1).minutes.do(job)
    #schedule.every().hour.do(job)
    #schedule.every().day.at("10:30").do(job)

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
