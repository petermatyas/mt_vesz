import feedparser
import json
import calendar
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
import os
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)

# Ingyenes, regisztráció/API-kulcs nélküli URL-rövidítők. A válasz egyszerű
# szöveg: maga a rövid URL.
URL_SHORTENERS = {
    "is.gd": "https://is.gd/create.php?format=simple&url={url}",
    "v.gd": "https://v.gd/create.php?format=simple&url={url}",
    "tinyurl": "https://tinyurl.com/api-create.php?url={url}",
}



class BMFeeds():
    def __init__(self, rss_url="https://www.katasztrofavedelem.hu/10466/RSS_VESZ",
                 cache_file='cache.json',
                 postfix_text="hírforrás: BM OKF",
                 max_message_length=0,
                 max_cache_entries=0,
                 clear_time_s=30 * 24 * 3600,
                 include_link=False,
                 url_shortener="is.gd"):
        self.url = rss_url
        self.cache_file = cache_file
        self.postfix_text = postfix_text
        # A kiküldött üzenet maximális hossza karakterben (0 = nincs korlát).
        self.max_message_length = max_message_length
        # Ha a cache ennél több bejegyzésre nő, lefut az idő-alapú takarítás
        # (0 = kikapcsolva). A clear_time_s adja meg, milyen régi elemek törlődnek.
        self.max_cache_entries = max_cache_entries
        self.clear_time_s = clear_time_s
        # Ha igaz, a hír oldalának (az RSS <link> mezője) linkje is bekerül az
        # üzenetbe, a url_shortener szolgáltatással lerövidítve ("" = rövidítés nélkül).
        self.include_link = include_link
        if url_shortener and url_shortener not in URL_SHORTENERS:
            logger.warning("Ismeretlen url_shortener (%r) – rövidítés nélkül küldjük a linket. "
                           "Lehetséges értékek: %s", url_shortener, ", ".join(URL_SHORTENERS))
            url_shortener = ""
        self.url_shortener = url_shortener
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

    def _shorten_url(self, url):
        """Lerövidíti az URL-t a beállított szolgáltatással.

        Hiba esetén (hálózat, időtúllépés, értelmezhetetlen válasz) nem állunk
        meg: figyelmeztetünk, és az eredeti, hosszú URL-t adjuk vissza."""
        if not self.url_shortener:
            return url
        api = URL_SHORTENERS[self.url_shortener].format(url=urllib.parse.quote(url, safe=""))
        try:
            req = urllib.request.Request(api, headers={"User-Agent": "mt_vesz"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                short = resp.read().decode("utf-8").strip()
        except (urllib.error.URLError, OSError, UnicodeDecodeError) as e:
            logger.warning("URL rövidítése sikertelen (%s): %s – a teljes linket küldjük.",
                           self.url_shortener, e)
            return url
        if not short.startswith("http"):
            # Az is.gd/v.gd hibát is 200-as válasszal, szövegként adhat vissza.
            logger.warning("URL rövidítése sikertelen (%s): %r – a teljes linket küldjük.",
                           self.url_shortener, short[:100])
            return url
        return short

    def _build_message(self, title, link=""):
        """Összeállítja a kiküldendő üzenetet: a cím, (ha van) a link, és a
        végére fűzött ``postfix_text``. A link és a postfix mindig az üzenet
        végén marad.

        Ha van hosszkorlát (``max_message_length`` > 0) és a teljes üzenet
        hosszabb annál, a cím végét levágjuk, három pontot ("...") teszünk a
        helyére, majd a link és a postfix következik – úgy, hogy az üzenet
        hossza pontosan a beállított korlát legyen."""
        tail = " ".join(p for p in (link, self.postfix_text) if p)
        full = f"{title} {tail}"
        if not self.max_message_length or len(full) <= self.max_message_length:
            return full

        # "...<szóköz>link postfix" – ez mindenképp az üzenet végén marad.
        suffix = f"... {tail}"
        keep = self.max_message_length - len(suffix)
        if keep <= 0:
            # A korlát még a postfixet (+ "...") sem fedi le – ilyenkor nem tudunk
            # a korláton belül maradni, de a postfixet nem dobjuk el.
            logger.warning(
                "A max_message_length (%d) túl kicsi a linkhez és a postfix_text-hez – "
                "az üzenet hosszabb lesz a korlátnál.", self.max_message_length)
            return suffix
        return f"{title[:keep]}{suffix}"

    def getNews(self):
        rawNews = self.download() or []
        news = list()
        for i in rawNews:
            title = i.get('title', '')  # cím nélküli bejegyzés ne dobjon AttributeError-t
            if not title:
                continue  # cím nélkül nincs értelmes üzenet, kihagyjuk
            link = i.get('link', '')
            if self.include_link and link:
                link = self._shorten_url(link)
            else:
                link = ""
            news.append(self._build_message(title, link))
        return news

if __name__ == "__main__":
    
    feeds = BMFeeds()
    news = feeds.getNews()

    if not news:
        print("Töröld a cache.json-t!")
        
    for line in news:
        print(line)








