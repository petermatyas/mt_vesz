import schedule
import time

import mt_lib
import vesz_lib




def init():
    mt.connect()
    mt.setChannel(edit_channel=1, new_settings={
        'psk': 'AQ==',
        'name': 'vesz_teszt',
        'uplink_enabled': False,
        'downlink_enabled': True,
        'position_precision': 13
    })
    mt.sendMessage("Veszélyhelyzet információs rendszer elindult.")

def job():

    print("I'm working...")
    #mt.sendMessage("aaa")
    
    news = feeds.getNews()
    print(f"Új hírek száma: {len(news)}")
    for i in news:
        print("Sending news: ", repr(i))
        mt.sendMessage(i)
        time.sleep(30)
    print(news)


mt = mt_lib.MtTcpHandler(host='192.168.0.182')
feeds = vesz_lib.BMFeeds()

#schedule.every(1).minutes.do(job)
#schedule.every().hour.do(job)
#schedule.every().day.at("10:30").do(job)


init()
job()


"""n = 0
while 1:
    try:
        print(f"loop {n}")
        n += 1
        schedule.run_pending()
    except KeyboardInterrupt:
        print("Program leállítva.")
        break
    except Exception as e:
        print(f"Hiba történt: {e}")
        time.sleep(5)
        mt.connect() 

    time.sleep(1)"""