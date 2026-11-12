"""جمع الأخبار من المصادر وتصنيفها بالقواعد.

لكل مصدر: يجرّب روابط RSS بالترتيب، وإن فشلت كلها يقرأ صفحات الأخبار.
يحتفظ فقط بالأخبار المرتبطة بالرؤية (relevant) أو المحتملة (uncertain)،
ويسجّل كل رابط رآه في data/state/seen.json حتى لا يُعالَج مرتين.
لا يُحفظ نص الخبر الكامل: العنوان ومقتطف قصير ورابط المصدر فقط.

التشغيل:  python scripts/collect.py [--source ID] [--no-body]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

import feedparser
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # لمصادر verifySSL=false فقط

from common import (CONFIG, STATE, article_id, classification_fields, clean_text, legislation_boost, load_articles, now_iso,
                    read_json, save_articles, title_key, url_key, write_json)
from taxonomy.classify import classify

UA = "Mozilla/5.0 (compatible; VisionNewsMonitor/1.0; +https://github.com/)"
TIMEOUT = 25
SEEN_DAYS = 90            # مدة تذكّر الروابط التي رُئيت
EXCLUDED_DAYS = 14        # مدة حفظ سجل المستبعد للمراجعة
MAX_ITEMS_PER_SOURCE = 120
MAX_BODY_FETCHES = 60     # حد قراءة صفحات الأخبار في التشغيلة الواحدة
EXCERPT_CHARS = 400

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})


def get(url: str, verify: bool = True) -> requests.Response:
    last = None
    for attempt in range(2):
        try:
            r = session.get(url, timeout=TIMEOUT, allow_redirects=True, verify=verify)
            if r.status_code >= 500 and attempt == 0:
                time.sleep(3)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # إعادة محاولة واحدة لأخطاء الشبكة
            last = e
            time.sleep(3)
    raise last if last else RuntimeError("fetch failed")


def parse_date(entry) -> str | None:
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except (TypeError, ValueError):
                pass
    return None


def from_feed(url: str, source: dict) -> list[dict]:
    r = get(url, source.get("verifySSL", True))
    feed = feedparser.parse(r.content)
    via_google = "news.google.com" in url
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"ملف RSS غير صالح: {type(feed.bozo_exception).__name__}")
    items = []
    for e in feed.entries[:MAX_ITEMS_PER_SOURCE]:
        title = clean_text(e.get("title", ""))
        link = e.get("link", "")
        if not title or not link:
            continue
        source_name = None
        if source.get("aggregator") or via_google:
            # عناوين Google News تنتهي بـ " - اسم المصدر"
            src = e.get("source", {})
            source_name = (src.get("title") if isinstance(src, dict) else None)
            m = re.match(r"^(.*)\s+-\s+([^-]{2,60})$", title)
            if m:
                title, source_name = m.group(1).strip(), source_name or m.group(2).strip()
        summary = clean_text(e.get("summary", "") or e.get("description", ""))
        items.append({"title": title, "url": link, "summary": summary, "publishedAt": parse_date(e),
                      "publisher": source_name})
    return items


def from_page(url: str, pattern: str, verify: bool = True) -> list[dict]:
    r = get(url, verify)
    soup = BeautifulSoup(r.text, "html.parser")
    rx = re.compile(pattern) if pattern else None
    host = urlsplit(r.url).hostname or ""
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(r.url, a["href"])
        text = clean_text(a.get_text(" "))
        if len(text) < 25 or href in seen:
            continue
        if rx and not rx.search(href):
            continue
        if not rx and (urlsplit(href).hostname or "") != host:
            continue
        seen.add(href)
        items.append({"title": text, "url": href, "summary": "", "publishedAt": None, "publisher": None})
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


def fetch_body(url: str) -> str:
    """نص الخبر لتحسين التصنيف فقط؛ لا يُحفظ."""
    try:
        r = get(url)
    except Exception:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    paras = [clean_text(p.get_text(" ")) for p in soup.find_all("p")]
    return "\n".join(p for p in paras if len(p) > 40)[:6000]


def load_sources(only: str | None) -> list[dict]:
    cfg = read_json(CONFIG / "sources.json", {"sources": []})
    return [s for s in cfg["sources"] if s.get("active", True) and (not only or s["id"] == only)]


def collect_source(source: dict) -> tuple[list[dict], dict]:
    status = {"method": None, "url": None, "errors": []}
    for url in source.get("feeds", []):
        try:
            items = from_feed(url, source)
            if items:
                status.update(method="rss", url=url)
                return items, status
            status["errors"].append(f"{url}: لا عناصر")
        except Exception as e:
            status["errors"].append(f"{url}: {short_error(e)}")
    for url in source.get("pages", []):
        try:
            items = from_page(url, source.get("linkPattern", ""), source.get("verifySSL", True))
            if items:
                status.update(method="page", url=url)
                return items, status
            status["errors"].append(f"{url}: لم يُعثر على روابط أخبار")
        except Exception as e:
            status["errors"].append(f"{url}: {short_error(e)}")
    return [], status


def short_error(e: Exception) -> str:
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return f"HTTP {e.response.status_code}"
    return f"{type(e).__name__}: {str(e)[:120]}"


def prune(seen: dict, excluded: list) -> tuple[dict, list]:
    cut_seen = (datetime.now(timezone.utc) - timedelta(days=SEEN_DAYS)).isoformat()
    cut_ex = (datetime.now(timezone.utc) - timedelta(days=EXCLUDED_DAYS)).isoformat()
    return ({k: v for k, v in seen.items() if v.get("t", "") >= cut_seen},
            [x for x in excluded if x.get("t", "") >= cut_ex])


def run(only: str | None = None, fetch_bodies: bool = True) -> dict:
    t0 = now_iso()
    seen = read_json(STATE / "seen.json", {})
    excluded = read_json(STATE / "excluded_recent.json", [])
    health = read_json(STATE / "sources_status.json", {})
    articles = load_articles()
    titles = {a.get("titleKey") for a in articles.values()}
    body_budget = MAX_BODY_FETCHES
    totals = {"found": 0, "new": 0, "kept": 0, "excluded": 0, "duplicates": 0}

    for source in load_sources(only):
        sid = source["id"]
        h = health.get(sid, {"consecutiveFailures": 0})
        items, st = collect_source(source)
        h.update(lastRunAt=t0, method=st["method"], url=st["url"], errors=st["errors"][:6], found=len(items))
        if not items:
            h["consecutiveFailures"] = h.get("consecutiveFailures", 0) + 1
            h["new"] = 0
            health[sid] = h
            print(f"✗ {sid}: فشل ({'; '.join(st['errors'][:3])})")
            continue
        h["consecutiveFailures"] = 0
        h["lastSuccessAt"] = t0
        new = kept = 0
        for it in items:
            key = url_key(it["url"])
            if key in seen:
                continue
            new += 1
            tk = title_key(it["title"])
            if tk in titles:
                seen[key] = {"v": "duplicate", "t": t0}
                totals["duplicates"] += 1
                continue
            omani = bool(source.get("omaniOutlet"))
            res = classify(it["title"], it["summary"], omani)
            if res.outcome in ("relevant", "uncertain") and fetch_bodies and body_budget > 0:
                body_budget -= 1
                body = fetch_body(it["url"])
                if body:
                    res = classify(it["title"], f"{it['summary']}\n{body}", omani)
            res = legislation_boost(res, it["title"], it["summary"])
            if res.outcome not in ("relevant", "uncertain"):
                seen[key] = {"v": res.outcome, "t": t0}
                excluded.append({"t": t0, "source": sid, "title": it["title"][:200], "url": it["url"], "why": res.outcome})
                totals["excluded"] += 1
                continue
            aid = article_id(key)
            articles[aid] = {
                "id": aid, "url": it["url"], "title": it["title"], "titleKey": tk,
                "excerpt": it["summary"][:EXCERPT_CHARS],
                "source": sid, "publisher": it.get("publisher"), "lang": source.get("lang", "ar"),
                "publishedAt": it["publishedAt"], "collectedAt": t0,
                **classification_fields(res),
            }
            titles.add(tk)
            seen[key] = {"v": res.outcome, "t": t0}
            kept += 1
        h["new"] = new
        h["kept"] = kept
        if kept:
            h["lastNewArticleAt"] = t0
        health[sid] = h
        totals["found"] += len(items)
        totals["new"] += new
        totals["kept"] += kept
        print(f"✓ {sid}: {len(items)} عنصر، {new} جديد، {kept} مرتبط بالرؤية ({st['method']})")

    seen, excluded = prune(seen, excluded)
    save_articles(articles)
    write_json(STATE / "seen.json", seen, indent=None)
    write_json(STATE / "excluded_recent.json", excluded)
    write_json(STATE / "sources_status.json", health)
    runs = read_json(STATE / "runs.json", [])
    runs.append({"at": t0, **totals})
    write_json(STATE / "runs.json", runs[-200:])
    print(f"المجموع: {totals}")
    return totals


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--no-body", action="store_true")
    a = ap.parse_args()
    run(a.source, not a.no_body)
    sys.exit(0)
