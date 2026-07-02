import feedparser
import json
import calendar
from datetime import datetime
from email.utils import parsedate_to_datetime
import os



class BMFeeds():
    def __init__(self, rss_url="https://www.katasztrofavedelem.hu/10466/RSS_VESZ",
                 cache_file='cache.json',
                 postfix_text="hírforrás: BM OKF",
                 max_cache_entries=0,
                 clear_time_s=30 * 24 * 3600):
        self.url = rss_url
        self.cache_file = cache_file
        self.postfix_text = postfix_text
        # Ha a cache ennél több bejegyzésre nő, lefut az idő-alapú takarítás
        # (0 = kikapcsolva). A clear_time_s adja meg, milyen régi elemek törlődnek.
        self.max_cache_entries = max_cache_entries
        self.clear_time_s = clear_time_s
        self.cache = self._load_cache()

    def _load_cache(self):
        """Betölti a cache-t a fájlból, ha létezik."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_cache(self):
        """Elmenti a jelenlegi cache tartalmát JSON fájlba.

        Írási hiba (megtelt lemez, jogosultság stb.) nem állítja meg a programot:
        csak jelezzük, és ``False``-szal térünk vissza. Ilyenkor a cache memóriában
        frissül, de a lemezre nem íródik ki (a hírek a következő futáskor újra
        újnak látszhatnak)."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=4)
            return True
        except OSError as e:
            print(f"Cache mentése sikertelen ({self.cache_file}): {e}")
            return False

    @staticmethod
    def _item_timestamp(item):
        """POSIX időbélyeg egy cache-elemhez, locale-független módon.

        Elsődlegesen a feedparser ``published_parsed`` mezőjét használja (UTC
        struct_time, a JSON cache-ben 9 elemű listaként tárolva); ha az hiányzik,
        a ``published`` RFC 2822 stringet az email.utils-szal értelmezi (ez sem
        locale-függő). Ha egyik sem értelmezhető, ``None``-t ad vissza."""
        parsed = item.get('published_parsed')
        if parsed:
            # calendar.timegm UTC struct_time-ot vár (a JSON-ből lista jön).
            return calendar.timegm(tuple(parsed))
        published = item.get('published')
        if published:
            try:
                return parsedate_to_datetime(published).timestamp()
            except (TypeError, ValueError):
                return None
        return None

    def download(self):
        feed = feedparser.parse(self.url)
        if not feed.entries:
            return []

        # A dedupot a link-alapú összehasonlítás végzi (update_cache), ezért nincs
        # szükség külön idő-alapú szűrőre.
        added, news = self.update_cache(feed.entries)
        if added:
            self._save_cache()  # csak akkor írunk lemezre, ha tényleg jött új hír
            self._enforce_cache_limit()  # túl nagy cache esetén takarítás
        return news

    def _enforce_cache_limit(self):
        """Ha a cache mérete meghaladja a beállított limitet, lefuttatja az
        idő-alapú takarítást (a ``clear_time_s``-nél régebbi elemeket törli)."""
        if self.max_cache_entries and len(self.cache) > self.max_cache_entries:
            print(f"Cache mérete ({len(self.cache)}) meghaladta a limitet "
                  f"({self.max_cache_entries}) – takarítás indul.")
            self.clear_cache(self.clear_time_s)


    def update_cache(self, entries):
        existing_links = {item.get('link') for item in self.cache}
        added = False
        
        news = list()
        for entry in entries:
            if entry.get('link') not in existing_links:
                # A feedparser objektumot átalakítjuk sima dict-re a JSON mentéshez
                self.cache.append(dict(entry))
                news.append(entry)
                added = True
        return added, news

    def clear_cache(self, clear_time_s):
        now_ts = datetime.now().timestamp()
        original_len = len(self.cache)

        def _keep(item):
            ts = self._item_timestamp(item)
            # Értelmezhetetlen időbélyegű elemet biztonságból megtartunk.
            return ts is None or (now_ts - ts) < clear_time_s

        self.cache = [item for item in self.cache if _keep(item)]

        if len(self.cache) < original_len:
            self._save_cache()
            print(f"Takarítás kész: {original_len - len(self.cache)} elem törölve.")

    def getNews(self):
        rawNews = self.download() or []
        news = list()
        for i in rawNews:
            text = i.title
            text += f" {self.postfix_text}"        
            news.append(text)
        return news

if __name__ == "__main__":
    
    feeds = BMFeeds()
    news = feeds.getNews()

    if not news:
        print("Töröld a cache.json-t!")
        
    for line in news:
        print(line)








