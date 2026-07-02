import feedparser
import json
import calendar
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
import os


logger = logging.getLogger(__name__)



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

        Egyik hiba sem állítja meg a programot – csak jelezzük, és ``False``-szal
        térünk vissza. Ilyenkor a cache memóriában frissül, de a lemezre nem íródik
        ki (a hírek a következő futáskor újra újnak látszhatnak):
          - szerializálási hiba (nem JSON-be írható bejegyzés): TypeError/ValueError,
          - írási hiba (megtelt lemez, jogosultság stb.): OSError.

        Előbb stringgé szerializálunk, és csak utána írunk, hogy egy szerializálási
        hiba ne hagyjon félig írt, sérült cache fájlt."""
        try:
            data = json.dumps(self.cache, ensure_ascii=False, indent=4)
        except (TypeError, ValueError) as e:
            logger.error("Cache szerializálása sikertelen (%s): %s", self.cache_file, e)
            return False

        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                f.write(data)
            return True
        except OSError as e:
            logger.error("Cache mentése sikertelen (%s): %s", self.cache_file, e)
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

        # A feedparser hálózati/parse-hibánál nem dob kivételt, csak a bozo flaget
        # állítja – enélkül a hiba némán "0 új hír"-ként jelenne meg. Kiírjuk az okot
        # a diagnosztikához. (bozo akkor is igaz lehet, ha az entries használható,
        # ezért nem lépünk ki, csak jelzünk.)
        if feed.bozo:
            logger.warning("A hírfolyam feldolgozása hibát jelzett: %s",
                           feed.get('bozo_exception'))

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
            logger.info("Cache mérete (%d) meghaladta a limitet (%d) – takarítás indul.",
                        len(self.cache), self.max_cache_entries)
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
            logger.info("Takarítás kész: %d elem törölve.", original_len - len(self.cache))

    def getNews(self):
        rawNews = self.download() or []
        news = list()
        for i in rawNews:
            title = i.get('title', '')  # cím nélküli bejegyzés ne dobjon AttributeError-t
            if not title:
                continue  # cím nélkül nincs értelmes üzenet, kihagyjuk
            news.append(f"{title} {self.postfix_text}")
        return news

if __name__ == "__main__":
    
    feeds = BMFeeds()
    news = feeds.getNews()

    if not news:
        print("Töröld a cache.json-t!")
        
    for line in news:
        print(line)








