"""استيراد أرشيف نظام «رصد 2040» السابق (لقطة Convex) — يُشغَّل مرة واحدة.

يعيد تصنيف كل خبر بالقواعد الحالية ويحتفظ فقط بالمرتبط والمحتمل.
التصنيف القديم (10 فئات غير رسمية) لا يُنقل.

python scripts/import_hercules.py path/to/news/documents.jsonl
"""
from __future__ import annotations

import json
import sys

from common import article_id, classification_fields, clean_text, load_articles, now_iso, save_articles, title_key, url_key
from taxonomy.classify import classify

NAME_TO_ID = {"جريدة عمان": "omandaily", "تايمز أوف عمان": "timesofoman", "عمان أوبزرفر": "omanobserver"}


def main(path: str) -> None:
    articles = load_articles()
    titles = {a.get("titleKey") for a in articles.values()}
    stats = {"read": 0, "relevant": 0, "uncertain": 0, "skipped": 0, "duplicates": 0}
    for line in open(path, encoding="utf-8"):
        n = json.loads(line)
        stats["read"] += 1
        sid = NAME_TO_ID.get(n.get("source") or "")
        url = n.get("sourceUrl")
        if not sid or not url:
            stats["skipped"] += 1
            continue
        res = classify(n["title"], n.get("content", ""), True)
        if res.outcome not in ("relevant", "uncertain"):
            stats["skipped"] += 1
            continue
        title = clean_text(n["title"])
        tk = title_key(title)
        key = url_key(url)
        aid = article_id(key)
        if aid in articles or tk in titles:
            stats["duplicates"] += 1
            continue
        titles.add(tk)
        stats[res.outcome] += 1
        articles[aid] = {
            "id": aid, "url": url, "title": title, "titleKey": tk,
            "excerpt": clean_text(n.get("content", ""))[:400],
            "source": sid, "publisher": None, "lang": "en" if sid != "omandaily" else "ar",
            "publishedAt": n.get("publishedAt") or n.get("submittedAt"),
            "collectedAt": n.get("detectedAt") or n.get("submittedAt") or now_iso(),
            "imported": "hercules-2026-11",
            **classification_fields(res),
        }
    save_articles(articles)
    print(stats)


if __name__ == "__main__":
    main(sys.argv[1])
