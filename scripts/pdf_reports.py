"""توليد ملفات PDF جاهزة للتقارير الأسبوعية والشهرية.

زر «طباعة» في المتصفح لا يعمل في تطبيق الجوال المثبت على الشاشة الرئيسية ولا في المتصفحات
الداخلية (Gmail، واتساب…)، لذلك تُبنى ملفات PDF هنا وتُنشر مع الموقع في site/data/reports/<id>.pdf
ويحمّلها الزر مباشرة.

يُشغَّل بعد build.py:
    python scripts/pdf_reports.py
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date

from common import ROOT, SITE

FONTS = ROOT / "assets" / "fonts"
OUT = SITE / "data" / "reports"
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

CSS = f"""
@font-face {{ font-family: Plex; src: url("{(FONTS / 'IBMPlexSansArabic-Regular.ttf').as_uri()}"); font-weight: 400; }}
@font-face {{ font-family: Plex; src: url("{(FONTS / 'IBMPlexSansArabic-Bold.ttf').as_uri()}"); font-weight: 700; }}
@page {{ size: A4; margin: 16mm 14mm 18mm;
  @bottom-center {{ content: counter(page) " / " counter(pages); font-family: Plex; font-size: 9pt; color: #777; }} }}
html {{ direction: rtl; }}
body {{ font-family: Plex, sans-serif; font-size: 10.5pt; line-height: 1.65; color: #222; text-align: right; }}
h1 {{ font-size: 17pt; color: #3f3566; margin: 0 0 2px; }}
h2 {{ font-size: 13pt; color: #3f3566; border-bottom: 1.5px solid #d9d3ea; padding-bottom: 3px; margin: 18px 0 8px; }}
h3 {{ font-size: 11pt; margin: 12px 0 4px; }}
.sub {{ color: #666; margin: 0 0 12px; }}
.kpis {{ display: flex; gap: 8px; }}
.kpi {{ flex: 1; background: #f3f0f9; border-radius: 6px; padding: 6px 10px; }}
.kpi .l {{ font-size: 9pt; color: #666; }} .kpi .v {{ font-size: 15pt; font-weight: 700; }}
.kpi .d {{ font-size: 9pt; color: #666; }}
ul {{ margin: 4px 0; padding-right: 18px; padding-left: 0; }}
li {{ margin: 2px 0; }}
.refs {{ font-size: 8.5pt; color: #777; }}
a {{ color: #3f3566; text-decoration: none; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9.5pt; }}
th, td {{ border-bottom: 1px solid #e4e0ee; padding: 3px 6px; text-align: right; }}
th {{ background: #f3f0f9; }} td.n, th.n {{ text-align: center; }}
.up {{ color: #1b7f4b; }} .down {{ color: #b3261e; }}
.chip {{ display: inline-block; background: #eef3fb; border-radius: 4px; padding: 0 5px; margin: 1px 2px; font-size: 8.5pt; }}
.muted {{ color: #777; }} h2, h3 {{ break-after: avoid; }} li {{ break-inside: avoid; }}
.note {{ font-size: 8.5pt; color: #777; margin-top: 16px; }}
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def fmt(n) -> str:
    return f"{int(n or 0):,}"


def date_ar(d: str) -> str:
    try:
        x = date.fromisoformat(d[:10])
        return f"{x.day} {AR_MONTHS[x.month - 1]} {x.year}"
    except Exception:
        return d or ""


def change(a, b) -> str:
    if not b:
        return ""
    return f'<span class="{"up" if a >= b else "down"}">{"+" if a >= b else ""}{fmt(a - b)}</span>'


def render(r: dict, meta: dict, arts: dict) -> str:
    src = {s["id"]: s["nameAr"] for s in meta["sources"]}

    def digest(dg, limit=8):
        if not dg or not dg.get("bullets"):
            return '<p class="muted">لا أخبار في هذه الفترة.</p>'
        items = []
        for b in dg["bullets"][:limit]:
            refs, seen = [], set()
            for rid in b.get("refs") or []:
                a = arts.get(rid)
                if not a:
                    continue
                name = a.get("pub") or src.get(a.get("s"), a.get("s"))
                if name in seen:
                    continue
                seen.add(name)
                refs.append(f'<a href="{esc(a.get("u"))}">{esc(name)}</a>')
            ref_html = f'<br><span class="refs">{" · ".join(refs[:4])}</span>' if refs else ""
            items.append(f'<li><span dir="auto">{esc(b["text"])}</span>{ref_html}</li>')
        return f'<ul>{"".join(items)}</ul>'

    kind = "الأسبوعي" if r["type"] == "week" else "الشهري"
    parts = [
        f'<h1>حراك أخبار رؤية عُمان 2040 — التقرير {kind}</h1>',
        f'<p class="sub">{esc(r["label"])}{" — حتى الآن" if r.get("partial") else ""}</p>',
        '<div class="kpis">'
        f'<div class="kpi"><div class="l">أخبار مرتبطة بالرؤية</div><div class="v">{fmt(r["total"])}</div>'
        f'<div class="d">السابقة {fmt(r["prevTotal"])} {change(r["total"], r["prevTotal"])}</div></div>'
        f'<div class="kpi"><div class="l">بانتظار تأكيد الفريق</div><div class="v">{fmt(r["awaiting"])}</div></div>'
        f'<div class="kpi"><div class="l">أولويات بلا أخبار</div><div class="v">{fmt(len(r["silentPriorities"]))}</div></div></div>',
        "<h2>الخلاصة</h2>", digest(r.get("digest")),
    ]
    if r.get("highlights"):
        parts += ["<h2>أرقام الحراك</h2><ul>", *[f"<li>{esc(h)}</li>" for h in r["highlights"]], "</ul>"]
    parts.append('<h2>حسب المحاور</h2><table><tr><th>المحور</th><th class="n">الأخبار</th><th class="n">السابقة</th><th class="n">التغير</th></tr>')
    for a in r["axes"]:
        parts.append(f'<tr><td>{esc(a["nameAr"])}</td><td class="n">{fmt(a["count"])}</td><td class="n">{fmt(a["prev"])}</td>'
                     f'<td class="n">{change(a["count"], a["prev"])}</td></tr>')
    parts.append("</table><h2>حسب الأولويات</h2>")
    for p in sorted(r["priorities"], key=lambda p: -p["count"]):
        if not p["count"]:
            continue
        inds = "".join(f'<span class="chip">{i["code"]} {esc(i["nameAr"][:55])} ({fmt(i["count"])})</span>' for i in p.get("indicators", []))
        heads = "".join(f'<li><a href="{esc(h["url"])}">{esc(h["title"])}</a> <span class="refs">— {esc(src.get(h["source"], h["source"]))}، {date_ar(h["date"])}</span></li>'
                        for h in p.get("headlines", []))
        parts.append(f'<div class="pri"><h3>{p["code"]} — {esc(p["nameAr"])} <span class="muted">({fmt(p["count"])}، السابقة {fmt(p["prev"])})</span></h3>'
                     f'{digest(p.get("digest"), 4)}'
                     f'{f"<div>{inds}</div>" if inds else ""}'
                     f'{f"<p class=refs><b>المصادر:</b></p><ul>{heads}</ul>" if heads else ""}</div>')
    if r.get("silentPriorities"):
        names = {p["code"]: p["nameAr"] for p in meta["priorities"]}
        parts.append(f'<h2>أولويات بلا أخبار</h2><p>{"، ".join(esc(names.get(c, c)) for c in r["silentPriorities"])}</p>')
    parts.append(f'<h2>المصادر</h2><p>{"، ".join(f"{esc(s["nameAr"])} ({fmt(s["count"])})" for s in r["sources"]) or "—"}</p>')
    parts.append(f'<p class="note">رصد إخباري لما نُشر عن أولويات رؤية عُمان 2040، مصنَّف وفق قواعد موثقة (الإصدار {esc(meta["rulesVersion"])}). '
                 'الخلاصة مستخلصة من الأخبار المرفقة روابطها.</p>')
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>{esc(r["label"])}</title></head><body>{"".join(parts)}</body></html>'


def main() -> int:
    try:
        from weasyprint import CSS as WCSS, HTML
    except ImportError:
        print("weasyprint غير مثبت — لن تُبنى ملفات PDF.", file=sys.stderr)
        return 1
    meta = json.loads((SITE / "data" / "meta.json").read_text(encoding="utf-8"))
    arts = {a["id"]: a for a in json.loads((SITE / "data" / "articles.json").read_text(encoding="utf-8"))}
    style = WCSS(string=CSS)
    for old in OUT.glob("*.pdf"):
        old.unlink()
    n = 0
    for item in meta["reports"]:
        r = json.loads((OUT / f"{item['id']}.json").read_text(encoding="utf-8"))
        HTML(string=render(r, meta, arts), base_url=str(ROOT)).write_pdf(OUT / f"{item['id']}.pdf", stylesheets=[style])
        n += 1
    print(f"تم بناء {n} ملف PDF للتقارير.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
