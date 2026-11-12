"""بناء بيانات الموقع والتقارير الأسبوعية والشهرية.

1. يقرأ الأرشيف data/articles ويطبّق قرارات الفريق من data/decisions.csv.
2. يحسب الحراك لكل محور وأولوية ومؤشر أسبوعيًا وشهريًا، وإشارات الحراك لكل مؤشر.
3. يكتب ملفات site/data/*.json للموقع، وتقارير Markdown في reports/.
إن وُجد خطأ في decisions.csv يتوقف ويشرح السبب بالعربية (فلا يُنشر شيء خاطئ).

python scripts/build.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from common import (CONFIG, DATA, REPORTS, SITE, STATE, TAXONOMY, load_articles, now_iso, read_json, to_muscat,
                    write_json)
from newstype import TYPES, news_type, rule_digest
from analysis import analyse

COUNTED = {"auto", "confirmed"}
DECISION_WORDS = {"تأكيد": "confirm", "confirm": "confirm", "رفض": "reject", "reject": "reject",
                  "تعديل": "assign", "assign": "assign"}
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- المرجع
def load_taxonomy():
    ref = json.loads((TAXONOMY / "reference.json").read_text(encoding="utf-8"))
    pri = {}
    for p in ref["priorities"]:
        code = f"P{p['number']:02d}"
        axis = next(a for a in ref["axes"] if p["number"] in a["priorities"])
        pri[code] = {"code": code, "number": p["number"], "nameAr": p["nameAr"], "nameEn": p["nameEn"], "axis": axis["id"]}
    ind = {}
    for i in ref["indicators"]:
        code = f"I{i['number']:02d}"
        ind[code] = {"code": code, "number": i["number"], "nameAr": i["nameAr"], "nameEn": i["nameEn"],
                     "priority": f"P{int(i['priorityStableId'][-2:]):02d}"}
    axes = [{"id": a["id"], "number": a["number"], "nameAr": a["nameAr"], "nameEn": a["nameEn"],
             "priorities": [f"P{n:02d}" for n in a["priorities"]]} for a in ref["axes"]]
    return axes, pri, ind


# ---------------------------------------------------------------- القرارات
def apply_decisions(articles: dict, pri: dict, ind: dict) -> tuple[list, list]:
    path = DATA / "decisions.csv"
    errors, warnings = [], []
    if not path.exists():
        return errors, warnings
    reader = csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    next(reader, None)
    for n, row in enumerate(reader, start=2):
        if not row or not any(c.strip() for c in row):
            continue
        row += [""] * (6 - len(row))
        aid, word, pcode, icodes, by, note = (c.strip() for c in row[:6])
        action = DECISION_WORDS.get(word.lower())
        if not action:
            errors.append(f"decisions.csv سطر {n}: القرار «{word}» غير معروف. المسموح: تأكيد، رفض، تعديل.")
            continue
        a = articles.get(aid)
        if not a:
            warnings.append(f"decisions.csv سطر {n}: لا يوجد خبر بالمعرف {aid} (ربما حُذف) — تم تجاهل السطر.")
            continue
        if action == "reject":
            a.update(status="rejected", decision={"action": "رفض", "by": by, "note": note})
            continue
        if action == "confirm" and not pcode:
            if not a.get("priorities"):
                errors.append(f"decisions.csv سطر {n}: لا يمكن تأكيد خبر بلا أولوية؛ استخدم «تعديل» واكتب الأولوية.")
                continue
            a.update(status="confirmed", decision={"action": "تأكيد", "by": by, "note": note})
            continue
        pcode = pcode.upper()
        if pcode not in pri:
            errors.append(f"decisions.csv سطر {n}: رمز الأولوية «{pcode}» غير صحيح (المسموح P01 إلى P12).")
            continue
        codes = [c.strip().upper() for c in icodes.replace("،", " ").replace(",", " ").replace(";", " ").split() if c.strip()]
        bad = [c for c in codes if c not in ind]
        if bad:
            errors.append(f"decisions.csv سطر {n}: رمز مؤشر غير صحيح {bad} (المسموح I01 إلى I38).")
            continue
        wrong = [c for c in codes if ind[c]["priority"] != pcode]
        if wrong:
            errors.append(f"decisions.csv سطر {n}: المؤشرات {wrong} لا تتبع الأولوية {pcode}.")
            continue
        a.update(status="confirmed", method="manual", priorities=[{"id": pcode, "score": 10}],
                 indicators=[{"id": c, "score": 10, "evidence": "manual"} for c in codes],
                 decision={"action": "تعديل", "by": by, "note": note})
    return errors, warnings


# ---------------------------------------------------------------- الفترات
def art_day(a: dict) -> date:
    return to_muscat(a.get("publishedAt") or a["collectedAt"]).date()


def week_start(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)  # الأسبوع يبدأ الأحد


def month_start(d: date) -> date:
    return d.replace(day=1)


def next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def label_week(s: date) -> str:
    e = s + timedelta(days=6)
    return f"{s.day} {AR_MONTHS[s.month - 1]} – {e.day} {AR_MONTHS[e.month - 1]} {e.year}"


def label_month(s: date) -> str:
    return f"{AR_MONTHS[s.month - 1]} {s.year}"


# ---------------------------------------------------------------- الخبر المختصر للموقع
def compact(a):
    return {
        "id": a["id"], "t": a["title"], "u": a["url"], "s": a["source"], "pub": a.get("publisher"),
        "d": art_day(a).isoformat(), "st": a["status"], "m": a.get("method", "rules"),
        "ty": news_type(a["title"], a.get("excerpt", "")), "lang": a.get("lang", "ar"),
        "p": [x["id"] for x in a.get("priorities", [])], "i": [x["id"] for x in a.get("indicators", [])],
        "k": a.get("terms", [])[:6], "r": a.get("reasons", []), "x": (a.get("excerpt") or "")[:220],
        **({"ai": a["ai"].get("note"), "ac": a["ai"].get("confidence")} if a.get("ai") else {}),
        **({"dec": a["decision"]} if a.get("decision") else {}),
    }


def digest_for(period_id: str, code: str, arts: list) -> dict:
    """الخلاصة: من الذكاء الاصطناعي إن وُجد ملخص محفوظ، وإلا بالقواعد."""
    saved = read_json(DATA / "summaries" / period_id / f"{code}.json", None)
    if saved and saved.get("bullets"):
        return {"source": "ai", "bullets": saved["bullets"]}
    return {"source": "rules", "bullets": rule_digest([compact(a) for a in arts], 6 if code == "ALL" else 5)}


# ---------------------------------------------------------------- التقارير
def period_report(kind, start, end, today, counted, review_all, pri, ind, axes, sources, prev_counted):
    def in_range(arts, s, e):
        return [a for a in arts if s <= art_day(a) < e]

    cur = in_range(counted, start, end)
    span = end - start
    prev_start = start - span if kind == "week" else (month_start(start - timedelta(days=1)))
    prev = in_range(prev_counted, prev_start, start)
    rev = in_range(review_all, start, end)

    def tally(arts):
        p, i = Counter(), Counter()
        for a in arts:
            for x in {y["id"] for y in a.get("priorities", [])}:
                p[x] += 1
            for x in {y["id"] for y in a.get("indicators", [])}:
                i[x] += 1
        return p, i

    pc, ic = tally(cur)
    ppc, pic = tally(prev)

    def primary(a):
        return a["priorities"][0]["id"] if a.get("priorities") else None

    priorities = []
    for code, p in pri.items():
        arts = sorted([a for a in cur if primary(a) == code or code in {x["id"] for x in a["priorities"]}],
                      key=lambda a: (-(a["priorities"][0]["score"] if primary(a) == code else 0), a.get("publishedAt") or ""))
        top_ind = [{"code": c, "nameAr": ind[c]["nameAr"], "count": ic[c]} for c in ind if ind[c]["priority"] == code and ic[c]]
        top_ind.sort(key=lambda x: -x["count"])
        rid_ = ("w-" if kind == "week" else "m-") + start.isoformat()
        priorities.append({
            "code": code, "nameAr": p["nameAr"], "axis": p["axis"], "count": pc[code], "prev": ppc[code],
            "digest": digest_for(rid_, code, arts) if arts else {"source": "rules", "bullets": []},
            "indicators": top_ind,
            "headlines": [{"id": a["id"], "title": a["title"], "url": a["url"], "source": a["source"],
                           "date": art_day(a).isoformat()} for a in arts[:5]],
        })
    axes_out = []
    for ax in axes:
        ids = set(ax["priorities"])
        c = sum(1 for a in cur if primary(a) in ids)
        pv = sum(1 for a in prev if primary(a) in ids)
        axes_out.append({"id": ax["id"], "nameAr": ax["nameAr"], "count": c, "prev": pv})

    active_ind = sorted([{"code": c, "nameAr": ind[c]["nameAr"], "priority": ind[c]["priority"], "count": ic[c],
                          "prev": pic[c]} for c in ind if ic[c] or pic[c]], key=lambda x: -x["count"])
    silent_p = [p["code"] for p in priorities if p["count"] == 0]
    src = Counter(a["source"] for a in cur)

    highlights = []
    if cur:
        best = max(priorities, key=lambda x: x["count"])
        highlights.append(f"الأولوية الأكثر حراكًا: {best['nameAr']} ({best['count']} خبرًا).")
        rising = [p for p in priorities if p["count"] >= 3 and p["count"] >= 1.5 * max(p["prev"], 1)]
        for p in sorted(rising, key=lambda x: -(x["count"] - x["prev"]))[:2]:
            highlights.append(f"ارتفاع ملحوظ في {p['nameAr']}: {p['count']} مقابل {p['prev']} في الفترة السابقة.")
        if active_ind:
            ti = active_ind[0]
            if ti["count"]:
                highlights.append(f"المؤشر الأكثر ذكرًا: {ti['nameAr']} ({ti['count']}).")
    if silent_p:
        highlights.append("أولويات بلا أخبار في هذه الفترة: " + "، ".join(pri[c]["nameAr"] for c in silent_p) + ".")

    rid = ("w-" if kind == "week" else "m-") + start.isoformat()
    return {
        "id": rid, "type": kind, "label": label_week(start) if kind == "week" else label_month(start),
        "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(), "partial": end > today,
        "total": len(cur), "prevTotal": len(prev),
        "byMethod": dict(Counter(a.get("method", "rules") for a in cur)),
        "awaiting": len(rev), "axes": axes_out, "priorities": priorities, "indicators": active_ind,
        "silentPriorities": silent_p,
        "silentIndicators": [c for c in ind if not ic[c]],
        "sources": [{"id": s, "nameAr": sources.get(s, {}).get("nameAr", s), "count": n} for s, n in src.most_common()],
        "highlights": highlights,
        "digest": digest_for(rid, "ALL", cur),
        "types": dict(Counter(news_type(a["title"], a.get("excerpt", "")) for a in cur)),
    }


def report_markdown(r: dict, pri: dict) -> str:
    kind = "الأسبوعي" if r["type"] == "week" else "الشهري"
    out = [f"# تقرير حراك رؤية عُمان 2040 {kind}", "", f"**الفترة:** {r['label']}" + (" (حتى الآن)" if r["partial"] else ""), "",
           f"- الأخبار المرتبطة بالرؤية: **{r['total']}** (الفترة السابقة: {r['prevTotal']})",
           f"- بانتظار تأكيد الفريق: {r['awaiting']}", ""]
    if r["digest"]["bullets"]:
        out += ["## الخلاصة: ماذا حدث", ""] + [f"- {TYPES[b['type']]['icon'] + ' ' if b.get('type') else ''}{b['text']}" for b in r["digest"]["bullets"]] + [""]
    if r["highlights"]:
        out += ["## أرقام الحراك", ""] + [f"- {h}" for h in r["highlights"]] + [""]
    out += ["## حسب المحاور", "", "| المحور | الأخبار | السابقة |", "|---|---|---|"]
    out += [f"| {a['nameAr']} | {a['count']} | {a['prev']} |" for a in r["axes"]] + [""]
    out += ["## حسب الأولويات", ""]
    for p in sorted(r["priorities"], key=lambda x: -x["count"]):
        if not p["count"]:
            continue
        out.append(f"### {p['code']} — {p['nameAr']} ({p['count']})")
        out += [f"- **{b['text']}**" for b in p["digest"]["bullets"][:4]]
        if p["indicators"]:
            out.append("المؤشرات: " + "، ".join(f"{i['nameAr']} ({i['count']})" for i in p["indicators"]))
        out += ["", "المصادر:"] + [f"- [{h['title']}]({h['url']}) — {h['date']}" for h in p["headlines"]] + [""]
    out += ["---", "*رصد إخباري لما نُشر عن أولويات رؤية عُمان 2040؛ الخلاصة مستخلصة من الأخبار المرفقة روابطها.*", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- البناء
def main() -> int:
    settings = read_json(CONFIG / "settings.json", {})
    axes, pri, ind = load_taxonomy()
    sources_cfg = {s["id"]: s for s in read_json(CONFIG / "sources.json", {"sources": []})["sources"]}
    health = read_json(STATE / "sources_status.json", {})
    articles = load_articles()

    errors, warnings = apply_decisions(articles, pri, ind)
    report_lines = [f"# تقرير البناء — {now_iso()}", ""]
    if errors:
        report_lines += ["## أخطاء أوقفت النشر", ""] + [f"- {e}" for e in errors]
    if warnings:
        report_lines += ["", "## تنبيهات", ""] + [f"- {w}" for w in warnings]

    today = datetime.now().astimezone(to_muscat("2026-01-01T00:00:00+04:00").tzinfo).date()
    if os.getenv("BUILD_TODAY"):
        today = date.fromisoformat(os.environ["BUILD_TODAY"])
    arts = list(articles.values())
    counted = [a for a in arts if a["status"] in COUNTED]
    review = [a for a in arts if a["status"] == "review"]
    uncertain = [a for a in arts if a["status"] == "uncertain"]

    # التقارير
    reports = []
    ws = week_start(today)
    for k in range(settings.get("reportWeeks", 12), -1, -1):
        s = ws - timedelta(weeks=k)
        reports.append(period_report("week", s, s + timedelta(days=7), today, counted, review, pri, ind, axes, sources_cfg, counted))
    ms = month_start(today)
    months = []
    m = ms
    for _ in range(settings.get("reportMonths", 12) + 1):
        months.append(m)
        m = month_start(m - timedelta(days=1))
    first_day = min((art_day(a) for a in counted), default=today)
    for s in reversed(months):
        if next_month(s) <= month_start(first_day):
            continue
        reports.append(period_report("month", s, next_month(s), today, counted, review, pri, ind, axes, sources_cfg, counted))
    reports = [r for r in reports if r["total"] or r["partial"] or r["awaiting"]]
    want = ["w-" + ws.isoformat(), "w-" + (ws - timedelta(days=7)).isoformat(), "m-" + ms.isoformat(),
            "m-" + month_start(ms - timedelta(days=1)).isoformat()]
    names = ["هذا الأسبوع", "الأسبوع الماضي", "هذا الشهر", "الشهر الماضي"]
    have = {r["id"]: r for r in reports}
    digest_periods = [{"id": w, "name": n, "label": have[w]["label"]} for w, n in zip(want, names) if w in have]

    # سلاسل أسبوعية لكل أولوية ومؤشر (آخر 26 أسبوعًا)
    weeks = [(ws - timedelta(weeks=k)).isoformat() for k in range(25, -1, -1)]
    series = {"weeks": weeks, "total": [0] * 26, "axes": defaultdict(lambda: [0] * 26),
              "priorities": defaultdict(lambda: [0] * 26), "indicators": defaultdict(lambda: [0] * 26)}
    wi = {w: n for n, w in enumerate(weeks)}
    axis_of = {c: p["axis"] for c, p in pri.items()}
    for a in counted:
        n = wi.get(week_start(art_day(a)).isoformat())
        if n is None:
            continue
        series["total"][n] += 1
        if a.get("priorities"):
            series["axes"][axis_of[a["priorities"][0]["id"]]][n] += 1
        for c in {x["id"] for x in a.get("priorities", [])}:
            series["priorities"][c][n] += 1
        for c in {x["id"] for x in a.get("indicators", [])}:
            series["indicators"][c][n] += 1

    totals_p = Counter(c for a in counted for c in {x["id"] for x in a.get("priorities", [])})
    totals_i = Counter(c for a in counted for c in {x["id"] for x in a.get("indicators", [])})


    by_date = lambda a: (art_day(a).isoformat(), a["id"])  # noqa: E731
    src_out = []
    for sid, s in sources_cfg.items():
        h = health.get(sid, {})
        n_art = sum(1 for a in counted if a["source"] == sid)
        last = max((art_day(a) for a in counted if a["source"] == sid), default=None)
        src_out.append({"id": sid, "nameAr": s["nameAr"], "nameEn": s["nameEn"], "kind": s.get("kind"),
                        "publishes": s.get("publishes"), "active": s.get("active", True), "articles": n_art,
                        "lastArticle": last.isoformat() if last else None, **{k: h.get(k) for k in (
                            "lastRunAt", "lastSuccessAt", "consecutiveFailures", "method", "url", "errors", "found", "new", "kept")}})

    excluded = read_json(STATE / "excluded_recent.json", [])
    runs = read_json(STATE / "runs.json", [])
    meta = {
        "builtAt": now_iso(), "today": today.isoformat(), "siteTitle": settings.get("siteTitle", "رصد الرؤية"),
        "rulesVersion": json.loads((TAXONOMY / "rules.json").read_text(encoding="utf-8"))["version"],
        "axes": axes, "priorities": list(pri.values()),
        "indicators": list(ind.values()), "types": TYPES,
        "totals": {"counted": len(counted), "review": len(review), "uncertain": len(uncertain),
                   "rejected": sum(1 for a in arts if a["status"] == "rejected"),
                   "byPriority": totals_p, "byIndicator": totals_i,
                   "byMethod": Counter(a.get("method", "rules") for a in counted)},
        "sources": src_out, "digestPeriods": digest_periods,
        "lastRun": runs[-1] if runs else None, "reasonLabels": json.loads((TAXONOMY / "rules.json").read_text(encoding="utf-8"))["review_reason_labels"],
        "reports": [{"id": r["id"], "type": r["type"], "label": r["label"], "total": r["total"], "partial": r["partial"]} for r in reports],
    }

    if errors:
        (DATA / "build_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        summary(report_lines)
        print("\n".join(errors), file=sys.stderr)
        return 1

    out = SITE / "data"
    write_json(out / "meta.json", meta, indent=None)
    write_json(out / "analysis.json", analyse([compact(a) for a in counted], axes, pri, ind, today, week_start), indent=None)
    write_json(out / "series.json", {k: (dict(v) if isinstance(v, defaultdict) else v) for k, v in series.items()}, indent=None)
    write_json(out / "articles.json", [compact(a) for a in sorted(counted + review, key=by_date, reverse=True)], indent=None)
    write_json(out / "uncertain.json", [compact(a) for a in sorted(uncertain, key=by_date, reverse=True)], indent=None)
    write_json(out / "excluded.json", excluded[-800:][::-1], indent=None)
    for f in (out / "reports").glob("*.json") if (out / "reports").exists() else []:
        f.unlink()
    for r in reports:
        write_json(out / "reports" / f"{r['id']}.json", r, indent=None)
        folder = REPORTS / ("weekly" if r["type"] == "week" else "monthly")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{r['start']}.md").write_text(report_markdown(r, pri), encoding="utf-8")

    report_lines += ["", f"- أخبار محتسبة: {len(counted)}، بانتظار التأكيد: {len(review)}، محتملة: {len(uncertain)}",
                     f"- تقارير: {len(reports)}"]
    (DATA / "build_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    summary(report_lines)
    print(f"تم البناء: {len(counted)} خبر محتسب، {len(review)} بانتظار التأكيد، {len(uncertain)} محتمل، {len(reports)} تقرير.")
    return 0


def summary(lines):
    p = os.getenv("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
