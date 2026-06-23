import feedparser
import re
import json
from datetime import datetime
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

    def _get_max_timestamp(self):
        """Megkeresi a legfrissebb elem időbélyegét a cache-ben."""
        if not self.cache:
            return 0
        return max(time.mktime(time.strptime(item['published'], "%a, %d %b %Y %H:%M:%S %z")) 
                   for item in self.cache if 'published' in item)

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
        
        self.cache = [
            item for item in self.cache 
            if (now_ts - time.mktime(time.strptime(item['published'], "%a, %d %b %Y %H:%M:%S %z"))) < clear_time_s
        ]
        
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








