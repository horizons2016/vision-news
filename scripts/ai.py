"""التصنيف الاختياري بالذكاء الاصطناعي — للأخبار «المحتملة» (uncertain) فقط.

لا يعمل إلا إذا أُضيف أحد المفتاحين في أسرار GitHub:
  ANTHROPIC_API_KEY   (النموذج الافتراضي AI_MODEL=claude-haiku-5-5)
  OPENAI_API_KEY      (النموذج الافتراضي AI_MODEL=gpt-5-mini)
بدون مفتاح يخرج دون أي أثر، وتبقى الأخبار المحتملة في قائمة «بحاجة لتأكيد».

ما يُرسل: العنوان والمقتطف القصير فقط. حد أقصى للتشغيلة: AI_MAX_ITEMS (افتراضيًا 40).
قرار الذكاء الاصطناعي:
  ثقة ≥ 0.75 وارتباط   → يُعتمد تلقائيًا (method=ai)
  ثقة 0.5–0.75         → «بحاجة لتأكيد» مع اقتراح الذكاء الاصطناعي
  غير مرتبط             → يُستبعد من الأرشيف ويُسجَّل في سجل المستبعد
"""
from __future__ import annotations

import json
import os
import re
import sys

import requests

from common import STATE, TAXONOMY, load_articles, now_iso, read_json, save_articles, write_json

BATCH = 10
AUTO_CONF = 0.75
REVIEW_CONF = 0.5


def provider() -> tuple[str, str, str] | None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ["ANTHROPIC_API_KEY"], os.getenv("AI_MODEL", "claude-haiku-5-5")
    if os.getenv("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"], os.getenv("AI_MODEL", "gpt-5-mini")
    return None


def taxonomy_prompt() -> str:
    ref = json.loads((TAXONOMY / "reference.json").read_text(encoding="utf-8"))
    lines = ["الأولويات:"]
    for p in ref["priorities"]:
        lines.append(f"P{p['number']:02d}: {p['nameAr']}")
    lines.append("\nالمؤشرات (رمز المؤشر ← أولويته):")
    for i in ref["indicators"]:
        lines.append(f"I{i['number']:02d} (P{int(i['priorityStableId'][-2:]):02d}): {i['nameAr']}")
    return "\n".join(lines)


SYSTEM = """أنت محلل في مديرية رؤية عُمان 2040. لكل خبر قرّر هل يرتبط فعلًا بأولويات الرؤية ومؤشراتها في سلطنة عُمان.
المرتبط: خبر عن سياسة أو مشروع أو قرار أو بيانات أو برنامج في عُمان يمسّ أولوية أو مؤشرًا.
غير المرتبط: المجاملات والبروتوكول والتعازي والرياضة والطقس والحوادث وأخبار الدول الأخرى التي لا تخص عُمان.
لا تربط بمؤشر إلا إذا كان الخبر يمسّه مباشرة؛ الربط بالأولوية وحدها مقبول.
{taxonomy}

أعد JSON فقط بالشكل:
{{"results":[{{"i":0,"relevant":true,"priority":"P06","indicators":["I19"],"confidence":0.8,"note":"جملة قصيرة بالعربية تشرح الربط"}}]}}"""


def call(kind: str, key: str, model: str, system: str, user: str) -> str:
    if kind == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 2000, "system": system, "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []))
    r = requests.post("https://api.openai.com/v1/chat/completions", timeout=120, headers={
        "Authorization": f"Bearer {key}"}, json={"model": model, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def parse(text: str) -> list[dict]:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        return json.loads(m.group(0)).get("results", [])
    except json.JSONDecodeError:
        return []


def apply_result(a: dict, res: dict, model: str, valid_p: set, valid_i: dict) -> str:
    conf = float(res.get("confidence") or 0)
    pid = res.get("priority")
    inds = [i for i in (res.get("indicators") or []) if i in valid_i and valid_i[i] == pid][:4]
    a["ai"] = {"model": model, "confidence": round(conf, 2), "note": (res.get("note") or "")[:300], "at": now_iso()}
    if not res.get("relevant") or pid not in valid_p or conf < REVIEW_CONF:
        return "drop"
    a["priorities"] = [{"id": pid, "score": round(conf * 10, 1)}]
    a["indicators"] = [{"id": i, "score": round(conf * 10, 1), "evidence": "ai"} for i in inds]
    a["outcome"] = "relevant"
    a["method"] = "ai"
    if conf >= AUTO_CONF:
        a["status"] = "auto"
        a["reasons"] = []
    else:
        a["status"] = "review"
        a["reasons"] = ["low_confidence"]
    return a["status"]


def run(max_items: int | None = None) -> dict:
    p = provider()
    if not p:
        print("الذكاء الاصطناعي غير مفعّل (لا يوجد مفتاح) — تخطي.")
        return {"skipped": True}
    kind, key, model = p
    max_items = max_items or int(os.getenv("AI_MAX_ITEMS", "40"))
    ref = json.loads((TAXONOMY / "reference.json").read_text(encoding="utf-8"))
    valid_p = {f"P{x['number']:02d}" for x in ref["priorities"]}
    valid_i = {f"I{x['number']:02d}": f"P{int(x['priorityStableId'][-2:]):02d}" for x in ref["indicators"]}
    system = SYSTEM.format(taxonomy=taxonomy_prompt())

    articles = load_articles()
    queue = [a for a in articles.values() if a["status"] == "uncertain" and "ai" not in a]
    queue.sort(key=lambda a: a.get("publishedAt") or a["collectedAt"], reverse=True)  # الأحدث أولًا
    queue = queue[:max_items]
    excluded = read_json(STATE / "excluded_recent.json", [])
    stats = {"sent": 0, "auto": 0, "review": 0, "drop": 0, "errors": 0}

    for start in range(0, len(queue), BATCH):
        batch = queue[start:start + BATCH]
        user = "\n\n".join(f"[{i}] {a['title']}\n{a.get('excerpt', '')[:400]}" for i, a in enumerate(batch))
        try:
            results = parse(call(kind, key, model, system, user))
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            print(f"خطأ من مزود الذكاء الاصطناعي HTTP {code} — إيقاف هذه التشغيلة.")
            stats["errors"] += 1
            if code in (401, 402, 403, 429):  # مفتاح أو رصيد: لا فائدة من الإكمال
                break
            continue
        except Exception as e:
            print(f"خطأ: {e}")
            stats["errors"] += 1
            continue
        stats["sent"] += len(batch)
        by_i = {r.get("i"): r for r in results if isinstance(r, dict)}
        for i, a in enumerate(batch):
            r = by_i.get(i)
            if not r:
                continue
            outcome = apply_result(a, r, model, valid_p, valid_i)
            stats[outcome] += 1
            if outcome == "drop":
                excluded.append({"t": now_iso(), "source": a["source"], "title": a["title"][:200], "url": a["url"], "why": "ai_not_relevant"})
                articles.pop(a["id"], None)

    save_articles(articles)
    write_json(STATE / "excluded_recent.json", excluded)
    print(f"الذكاء الاصطناعي: {stats}")
    return stats


if __name__ == "__main__":
    run()
    sys.exit(0)
