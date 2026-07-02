import feedparser
import re
import json
import calendar
from datetime import datetime
from email.utils import parsedate_to_datetime
import time
import os
import schedule



class BMFeeds():
    def __init__(self, rss_url="https://www.katasztrofavedelem.hu/10466/RSS_VESZ", 
                 cache_file='cache.json',
                 postfix_text="hírforrás: BM OKF"):
        self.url = rss_url
        self.cache_file = cache_file
        self.postfix_text = postfix_text
        self.cache = self._load_cache()
        # Az utolsó frissítés idejét a legfrissebb cache elemhez igazítjuk
        self.last_updated_cache_time = self._get_max_timestamp()

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
        """Elmenti a jelenlegi cache tartalmát JSON fájlba."""
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=4)

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

    def _get_max_timestamp(self):
        """Megkeresi a legfrissebb elem időbélyegét a cache-ben."""
        timestamps = [ts for ts in (self._item_timestamp(item) for item in self.cache)
                      if ts is not None]
        return max(timestamps) if timestamps else 0

    def download(self):
        feed = feedparser.parse(self.url)
        if not feed.entries:
            return

        current_feed_time = time.mktime(feed.get('updated_parsed', time.gmtime()))

        news = list()
        if current_feed_time > self.last_updated_cache_time:
            added, news = self.update_cache(feed.entries)
            self.last_updated_cache_time = current_feed_time
            self._save_cache() # Mentés minden sikeres letöltés után

        return news


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








