"""«الزبدة» التحريرية بالذكاء الاصطناعي — اختياري، يعمل فقط بوجود مفتاح (انظر ai.py).

لكل أولوية، وللمجمل، في الفترات: الأسبوع الحالي، الأسبوع الماضي، الشهر الحالي، الشهر الماضي.
يُرسل العناوين والمقتطفات القصيرة فقط، ويطلب 3–6 نقاط ملموسة (ماذا حدث، من، كم) مع أرقام الأخبار المصدر.
النتائج تُحفظ في data/summaries/ ولا تُعاد كتابتها إلا إذا تغيّرت أخبار الفترة،
وملخص الفترة الجارية لا يُحدَّث أكثر من مرة كل 12 ساعة (للتوفير).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from ai import call, parse_obj, provider
from build import COUNTED, art_day, load_taxonomy, month_start, next_month, week_start
from common import DATA, load_articles, now_iso, read_json, write_json

SUMMARIES = DATA / "summaries"
MAX_CALLS = int(os.getenv("AI_MAX_SUMMARIES", "30"))
REFRESH_HOURS = 12

SYSTEM = """أنت محرر في مديرية رؤية عُمان 2040. تكتب «الزبدة» لمختصي الأولويات: ماذا حدث فعلًا في الفترة.
القواعد:
- 3 إلى 6 نقاط، كل نقطة جملة واحدة بالعربية الفصحى المختصرة تبدأ بالفعل أو الجهة: «وقّعت…»، «صدر مرسوم سلطاني…»، «رفع البنك الدولي توقعاته…»، «ارتفع…».
- اذكر الأرقام والجهات والأسماء كما وردت في الأخبار فقط. لا تخمّن ولا تضف معلومة غير موجودة في النص.
- ادمج الأخبار التي تتحدث عن الحدث نفسه في نقطة واحدة.
- قدّم الأهم: المراسيم والقرارات، ثم التقييمات الدولية والأرقام، ثم الاتفاقيات والمشاريع، وأخيرًا الفعاليات.
- تجاهل الأخبار البروتوكولية التي لا تحمل حدثًا ملموسًا.
- أرفق مع كل نقطة أرقام الأخبار التي تستند إليها.
أعد JSON فقط: {"bullets":[{"text":"...","refs":[0,3]}]}"""


def periods(today):
    ws = week_start(today)
    ms = month_start(today)
    pm = month_start(ms - timedelta(days=1))
    return [("w-" + ws.isoformat(), ws, ws + timedelta(days=7)),
            ("w-" + (ws - timedelta(days=7)).isoformat(), ws - timedelta(days=7), ws),
            ("m-" + ms.isoformat(), ms, next_month(ms)),
            ("m-" + pm.isoformat(), pm, ms)]


def run() -> dict:
    p = provider()
    if not p:
        print("الذكاء الاصطناعي غير مفعّل — الزبدة تُصاغ بالقواعد.")
        return {"skipped": True}
    kind, key, model = p
    _, pri, _ = load_taxonomy()
    arts = [a for a in load_articles().values() if a["status"] in COUNTED]
    today = datetime.now(timezone(timedelta(hours=4))).date()
    calls = 0
    stats = {"written": 0, "cached": 0, "errors": 0}
    for pid, start, end in periods(today):
        in_period = [a for a in arts if start <= art_day(a) < end]
        groups = [("ALL", "كل الأولويات", in_period)] + [
            (c, p["nameAr"], [a for a in in_period if c in {x["id"] for x in a.get("priorities", [])}]) for c, p in pri.items()]
        for code, name, items in groups:
            if not items:
                continue
            items = sorted(items, key=lambda a: a.get("publishedAt") or a["collectedAt"], reverse=True)[:60 if code == "ALL" else 40]
            digest = hashlib.sha1("|".join(sorted(a["id"] for a in items)).encode()).hexdigest()[:16]
            path = SUMMARIES / pid / f"{code}.json"
            old = read_json(path, None)
            partial = end > today
            if old and (old.get("hash") == digest or (partial and datetime.fromisoformat(old["at"]) > datetime.now(timezone.utc) - timedelta(hours=REFRESH_HOURS))):
                stats["cached"] += 1
                continue
            if calls >= MAX_CALLS:
                continue
            calls += 1
            user = f"الأولوية: {name}\nالفترة: {start} إلى {end - timedelta(days=1)}\n\n" + "\n\n".join(
                f"[{i}] {a['title']}\n{(a.get('excerpt') or '')[:300]}" for i, a in enumerate(items))
            try:
                obj = parse_obj(call(kind, key, model, SYSTEM, user))
            except Exception as e:
                print(f"خطأ في تلخيص {pid}/{code}: {e}")
                stats["errors"] += 1
                if "401" in str(e) or "402" in str(e) or "429" in str(e):
                    break
                continue
            bullets = []
            for b in (obj or {}).get("bullets", [])[:6]:
                refs = [items[i]["id"] for i in b.get("refs", []) if isinstance(i, int) and 0 <= i < len(items)]
                if b.get("text"):
                    bullets.append({"text": str(b["text"])[:400], "refs": refs[:6]})
            if bullets:
                write_json(path, {"hash": digest, "at": now_iso(), "model": model, "bullets": bullets})
                stats["written"] += 1
    print(f"الزبدة بالذكاء الاصطناعي: {stats}")
    return stats


if __name__ == "__main__":
    run()
    sys.exit(0)
