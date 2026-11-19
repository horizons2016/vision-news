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
from datetime import date

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


# جذور تقريبية (أول 4 أحرف بعد «ال») لمقارنة صيغ مختلفة للحدث نفسه: الأوزبكي/أوزبكستان، توقع/توقيع.
_GENERIC = {"اتفا", "مذكر", "تفاه", "توقي", "توقع", "يوقع", "وقعت", "برنا", "تعاو", "تعزي", "لتعز", "شراك", "شرا", "مشرو",
            "افتت", "اطلا", "يدشن", "تدشي", "وزار", "وزير", "هيئه", "شرك", "شركه", "مجلس", "محاف", "جامع", "مركز", "جلال",
            "سلطا", "الس", "يشهد", "يشهدا", "اقتص", "الاق", "ريال", "مليو", "حكوم", "عام", "جديد", "agre", "sign", "mous",
            "memo", "coop", "mini", "auth", "comp", "proj", "laun", "boos", "trad", "inve", "deal", "talk", "with"}


def stems(title: str) -> set[str]:
    out = set()
    for w in tokens(title):
        if w.startswith("ال") and len(w) > 4:
            w = w[2:]
        out.add(w[:4])
    return out


def _days_apart(a: dict, b: dict) -> int:
    try:
        return abs((date.fromisoformat(a.get("d", "")[:10]) - date.fromisoformat(b.get("d", "")[:10])).days)
    except ValueError:
        return 99


def cluster(articles: list[dict]) -> list[list[dict]]:
    """يجمع الأخبار التي تتحدث عن الحدث نفسه (تشابه كلمات العنوان).

    المراسيم السلطانية تصدر دفعة واحدة وتغطيها الصحف بالعربية والإنجليزية بعناوين مختلفة،
    لذلك تُجمع كل أخبار المراسيم الصادرة في اليوم نفسه (±يوم) في حدث واحد."""
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
            st, gs = stems(a["t"]), {x for y in g[1] for x in stems(y["t"])}
            common = st & gs
            if len(common) >= 3 and common - _GENERIC and any(_days_apart(a, x) <= 2 for x in g[1]):
                best = g
                break
            if a.get("ty") == "decree" and any(x.get("ty") == "decree" and _days_apart(a, x) <= 1 for x in g[1]):
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
    arabic = any(a.get("lang") == "ar" for a in g)
    # الخبر الذي له تغطية عربية يتقدم: القارئ عربي، والعنوان العربي أوضح في الخلاصة
    return TYPES[kind]["weight"] + 2 * (sources - 1) + (1 if _NUM.search(g[0]["t"]) else 0) + (2 if arabic else 0)


def rule_digest(articles: list[dict], limit: int = 6) -> list[dict]:
    """«الخلاصة» بالقواعد: أهم الأحداث مرتبة، لكل حدث عنوان ممثل ونوعه وعدد المصادر."""
    groups = cluster(articles)
    for g in groups:
        # النوع الأقوى داخل المجموعة
        g.sort(key=lambda a: -TYPES[a.get("ty", "other")]["weight"])
    groups.sort(key=rank_group, reverse=True)
    out = []
    for g in groups[:limit]:
        kind = g[0].get("ty", "other")
        ar = [a for a in g if a.get("lang") == "ar"] or g
        # في دفعة المراسيم: العنوان الجامع («يصدر 4 مراسيم») أوضح من عنوان مرسوم واحد
        lead = next((a for a in ar if kind == "decree" and normalize("مراسيم") in normalize(a["t"])), ar[0])
        out.append({"text": lead["t"], "type": kind, "refs": [a["id"] for a in g][:6],
                    "sources": len({a["s"] for a in g})})
    return out
