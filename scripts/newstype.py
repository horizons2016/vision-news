"""نوع الخبر وتجميع تغطيات الحدث الواحد وصياغة «الخلاصة» بالقواعد (بدون ذكاء اصطناعي).

أنواع الأخبار مرتبة حسب الأهمية:
  decree        مرسوم سلطاني
  decision      قرار وزاري / تنظيمي
  international تقرير أو تقييم دولي (صندوق النقد، البنك الدولي، وكالات التصنيف...)
  agreement     اتفاقية / مذكرة تفاهم / توقيع
  figures       أرقام وإحصاءات (ارتفع، انخفض، بلغ...)
  project       مشروع / إطلاق / افتتاح
  event         فعالية / مؤتمر / ملتقى
  other         خبر عام
"""
from __future__ import annotations

import re

from taxonomy.classify import clean_text, contains, normalize

TYPES = {
    "decree": {"label": "مرسوم سلطاني", "icon": "📜", "weight": 7},
    "decision": {"label": "قرار", "icon": "⚖️", "weight": 6},
    "international": {"label": "تقييم دولي", "icon": "🌐", "weight": 5},
    "agreement": {"label": "اتفاقية", "icon": "🤝", "weight": 5},
    "figures": {"label": "أرقام", "icon": "📊", "weight": 4},
    "project": {"label": "مشروع", "icon": "🏗️", "weight": 3},
    "event": {"label": "فعالية", "icon": "🗓️", "weight": 1},
    "other": {"label": "خبر", "icon": "📰", "weight": 2},
}

_T = {
    "decree": ["مرسوم سلطاني", "مراسيم سلطانية", "المرسوم السلطاني", "royal decree", "royal decrees"],
    "decision": ["قرار وزاري", "قرارا وزاريا", "قرارًا وزاريًا", "يصدر قرارا", "يصدر قرارًا", "أصدر قرارا", "أصدر قرارًا", "تصدر قرارا",
                 "قرار رقم", "لائحة تنفيذية", "اللائحة التنفيذية", "ministerial decision", "ministerial decree", "issues decision",
                 "executive regulations", "new regulation", "bans", "يحظر", "حظر", "exempts", "إعفاء", "اللائحة", "مجلس الوزراء يقرر", "يعتمد مجلس الوزراء", "قرر مجلس الوزراء"],
    "international": ["صندوق النقد الدولي", "البنك الدولي", "ستاندرد آند بورز", "موديز", "فيتش", "وكالة التصنيف", "التصنيف الائتماني",
                      "منظمة التعاون الاقتصادي", "المنتدى الاقتصادي العالمي", "الأمم المتحدة", "imf", "international monetary fund",
                      "world bank", "moody s", "moodys", "fitch", "s p global", "standard poor", "credit rating", "oecd",
                      "world economic forum", "standard chartered", "united nations", "unctad", "wto"],
    "agreement": ["اتفاقية", "اتفاقيتين", "اتفاقيات", "مذكرة تفاهم", "مذكرتي تفاهم", "مذكرات تفاهم", "توقيع", "يوقع", "يوقعان", "توقعان", "وقعت", "تم التوقيع",
                  "agreement", "agreements", "mou", "mous", "memorandum", "signs", "signed", "inks", "inked", "pact", "pacts", "deal"],
    "figures": ["ارتفع", "ارتفاع", "انخفض", "انخفاض", "تراجع", "بلغ", "بلغت", "نمو", "نسبة", "بالمائة", "بالمئة", "إحصاء", "إحصائيات",
                "المركز الوطني للإحصاء", "rose", "rises", "rise", "fell", "falls", "drop", "growth", "grew", "reached", "per cent",
                "percent", "ncsi", "statistics", "surge", "jump"],
    "project": ["مشروع", "مشروعات", "مشاريع", "تدشين", "يدشن", "افتتاح", "يفتتح", "إطلاق", "تطلق", "يطلق", "إنشاء", "تشغيل",
                "project", "projects", "launch", "launches", "launched", "inaugurates", "inaugurated", "opens", "plant", "construction"],
    "event": ["ملتقى", "مؤتمر", "ندوة", "ورشة", "حلقة عمل", "معرض", "منتدى", "فعالية", "فعاليات", "يحتفل", "احتفال", "forum", "conference",
              "seminar", "workshop", "exhibition", "summit", "symposium", "celebrates"],
}
_C = {k: [normalize(t) for t in v] for k, v in _T.items()}
_NUM = re.compile(r"\d")
ORDER = ["decree", "decision", "international", "agreement", "figures", "project", "event"]


def news_type(title: str, excerpt: str = "") -> str:
    t = normalize(clean_text(title))
    b = normalize(clean_text(excerpt))[:300]
    for kind in ORDER:
        terms = _C[kind]
        hit_title = any(contains(t, x) for x in terms)
        if kind == "figures":
            # الأرقام تحتاج رقمًا فعليًا في العنوان
            if hit_title and _NUM.search(t):
                return kind
            continue
        if hit_title:
            return kind
    return "other"


# ---------------------------------------------------------------- تجميع تغطيات الحدث الواحد
_STOP = set(normalize(" ".join([
    "في من على الى إلى عن مع هذا هذه التي الذي كما بعد قبل حول خلال تم ان أن او أو ثم و ال سلطنة عمان عُمان العمانية العماني",
    "the and for with from that this has have are was will its into over after says oman omani muscat to of in on a an at by as is",
])).split())


def tokens(title: str) -> set[str]:
    return {w for w in normalize(clean_text(title)).split() if len(w) > 2 and w not in _STOP}


def cluster(articles: list[dict]) -> list[list[dict]]:
    """يجمع الأخبار التي تتحدث عن الحدث نفسه (تشابه كلمات العنوان)."""
    groups: list[tuple[set, list]] = []
    for a in sorted(articles, key=lambda x: x.get("d", "")):
        tk = tokens(a["t"])
        best = None
        for g in groups:
            inter = len(tk & g[0])
            union = len(tk | g[0]) or 1
            if inter >= 4 or (inter >= 2 and inter / union >= 0.5):
                best = g
                break
        if best:
            best[0].update(tk)
            best[1].append(a)
        else:
            groups.append((set(tk), [a]))
    return [g[1] for g in groups]


def rank_group(g: list[dict]) -> float:
    kind = g[0].get("ty", "other")
    sources = len({a["s"] for a in g})
    return TYPES[kind]["weight"] + 2 * (sources - 1) + (1 if _NUM.search(g[0]["t"]) else 0)


def rule_digest(articles: list[dict], limit: int = 6) -> list[dict]:
    """«الخلاصة» بالقواعد: أهم الأحداث مرتبة، لكل حدث عنوان ممثل ونوعه وعدد المصادر."""
    groups = cluster(articles)
    for g in groups:
        # النوع الأقوى داخل المجموعة
        g.sort(key=lambda a: -TYPES[a.get("ty", "other")]["weight"])
    groups.sort(key=rank_group, reverse=True)
    out = []
    for g in groups[:limit]:
        lead = next((a for a in g if a.get("lang") == "ar"), g[0])
        kind = g[0].get("ty", "other")
        out.append({"text": lead["t"], "type": kind, "refs": [a["id"] for a in g][:6],
                    "sources": len({a["s"] for a in g})})
    return out
