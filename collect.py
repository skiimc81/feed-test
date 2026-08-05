#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
कलेक्टर — GitHub Actions पर चलता है।
सारे फ़ीड (+ Google News) पढ़कर एक news.json बनाता है, जिसे बाद में
आपका साझा डेस्क (Cloudflare या GitHub Pages) दिखाएगा।
जो फ़ीड क्लाउड पर ब्लॉक हों, उनकी खबरें Google News के रास्ते आ जाती हैं।
"""
import json, re, html, difflib
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, feedparser

FEEDS = [
    # ---------- Moneycontrol ----------
    # ⚠ Moneycontrol कड़ी बॉट-सुरक्षा (Akamai) के पीछे है — सामान्य तरीक़े से नहीं खुलता,
    #   इसलिए हटा दिया। इसकी ज़्यादातर खबरें Mint/Business Standard/ET में मिल जाती हैं।
    #   (चाहें तो नीचे की लाइनें अनकमेंट करके ख़ुद आज़मा सकते हैं।)
    # {"name": "Moneycontrol", "url": "https://www.moneycontrol.com/rss/latestnews.xml", "cat": "corp", "lang": "en", "region": "india"},


    # ---------- Mint / LiveMint (अंग्रेज़ी, भारत) ----------
    {"name": "Mint", "url": "https://www.livemint.com/rss/markets",   "cat": "market", "lang": "en", "region": "india"},
    {"name": "Mint", "url": "https://www.livemint.com/rss/money",     "cat": "pf",     "lang": "en", "region": "india"},
    {"name": "Mint", "url": "https://www.livemint.com/rss/industry",  "cat": "corp",   "lang": "en", "region": "india"},
    {"name": "Mint", "url": "https://www.livemint.com/rss/companies", "cat": "corp",   "lang": "en", "region": "india"},
    {"name": "Mint", "url": "https://www.livemint.com/rss/economy",   "cat": "eco",    "lang": "en", "region": "india"},

    # ---------- Business Standard (अंग्रेज़ी, भारत) ----------
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/markets-106.rss",            "cat": "market", "lang": "en", "region": "india"},
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/economy-102.rss",            "cat": "eco",    "lang": "en", "region": "india"},
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/finance-103.rss",            "cat": "bank",   "lang": "en", "region": "india"},
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/companies-101.rss",          "cat": "corp",   "lang": "en", "region": "india"},
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/home_page_top_stories.rss",  "cat": "corp",   "lang": "en", "region": "india"},
    {"name": "Business Standard", "url": "https://www.business-standard.com/rss/latest.rss",                 "cat": "corp",   "lang": "en", "region": "india"},

    # ---------- Economic Times (अंग्रेज़ी, भारत) ----------
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",              "cat": "corp",   "lang": "en", "region": "india"},
    {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",     "cat": "market", "lang": "en", "region": "india"},

    # ---------- अन्य भारतीय (अंग्रेज़ी) ----------
    {"name": "BusinessLine",       "url": "https://www.thehindubusinessline.com/feeder/default.rss", "cat": "corp", "lang": "en", "region": "india"},
    # Financial Express हटाया (नहीं खुला — Indian Express समूह की सुरक्षा)।

    # ---------- हिंदी फ़ीड ----------
    # अमर उजाला के फ़ीड भरोसेमंद पाए गए, इसलिए इन्हीं पर टिके हैं।
    # (जनसत्ता, नवभारत टाइम्स, ज़ी बिज़नेस — सब ब्लॉक/खाली मिले, इसलिए हटाए।)
    {"name": "अमर उजाला",       "url": "https://www.amarujala.com/rss/business.xml",       "cat": "corp",   "lang": "hi", "region": "india"},
    {"name": "अमर उजाला टेक",   "url": "https://www.amarujala.com/rss/technology.xml",     "cat": "tech",   "lang": "hi", "region": "india"},
    # 'अमर उजाला ताज़ा' (breaking-news.xml) हटाया — वह बिज़नेस नहीं, हर तरह की खबर (क्राइम/राजनीति) लाता था।
    # — नीचे वाले उपयोगकर्ता द्वारा जाँचे हुए, चलते हुए हिंदी फ़ीड —
    {"name": "TV9 हिंदी",       "url": "https://www.tv9hindi.com/business/feed",           "cat": "corp",   "lang": "hi", "region": "india"},
    {"name": "Money9",          "url": "https://www.money9live.com/feed/",                 "cat": "pf",     "lang": "hi", "region": "india"},
    {"name": "दैनिक भास्कर",    "url": "https://www.bhaskar.com/rss-v1--category-1742.xml", "cat": "corp",   "lang": "hi", "region": "india"},
    {"name": "दैनिक जागरण",     "url": "http://rss.jagran.com/rss/news/business.xml",       "cat": "corp",   "lang": "hi", "region": "india"},
    # — हिंदी Business Standard, हिंदी Moneycontrol, लाइव हिन्दुस्तान —
    {"name": "लाइव हिन्दुस्तान",   "url": "https://api.livehindustan.com/feeds/rss/business/rssfeed.xml", "cat": "corp",   "lang": "hi", "region": "india"},
    {"name": "BS हिंदी अर्थ",    "url": "https://hindi.business-standard.com/rss/economy.xml",           "cat": "eco",    "lang": "hi", "region": "india"},
    {"name": "BS हिंदी मनी",     "url": "https://hindi.business-standard.com/rss/money.xml",             "cat": "pf",     "lang": "hi", "region": "india"},
    {"name": "BS हिंदी ताज़ा",   "url": "https://hindi.business-standard.com/rss/latest-news.xml",       "cat": "corp",   "lang": "hi", "region": "india"},
    {"name": "MC हिंदी ताज़ा",   "url": "https://hindi.moneycontrol.com/news/rss/feeds/latest-news.xml", "cat": "corp",   "lang": "hi", "region": "india"},
    {"name": "MC हिंदी मनी",     "url": "https://hindi.moneycontrol.com/news/rss/feeds/your-money.xml",  "cat": "pf",     "lang": "hi", "region": "india"},
    {"name": "MC हिंदी बाज़ार",  "url": "https://hindi.moneycontrol.com/news/rss/feeds/markets.xml",     "cat": "market", "lang": "hi", "region": "india"},

    # ---------- वैश्विक (अंग्रेज़ी) ----------
    # Reuters/Bloomberg के सार्वजनिक RSS अब सीमित हैं; CNBC World रखा है।
    {"name": "CNBC World", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", "cat": "global", "lang": "en", "region": "intl"},
    {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "cat": "market", "lang": "en", "region": "intl"},

    {"name": "GN·RBI/महँगाई", "url": "https://news.google.com/rss/search?q=RBI%20%E0%A4%B0%E0%A5%87%E0%A4%AA%E0%A5%8B%20%E0%A4%B0%E0%A5%87%E0%A4%9F%20%E0%A4%AE%E0%A4%B9%E0%A4%82%E0%A4%97%E0%A4%BE%E0%A4%88&hl=hi-IN&gl=IN&ceid=IN:hi", "cat": "rbi", "lang": "hi", "region": "india"},
    {"name": "GN·RBI/महँगाई EN", "url": "https://news.google.com/rss/search?q=RBI%20repo%20rate%20inflation%20India&hl=en-IN&gl=IN&ceid=IN:en", "cat": "rbi", "lang": "en", "region": "india"},
    {"name": "GN·बाज़ार", "url": "https://news.google.com/rss/search?q=%E0%A4%B6%E0%A5%87%E0%A4%AF%E0%A4%B0%20%E0%A4%AC%E0%A4%BE%E0%A4%9C%E0%A4%BE%E0%A4%B0%20%E0%A4%B8%E0%A5%87%E0%A4%82%E0%A4%B8%E0%A5%87%E0%A4%95%E0%A5%8D%E0%A4%B8%20%E0%A4%A8%E0%A4%BF%E0%A4%AB%E0%A5%8D%E0%A4%9F%E0%A5%80&hl=hi-IN&gl=IN&ceid=IN:hi", "cat": "market", "lang": "hi", "region": "india"},
    {"name": "GN·बाज़ार EN", "url": "https://news.google.com/rss/search?q=sensex%20nifty%20stock%20market%20India&hl=en-IN&gl=IN&ceid=IN:en", "cat": "market", "lang": "en", "region": "india"},
    {"name": "GN·GST", "url": "https://news.google.com/rss/search?q=GST%20%E0%A4%9C%E0%A5%80%E0%A4%8F%E0%A4%B8%E0%A4%9F%E0%A5%80%20%E0%A4%9F%E0%A5%88%E0%A4%95%E0%A5%8D%E0%A4%B8&hl=hi-IN&gl=IN&ceid=IN:hi", "cat": "tax", "lang": "hi", "region": "india"},
    {"name": "GN·GST EN", "url": "https://news.google.com/rss/search?q=GST%20tax%20India&hl=en-IN&gl=IN&ceid=IN:en", "cat": "tax", "lang": "en", "region": "india"},
    {"name": "GN·IPO", "url": "https://news.google.com/rss/search?q=IPO%20%E0%A4%86%E0%A4%88%E0%A4%AA%E0%A5%80%E0%A4%93%20%E0%A4%B6%E0%A5%87%E0%A4%AF%E0%A4%B0%20%E0%A4%AC%E0%A4%BE%E0%A4%9C%E0%A4%BE%E0%A4%B0&hl=hi-IN&gl=IN&ceid=IN:hi", "cat": "ipo", "lang": "hi", "region": "india"},
    {"name": "GN·IPO EN", "url": "https://news.google.com/rss/search?q=IPO%20India%20listing&hl=en-IN&gl=IN&ceid=IN:en", "cat": "ipo", "lang": "en", "region": "india"},
    {"name": "GN·सोना-चाँदी", "url": "https://news.google.com/rss/search?q=%E0%A4%B8%E0%A5%8B%E0%A4%A8%E0%A4%BE%20%E0%A4%9A%E0%A4%BE%E0%A4%82%E0%A4%A6%E0%A5%80%20%E0%A4%95%E0%A5%80%E0%A4%AE%E0%A4%A4&hl=hi-IN&gl=IN&ceid=IN:hi", "cat": "commodity", "lang": "hi", "region": "india"},
    {"name": "GN·सोना-चाँदी EN", "url": "https://news.google.com/rss/search?q=gold%20silver%20price%20India&hl=en-IN&gl=IN&ceid=IN:en", "cat": "commodity", "lang": "en", "region": "india"},
    # --- और जाँचे हुए फ़ीड (उपयोगकर्ता द्वारा) ---
    {"name": "Business Standard PR", "url": "https://www.business-standard.com/rss/content/press-releases-ani-22304.rss", "cat": "corp", "lang": "en", "region": "india"},
    {"name": "Business Standard PF", "url": "https://www.business-standard.com/rss/finance/personal-finance-10313.rss", "cat": "pf", "lang": "en", "region": "india"},
    {"name": "MC हिंदी निवेश", "url": "https://hindi.moneycontrol.com/news/rss/feeds/business/investment.xml", "cat": "pf", "lang": "hi", "region": "india"},
    {"name": "BS हिंदी टेलीकॉम", "url": "https://hindi.business-standard.com/rss/companies/telecom.xml", "cat": "corp", "lang": "hi", "region": "india"},
    {"name": "ET Wealth", "url": "https://economictimes.indiatimes.com/wealth/rssfeeds/837555174.cms", "cat": "pf", "lang": "en", "region": "india"},
    {"name": "दैनिक भास्कर 1051", "url": "https://www.bhaskar.com/rss-v1--category-1051.xml", "cat": "corp", "lang": "hi", "region": "india"},
    {"name": "दैनिक भास्कर 5707", "url": "https://www.bhaskar.com/rss-v1--category-5707.xml", "cat": "corp", "lang": "hi", "region": "india"},
    {"name": "Hindustan Times", "url": "https://www.hindustantimes.com/feeds/rss/business/rssfeed.xml", "cat": "corp", "lang": "en", "region": "india"},
    {"name": "LiveMint News", "url": "https://www.livemint.com/rss/news", "cat": "corp", "lang": "en", "region": "india"},
]

CATEGORY_RULES = [
    ("rbi",       ["rbi", "repo rate", "repo ", "monetary policy", "mpc", "reserve bank",
                   "रिज़र्व बैंक", "रेपो", "मौद्रिक नीति"]),
    ("ipo",       ["ipo", "drhp", "listing gains", "issue price", "इश्यू", "आईपीओ", "लिस्टिंग"]),
    ("tax",       ["gst", "income tax", "cbdt", "tax ", "जीएसटी", "आयकर", "टैक्स"]),
    ("commodity", ["gold", "silver", "crude", "commodity", "bullion",
                   "सोना", "चाँदी", "चांदी", "कच्चा तेल", "कमोडिटी"]),
    ("startup",   ["startup", "funding", "series a", "series b", "venture", "raises $",
                   "स्टार्टअप", "फंडिंग", "फ़ंडिंग"]),
    ("auto",      ["auto ", "vehicle", "car sales", "ev ", "two-wheeler",
                   "वाहन", "ऑटो", "इलेक्ट्रिक वाहन"]),
    ("realty",    ["real estate", "housing", "property", "realty",
                   "रियल एस्टेट", "संपत्ति", "मकान", "आवास"]),
    ("pf",        ["mutual fund", "insurance", "personal finance", "savings", "fixed deposit",
                   " sip ", "म्यूचुअल फंड", "बीमा", "पर्सनल फाइनेंस", "सावधि जमा"]),
    ("bank",      ["bank", "loan", "deposit", "npa", "lending", "credit growth",
                   "बैंक", "कर्ज़", "कर्ज", "ऋण", "जमा"]),
    ("market",    ["sensex", "nifty", "stock", "share", " bse ", " nse ", "equit", "market",
                   "सेंसेक्स", "निफ्टी", "शेयर", "बाज़ार", "बाजार"]),
    ("global",    [" fed ", "tariff", "trump", "china", "u.s.", "us economy", "europe", "ecb",
                   "फेड", "टैरिफ", "चीन", "अमेरिका", "वैश्विक"]),
    ("tech",      ["ai ", "artificial intelligence", "chip", "semiconductor", "tech ",
                   "एआई", "टेक", "चिप", "सेमीकंडक्टर"]),
    ("eco",       ["gdp", "inflation", "cpi", "wpi", "economy", "fiscal", "growth",
                   "जीडीपी", "महँगाई", "महंगाई", "अर्थव्यवस्था", "वृद्धि"]),
    ("corp",      ["profit", "revenue", "results", "quarter", "q1", "q2", "q3", "q4",
                   "कंपनी", "मुनाफा", "नतीजे", "तिमाही"]),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
}

def clean(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    return html.unescape(t).strip()

def detect_category(default, title, summary):
    text = " " + (title + " " + summary).lower() + " "
    for cat, words in CATEGORY_RULES:
        if any(w in text for w in words):
            return cat
    return default

def rel_time(pp):
    if not pp: return "अभी"
    try: dt = datetime(*pp[:6], tzinfo=timezone.utc)
    except Exception: return "अभी"
    m = (datetime.now(timezone.utc) - dt).total_seconds() / 60
    if m < 1: return "अभी"
    if m < 60: return f"{int(m)} मिनट पहले"
    if m < 1440: return f"{int(m//60)} घंटे पहले"
    return f"{int(m//1440)} दिन पहले"

def age_min(pp):
    if not pp: return 9999
    try:
        dt = datetime(*pp[:6], tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception: return 9999

def parse_entries(feed):
    try:
        r = requests.get(feed["url"], headers=HEADERS, timeout=20, allow_redirects=True)
        if r.status_code == 200 and r.content:
            p = feedparser.parse(r.content)
            if p.entries: return p.entries
    except Exception: pass
    try:
        p = feedparser.parse(feed["url"], request_headers=HEADERS)
        if p.entries: return p.entries
    except Exception: pass
    return None

def fetch_one(feed):
    ents = parse_entries(feed)
    if not ents: return feed, [], False
    out = []
    for e in ents[:25]:
        title = clean(getattr(e, "title", ""))
        if not title: continue
        summ = clean(getattr(e, "summary", getattr(e, "description", "")))[:280]
        pp = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        out.append({
            "src": feed["name"], "lang": feed["lang"], "region": feed["region"],
            "cat": detect_category(feed["cat"], title, summ),
            "h": title, "p": summ, "url": getattr(e, "link", "#"),
            "time": rel_time(pp), "_age": age_min(pp),
        })
    return feed, out, True

def dedupe(items):
    for it in items: it["cluster"] = ""
    cid = 0
    for i in range(len(items)):
        if items[i]["cluster"]: continue
        grp = [i]; a = items[i]["h"].lower()
        for j in range(i+1, len(items)):
            if items[j]["cluster"]: continue
            if difflib.SequenceMatcher(None, a, items[j]["h"].lower()).ratio() > 0.62:
                grp.append(j)
        if len(grp) > 1:
            cid += 1
            for g in grp: items[g]["cluster"] = f"c{cid}"
    return items

def main():
    all_items, ok, bad = [], [], []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(fetch_one, f) for f in FEEDS]
        for fu in as_completed(futs):
            feed, items, good = fu.result()
            all_items.extend(items)
            (ok if good else bad).append(feed["name"])
    all_items.sort(key=lambda x: x["_age"])
    for idx, it in enumerate(all_items, 1):
        it["id"] = idx
        it["prio"] = "break" if it["_age"] < 45 else ""
        del it["_age"]
    all_items = dedupe(all_items)

    data = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(all_items),
        "items": all_items,
    }
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    print("=" * 56)
    print(f"  कलेक्टर पूरा — {len(all_items)} खबरें · {len(ok)} फ़ीड चले · {len(bad)} नहीं")
    print("=" * 56)
    for n in bad: print(f"  ✗ {n}")
    print("=" * 56)

if __name__ == "__main__":
    main()
