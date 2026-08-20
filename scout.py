"""
Deal Scout — continuous undervalued-inventory finder.

This module powers the "Scout" side of the site: instead of selling cards, it
continuously searches online listings for *buying* opportunities — sealed
sports-card boxes, memorabilia, and card lots that look undervalued.

How it works
------------
A background thread walks a watchlist of searches (watchlist.json). For each
search it:

  1. Pulls current listings from every enabled source (eBay Browse API today;
     the SOURCES registry makes more pluggable).
  2. Builds a *reference price* for that kind of item — the median asking price
     of comparable Buy-It-Now listings in the same search (a market proxy;
     eBay's true sold-comp data needs the restricted Marketplace Insights API).
  3. Flags listings priced meaningfully below that reference as deals, scores
     them by discount + dollar savings + confidence, and saves them to
     deals.json (deduped by item id, with first_seen / last_seen tracking).

Auctions are only flagged when they are ending soon *and* the current bid is
still below reference — an early auction with a $1 bid and six days left is not
a deal yet, so we don't cry wolf.

With no eBay keys configured, the scout runs in DEMO mode: it synthesizes a
realistic, lightly-varying set of deals so the whole dashboard works end-to-end
before you plug anything in.

Design notes
------------
* Zero third-party dependencies — standard library only, like server.py.
* server.py calls init() once with its config + shared HTTP/eBay helpers, then
  start(). No import of server here, so there's no circular import.
"""

import gzip
import json
import math
import os
import random
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
DEALS_PATH = os.path.join(SITE_DIR, "deals.json")
WATCHLIST_PATH = os.path.join(SITE_DIR, "watchlist.json")

# ---- injected by server.init() so we don't import server (avoids a cycle)
_cfg = {}
_http_json = None
_ebay_token = None
_ebay_live = lambda: False

_deals_lock = threading.Lock()
_state = {
    "running": False,
    "runs": 0,
    "last_run": None,
    "last_run_started": None,
    "last_duration_sec": None,
    "last_error": None,
    "last_deals_found": 0,
    "scanning_now": False,
    "next_run_eta": None,
    "sources": [],
    "mode": "demo",
}
_scan_lock = threading.Lock()  # ensures only one scan runs at a time


# ---------------------------------------------------------------- tunables

def _num(key, default):
    try:
        return float(_cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def _int(key, default):
    try:
        return int(float(_cfg.get(key, default)))
    except (TypeError, ValueError):
        return default


def interval_min():
    return max(5, _int("SCOUT_INTERVAL_MIN", 30))


def min_discount():
    # A listing must be at least this fraction below reference to be a deal.
    return max(0.05, _num("SCOUT_MIN_DISCOUNT", 0.25))


def min_comps():
    # How many comparable BIN listings we need before we trust a median.
    return max(3, _int("SCOUT_MIN_COMPS", 4))


def min_price():
    return _num("SCOUT_MIN_PRICE", 8.0)


def auction_window_hours():
    return _num("SCOUT_AUCTION_WINDOW_HOURS", 12)


def retention_days():
    return _num("SCOUT_RETENTION_DAYS", 14)


def per_query_limit():
    return min(200, max(10, _int("SCOUT_PER_QUERY_LIMIT", 100)))


def autostart():
    # Background loop on by default; set SCOUT_AUTOSTART=false to require manual scans.
    val = _cfg.get("SCOUT_AUTOSTART", True)
    return str(val).lower() not in ("false", "0", "no", "off")


def public_ebay_enabled():
    # Scrape eBay's public search (no API keys) when keys aren't configured.
    val = _cfg.get("SCOUT_PUBLIC_EBAY", True)
    return str(val).lower() not in ("false", "0", "no", "off")


# ---------------------------------------------------------------- watchlist

# What the scout hunts for out of the box. Each entry is one saved search.
# category: sealed_box | card_lot | memorabilia | single_card
# ref_price (optional): a hand-set market anchor used when live comps are thin.
DEFAULT_WATCHLIST = [
    {"query": "baseball hobby box sealed", "category": "sealed_box", "sport": "Baseball"},
    {"query": "basketball hobby box sealed", "category": "sealed_box", "sport": "Basketball"},
    {"query": "football hobby box sealed", "category": "sealed_box", "sport": "Football"},
    {"query": "topps chrome hobby box factory sealed", "category": "sealed_box", "sport": "Baseball"},
    {"query": "panini prizm sealed hobby box", "category": "sealed_box", "sport": "Basketball"},
    {"query": "bowman chrome hobby box sealed", "category": "sealed_box", "sport": "Baseball"},
    {"query": "unopened wax box vintage baseball", "category": "sealed_box", "sport": "Baseball"},
    {"query": "sports card lot collection estate", "category": "card_lot", "sport": "Mixed"},
    {"query": "baseball card lot vintage shoebox", "category": "card_lot", "sport": "Baseball"},
    {"query": "basketball card lot collection", "category": "card_lot", "sport": "Basketball"},
    {"query": "sports memorabilia lot signed", "category": "memorabilia", "sport": "Mixed"},
    {"query": "storage unit sports cards collection", "category": "card_lot", "sport": "Mixed"},
]


def load_watchlist():
    if os.path.exists(WATCHLIST_PATH):
        try:
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [w for w in data if isinstance(w, dict) and w.get("query")]
        except Exception as e:  # malformed file -> fall back, don't crash
            print("[scout] watchlist.json unreadable, using defaults:", e)
    return DEFAULT_WATCHLIST


# ---------------------------------------------------------------- filtering

# Words that usually mean "this isn't the intact, sealed, real thing".
RED_FLAG_WORDS = [
    "empty box", "empty", "no cards", "box only", "wrapper only", "wrappers only",
    "reprint", "reprints", "rp ", "custom", "aceo", "novelty", "sticker",
    "digital", "nft", "read description", "damaged", "water damage", "as is repair",
    "poster", "magazine", "toploader", "top loader", "supplies", "penny sleeves",
    "binder only", "empty pack", "resealed", "re-sealed", "opened",
]

# Positive signals per category — a candidate must hit at least one.
CATEGORY_KEYWORDS = {
    "sealed_box": ["sealed", "unopened", "factory", "hobby box", "wax box", "case", "box"],
    "card_lot": ["lot", "collection", "cards", "estate", "shoebox", "bulk", "binder"],
    "memorabilia": ["signed", "autograph", "auto", "jersey", "patch", "relic",
                    "memorabilia", "game used", "game-used", "photo", "ball", "helmet"],
    "single_card": ["card", "rookie", "psa", "bgs", "sgc", "prizm", "refractor", "auto"],
}

SPORT_KEYWORDS = {
    "Baseball": ["baseball", "mlb", "topps", "bowman"],
    "Basketball": ["basketball", "nba", "prizm basketball", "hoops"],
    "Football": ["football", "nfl"],
    "Hockey": ["hockey", "nhl"],
    "Soccer": ["soccer", "fifa", "futbol"],
}


def _has_red_flag(title):
    t = f" {title.lower()} "
    return any(f" {w} " in t or t.strip().startswith(w) for w in RED_FLAG_WORDS)


def _matches_category(title, category):
    t = title.lower()
    kws = CATEGORY_KEYWORDS.get(category, [])
    return any(k in t for k in kws) if kws else True


def _guess_sport(title, fallback="Mixed"):
    t = title.lower()
    for sport, kws in SPORT_KEYWORDS.items():
        if any(k in t for k in kws):
            return sport
    return fallback


# ---------------------------------------------------------------- eBay source

def _epoch_from_iso(iso):
    """Robust ISO-8601 (UTC 'Z') -> epoch seconds using calendar math."""
    try:
        date_part, time_part = iso.split("T")
        y, mo, d = (int(x) for x in date_part.split("-"))
        time_part = time_part.rstrip("Z")
        if "." in time_part:
            time_part = time_part.split(".")[0]
        if "+" in time_part:
            time_part = time_part.split("+")[0]
        h, mi, s = (int(x) for x in time_part.split(":"))
        return calendar_timegm((y, mo, d, h, mi, s))
    except Exception:
        return None


def calendar_timegm(t):
    """timegm without importing calendar just for one call."""
    import calendar
    return calendar.timegm(t)


def fetch_ebay(query, category, limit):
    """Return normalized candidate listings from eBay's Browse API."""
    token, err = _ebay_token()
    if err:
        return None, err
    all_items = []
    offset = 0
    page = 100 if limit >= 100 else limit
    while offset < limit:
        params = urllib.parse.urlencode({
            "q": query,
            "limit": str(min(page, limit - offset)),
            "offset": str(offset),
            "filter": "buyingOptions:{FIXED_PRICE|AUCTION}",
        })
        data, err = _http_json(
            f"https://api.ebay.com/buy/browse/v1/item_summary/search?{params}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            },
        )
        if err:
            return (all_items or None), (None if all_items else err)
        summaries = data.get("itemSummaries", []) or []
        for it in summaries:
            all_items.append(_normalize_ebay(it, query, category))
        if len(summaries) < page:
            break
        offset += page
    return all_items, None


def _normalize_ebay(it, query, category):
    opts = it.get("buyingOptions", []) or []
    is_auction = "AUCTION" in opts
    bin_price = _price_val(it.get("price"))
    bid_price = _price_val(it.get("currentBidPrice"))
    effective = bid_price if (is_auction and bid_price is not None) else bin_price
    title = it.get("title") or ""
    return {
        "source": "ebay",
        "id": it.get("itemId") or it.get("itemWebUrl") or title,
        "title": title,
        "price": effective,
        "bin_price": bin_price,
        "currency": (it.get("price") or {}).get("currency", "USD"),
        "image": (it.get("image") or {}).get("imageUrl"),
        "url": it.get("itemWebUrl"),
        "condition": it.get("condition"),
        "seller": (it.get("seller") or {}).get("username"),
        "buying_options": opts,
        "is_auction": is_auction,
        "bid_count": it.get("bidCount"),
        "end_time": _epoch_from_iso(it.get("itemEndDate")) if it.get("itemEndDate") else None,
        "category": category,
        "sport": _guess_sport(title),
        "query": query,
    }


def _price_val(p):
    if not p:
        return None
    try:
        return round(float(p.get("value")), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- eBay (public search, no API key)

# A desktop browser UA — eBay serves the normal results HTML for this.
_PUBLIC_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _http_get_text(url, headers=None):
    """GET a page and return (html_text, error). Handles gzip."""
    req = urllib.request.Request(url, headers=headers or _PUBLIC_HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {url}"
    except Exception as e:
        return None, f"request to {url} failed: {e}"


def fetch_ebay_public(query, category, limit):
    """Scrape eBay's public search results (no API key required).

    Polite by design: a couple of pages per query, a short pause between pages,
    and the whole watchlist runs on a slow interval. This reads the same public
    results page a shopper sees.
    """
    results, seen = [], set()
    per_page = 60
    pages = max(1, min(3, math.ceil(limit / per_page)))
    for pg in range(1, pages + 1):
        params = urllib.parse.urlencode({
            "_nkw": query,
            "_ipg": str(per_page),   # items per page
            "_pgn": str(pg),         # page number
            "LH_PrefLoc": "1",       # prefer US-located items
        })
        html, err = _http_get_text(f"https://www.ebay.com/sch/i.html?{params}")
        if err:
            return (results or None), (None if results else err)
        items = _parse_ebay_search(html, query, category)
        new = 0
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            results.append(it)
            new += 1
        if new < 10:            # last page reached
            break
        if pg < pages:
            time.sleep(1.2)     # be gentle between page requests
    return results[:limit], None


# Precompiled patterns for the results markup.
_RE_PRICE = re.compile(r'class="s-item__price"[^>]*>(.*?)</span>', re.S)
_RE_TITLE = re.compile(r'class="s-item__title"[^>]*>(.*?)</(?:div|h3|span)>\s*</(?:div|h3|a)>', re.S)
_RE_TITLE_FALLBACK = re.compile(r'class="s-item__title"[^>]*>(.*?)</div>', re.S)
_RE_LINK = re.compile(r'class="s-item__link"[^>]*href="([^"]+)"')
_RE_IMG = re.compile(r'<img[^>]+(?:data-src|src)="(https?://[^"]+)"')
_RE_ITEMID = re.compile(r'/itm/(?:[^/]+/)?(\d{6,})')
_RE_BIDS = re.compile(r's-item__bid[^"]*"[^>]*>(.*?)</span>', re.S)
_RE_TIMELEFT = re.compile(r's-item__time-left"[^>]*>(.*?)</span>', re.S)
_RE_SUBTITLE = re.compile(r'class="s-item__subtitle"[^>]*>(.*?)</div>', re.S)
_RE_TAGSTRIP = re.compile(r'<[^>]+>')
_RE_MONEY = re.compile(r'([\d][\d,]*(?:\.\d{2})?)')


def _strip_tags(s):
    return re.sub(r"\s+", " ", _RE_TAGSTRIP.sub(" ", s)).strip()


def _money_from_text(text):
    """First dollar figure in a price cell ('$1,234.56', ranges -> low end)."""
    m = _RE_MONEY.search(text.replace("&nbsp;", " "))
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", "")), 2)
    except ValueError:
        return None


def _timeleft_to_epoch(text):
    """'1d 5h left' / '5h 12m' / '45m' -> epoch seconds, or None."""
    t = _strip_tags(text).lower()
    d = re.search(r"(\d+)\s*d", t)
    h = re.search(r"(\d+)\s*h", t)
    mi = re.search(r"(\d+)\s*m", t)
    if not (d or h or mi):
        return None
    secs = (int(d.group(1)) * 86400 if d else 0) + \
           (int(h.group(1)) * 3600 if h else 0) + \
           (int(mi.group(1)) * 60 if mi else 0)
    return time.time() + secs if secs > 0 else None


def _parse_ebay_search(html, query, category):
    """Parse eBay search-results HTML into normalized listings (stdlib only)."""
    items = []
    # One "s-item__wrapper" per result card; the first chunk is page chrome.
    for chunk in html.split("s-item__wrapper")[1:]:
        link_m = _RE_LINK.search(chunk)
        if not link_m:
            continue
        url = link_m.group(1).split("?")[0]
        id_m = _RE_ITEMID.search(url) or _RE_ITEMID.search(chunk)
        item_id = f"ebay-{id_m.group(1)}" if id_m else "ebay-" + url

        title_m = _RE_TITLE.search(chunk) or _RE_TITLE_FALLBACK.search(chunk)
        title = _strip_tags(title_m.group(1)) if title_m else ""
        # eBay salts a placeholder card and "New Listing" tags into titles.
        title = re.sub(r"^\s*(new listing|sponsored)\s*", "", title, flags=re.I).strip()
        if not title or title.lower() in ("shop on ebay", "shop on eBay".lower()):
            continue

        price_m = _RE_PRICE.search(chunk)
        price = _money_from_text(_strip_tags(price_m.group(1))) if price_m else None
        if price is None:
            continue

        img_m = _RE_IMG.search(chunk)
        image = img_m.group(1) if img_m else None

        bids_txt = _strip_tags(_RE_BIDS.search(chunk).group(1)) if _RE_BIDS.search(chunk) else ""
        is_auction = "bid" in bids_txt.lower()
        bid_count = None
        bc = re.search(r"(\d+)", bids_txt)
        if bc:
            bid_count = int(bc.group(1))
        end_time = None
        tl_m = _RE_TIMELEFT.search(chunk)
        if tl_m:
            end_time = _timeleft_to_epoch(tl_m.group(1))
            if end_time:
                is_auction = True  # eBay shows time-left on timed auction listings

        sub_m = _RE_SUBTITLE.search(chunk)
        condition = _strip_tags(sub_m.group(1)) if sub_m else None

        items.append({
            "source": "ebay",
            "id": item_id,
            "title": title,
            "price": price,
            "bin_price": None if is_auction else price,
            "currency": "USD",
            "image": image,
            "url": url,
            "condition": condition,
            "seller": None,
            "buying_options": ["AUCTION"] if is_auction else ["FIXED_PRICE"],
            "is_auction": is_auction,
            "bid_count": bid_count,
            "end_time": end_time,
            "category": category,
            "sport": _guess_sport(title),
            "query": query,
        })
    return items


# Source registry — add adapters here as they become available.
# Each adapter: fn(query, category, limit) -> (list_of_normalized_items, error)
# needs(): whether this source is currently usable given config/credentials.
SOURCES = {
    # Official Browse API — used automatically when eBay keys are configured.
    "ebay_api": {"fetch": fetch_ebay, "needs": lambda: _ebay_live()},
    # Public search scrape — the default when no keys are set.
    "ebay_public": {"fetch": fetch_ebay_public,
                    "needs": lambda: (not _ebay_live()) and public_ebay_enabled()},
}


# ---------------------------------------------------------------- valuation

def reference_price(candidates, watch_entry):
    """Median asking price of clean Buy-It-Now comps == our market proxy.

    Returns (reference_price, confidence_count). Falls back to a hand-set
    ref_price on the watchlist entry when live comps are too thin.
    """
    bin_prices = [
        c["price"] for c in candidates
        if c.get("bin_price") is not None
        and not c.get("is_auction")
        and c["price"] and c["price"] >= min_price()
        and not _has_red_flag(c["title"])
        and _matches_category(c["title"], c["category"])
    ]
    if len(bin_prices) >= min_comps():
        # Trim the wildest 10% each side so one absurd listing can't skew it.
        bin_prices.sort()
        k = int(len(bin_prices) * 0.10)
        trimmed = bin_prices[k: len(bin_prices) - k] or bin_prices
        return round(statistics.median(trimmed), 2), len(bin_prices)
    hint = watch_entry.get("ref_price")
    if hint:
        try:
            return round(float(hint), 2), 0
        except (TypeError, ValueError):
            pass
    return None, len(bin_prices)


def score_deal(discount, savings, confidence, is_auction, ending_soon):
    """Blend discount %, dollar savings, and comp confidence into 0-100ish."""
    score = discount * 100.0
    score += min(savings, 500) / 20.0            # up to +25 for big dollar wins
    score += min(confidence, 20) * 0.6           # up to +12 for well-supported refs
    if is_auction and ending_soon:
        score += 8                               # act-now bonus
    return round(score, 1)


def evaluate(candidates, watch_entry):
    """Turn one search's candidates into flagged deals."""
    reference, confidence = reference_price(candidates, watch_entry)
    if not reference:
        return [], reference, confidence
    threshold = reference * (1 - min_discount())
    now = time.time()
    deals = []
    for c in candidates:
        price = c.get("price")
        if not price or price < min_price():
            continue
        if _has_red_flag(c["title"]) or not _matches_category(c["title"], c["category"]):
            continue
        # A price under 8% of reference is almost always a mislabel/accessory/scam.
        if price < reference * 0.08:
            continue
        if price > threshold:
            continue

        ending_soon = False
        if c["is_auction"]:
            if not c.get("end_time"):
                continue  # can't judge urgency, skip to avoid early-auction noise
            hours_left = (c["end_time"] - now) / 3600.0
            if hours_left < 0 or hours_left > auction_window_hours():
                continue
            ending_soon = True

        discount = round((reference - price) / reference, 4)
        savings = round(reference - price, 2)
        deal = dict(c)
        deal.update({
            "reference": reference,
            "confidence": confidence,
            "discount": discount,
            "est_savings": savings,
            "ending_soon": ending_soon,
            "score": score_deal(discount, savings, confidence, c["is_auction"], ending_soon),
        })
        deals.append(deal)
    return deals, reference, confidence


# ---------------------------------------------------------------- persistence

def read_deals():
    if not os.path.exists(DEALS_PATH):
        return []
    try:
        with open(DEALS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write_deals(deals):
    tmp = DEALS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(deals, f, indent=2)
    os.replace(tmp, DEALS_PATH)


def merge_deals(found):
    """Merge freshly-found deals into the store, deduped by id, and prune."""
    now = time.time()
    with _deals_lock:
        existing = {d["id"]: d for d in read_deals()}
        for d in found:
            prev = existing.get(d["id"])
            if prev:
                d["first_seen"] = prev.get("first_seen", now)
                d["seen_count"] = prev.get("seen_count", 1) + 1
            else:
                d["first_seen"] = now
                d["seen_count"] = 1
            d["last_seen"] = now
            d["status"] = "active"
            existing[d["id"]] = d

        cutoff = now - retention_days() * 86400
        kept = []
        for d in existing.values():
            # drop finished auctions and long-unseen deals
            if d.get("is_auction") and d.get("end_time") and d["end_time"] < now:
                continue
            if d.get("last_seen", 0) < cutoff:
                continue
            kept.append(d)
        kept.sort(key=lambda x: (x.get("score", 0), x.get("discount", 0)), reverse=True)
        _write_deals(kept)
        return kept


# ---------------------------------------------------------------- demo mode

_DEMO_TEMPLATES = [
    ("2024 Topps Chrome Baseball Hobby Box — Factory Sealed", "sealed_box", "Baseball", "⚾", 300),
    ("2023-24 Panini Prizm Basketball Hobby Box Sealed", "sealed_box", "Basketball", "🏀", 520),
    ("2023 Panini Prizm Football Hobby Box — Unopened", "sealed_box", "Football", "🏈", 470),
    ("2024 Bowman Chrome Baseball Hobby Box Factory Sealed", "sealed_box", "Baseball", "⚾", 260),
    ("Vintage 1980s Baseball Card Lot — Estate Shoebox (500+)", "card_lot", "Baseball", "⚾", 180),
    ("Basketball Card Collection Lot — Storage Unit Find", "card_lot", "Basketball", "🏀", 240),
    ("Mixed Sports Card Lot — Old Collection, Unsearched", "card_lot", "Mixed", "🎴", 150),
    ("Signed Baseball Memorabilia Lot — HOF Autographs", "memorabilia", "Baseball", "✍️", 400),
    ("Game-Used Patch Relic Lot — Multiple Players", "memorabilia", "Football", "🏈", 320),
    ("1970s Unopened Wax Box — Vintage Baseball", "sealed_box", "Baseball", "⚾", 900),
]


def _demo_deals():
    """A realistic, lightly-varying set of deals for demo mode."""
    rng = random.Random(int(time.time() // (interval_min() * 60)))  # changes each cycle
    now = time.time()
    out = []
    for i, (title, cat, sport, icon, ref) in enumerate(_DEMO_TEMPLATES):
        reference = round(ref * rng.uniform(0.95, 1.08), 2)
        discount = rng.uniform(min_discount(), 0.55)
        price = round(reference * (1 - discount), 2)
        is_auction = rng.random() < 0.35
        end_time = now + rng.uniform(1, auction_window_hours()) * 3600 if is_auction else None
        savings = round(reference - price, 2)
        confidence = rng.randint(min_comps(), 22)
        out.append({
            "source": "demo",
            "id": f"demo-{i}",
            "title": title,
            "price": price,
            "bin_price": None if is_auction else price,
            "currency": "USD",
            "image": None,
            "icon": icon,
            "url": "https://www.ebay.com/sch/i.html?_nkw=" +
                   urllib.parse.quote(title),
            "condition": "New (Sealed)" if cat == "sealed_box" else "Used",
            "seller": rng.choice(["cardvault_pro", "estate_finds_llc", "hobbybox_deals",
                                   "midwest_collectibles", "atticfind_auctions"]),
            "buying_options": ["AUCTION"] if is_auction else ["FIXED_PRICE"],
            "is_auction": is_auction,
            "bid_count": rng.randint(0, 14) if is_auction else None,
            "end_time": end_time,
            "category": cat,
            "sport": sport,
            "query": f"demo:{cat}",
            "reference": reference,
            "confidence": confidence,
            "discount": round(discount, 4),
            "est_savings": savings,
            "ending_soon": bool(is_auction),
            "score": score_deal(discount, savings, confidence, is_auction, is_auction),
        })
    return out


# ---------------------------------------------------------------- scanning

def run_scan_once():
    """One full pass over the watchlist across all enabled sources."""
    if not _scan_lock.acquire(blocking=False):
        return {"skipped": "a scan is already running"}
    started = time.time()
    _state["scanning_now"] = True
    _state["last_run_started"] = started
    errors = []
    all_found = []
    try:
        live_sources = [name for name, s in SOURCES.items() if s["needs"]()]
        _state["sources"] = live_sources
        _state["mode"] = "live" if live_sources else "demo"

        if not live_sources:
            all_found = _demo_deals()
        else:
            watchlist = load_watchlist()
            for entry in watchlist:
                query = entry["query"]
                category = entry.get("category", "card_lot")
                candidates = []
                for name in live_sources:
                    items, err = SOURCES[name]["fetch"](query, category, per_query_limit())
                    if err:
                        errors.append(f"{name}/{query}: {err}")
                    if items:
                        candidates.extend(items)
                if not candidates:
                    continue
                for c in candidates:  # honor the entry's intended sport when known
                    if entry.get("sport") and entry["sport"] != "Mixed" and c["sport"] == "Mixed":
                        c["sport"] = entry["sport"]
                deals, _ref, _conf = evaluate(candidates, entry)
                all_found.extend(deals)

        # de-dupe within this run (same item can match several searches)
        best = {}
        for d in all_found:
            cur = best.get(d["id"])
            if not cur or d.get("score", 0) > cur.get("score", 0):
                best[d["id"]] = d
        kept = merge_deals(list(best.values()))

        _state["runs"] += 1
        _state["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _state["last_duration_sec"] = round(time.time() - started, 1)
        _state["last_deals_found"] = len(best)
        _state["last_error"] = "; ".join(errors[:3]) if errors else None
        return {
            "deals_found": len(best),
            "total_active": len(kept),
            "errors": errors,
            "mode": _state["mode"],
        }
    finally:
        _state["scanning_now"] = False
        _scan_lock.release()


def _loop():
    _state["running"] = True
    # small initial delay so the web server is up and responsive first
    time.sleep(3)
    while True:
        try:
            run_scan_once()
        except Exception as e:
            _state["last_error"] = f"scan crashed: {e}"
            print("[scout] scan crashed:", e)
        wait = interval_min() * 60
        _state["next_run_eta"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time() + wait))
        time.sleep(wait)


# ---------------------------------------------------------------- public API

def init(cfg, http_json, ebay_token, ebay_live):
    global _cfg, _http_json, _ebay_token, _ebay_live
    _cfg = cfg
    _http_json = http_json
    _ebay_token = ebay_token
    _ebay_live = ebay_live
    _state["mode"] = "live" if (ebay_live() or public_ebay_enabled()) else "demo"


def start():
    """Start the background scan loop (idempotent)."""
    if _state["running"]:
        return
    if not autostart():
        print("[scout] autostart disabled — waiting for manual scans")
        return
    t = threading.Thread(target=_loop, name="scout-loop", daemon=True)
    t.start()


def trigger_scan_async():
    """Kick off one scan in the background (for the manual 'Scan now' button)."""
    if _state["scanning_now"]:
        return False
    threading.Thread(target=run_scan_once, name="scout-manual", daemon=True).start()
    return True


def get_status():
    st = dict(_state)
    st.update({
        "interval_min": interval_min(),
        "min_discount": min_discount(),
        "min_comps": min_comps(),
        "auction_window_hours": auction_window_hours(),
        "watchlist_size": len(load_watchlist()),
        "active_deals": len(read_deals()),
    })
    return st


def get_deals(category=None, sport=None, min_disc=None, source=None, limit=200):
    deals = read_deals()
    if category and category != "all":
        deals = [d for d in deals if d.get("category") == category]
    if sport and sport != "all":
        deals = [d for d in deals if d.get("sport") == sport]
    if source and source != "all":
        deals = [d for d in deals if d.get("source") == source]
    if min_disc:
        try:
            md = float(min_disc)
            deals = [d for d in deals if (d.get("discount", 0) * 100) >= md]
        except ValueError:
            pass
    deals.sort(key=lambda x: (x.get("score", 0), x.get("discount", 0)), reverse=True)
    return deals[:limit]
