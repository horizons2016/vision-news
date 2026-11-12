"""مصنِّف أخبار رؤية عُمان 2040 بالقواعد.

يربط الخبر بالمحور ← الأولوية ← المؤشر (القائمة المحدثة: 12 أولوية و38 مؤشرًا).
القواعد والمصطلحات كلها في taxonomy/rules.json؛ أي تعديل فيها يستلزم رفع رقم الإصدار "version".

النتيجة (outcome):
  relevant          ارتباط مُثبت بأولوية واحدة على الأقل (وربما مؤشرات).
  uncertain         سياق عماني وإشارة موضوعية لكنها دون حد الإثبات: هذه وحدها تذهب للذكاء الاصطناعي إن كان مفعّلًا.
  excluded_general  خبر عام (رياضة، طقس، حوادث...) بلا دليل قوي على مؤشر.
  no_oman_context   لا يخص عُمان.
  no_match          عُماني لكن لا علاقة له بالأولويات.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
_ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"


# ---------------------------------------------------------------- النص
def clean_text(text: str) -> str:
    """إزالة الوسوم وفك ترميز HTML (مرتين لعلاج الترميز المزدوج مثل &amp;quot;)."""
    if not text:
        return ""
    text = re.sub(r"<!\[CDATA\[|\]\]>", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(html.unescape(text))
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def normalize(text: str) -> str:
    """توحيد الحروف العربية والأرقام وإزالة التشكيل والرموز."""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[٠-٩]", lambda m: str(_ARABIC_INDIC.index(m.group(0))), t)
    t = re.sub(r"[ً-ٰٟـ]", "", t)
    t = re.sub(r"[أإآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه")
    t = re.sub(r"[​-‏‪-‮]", "", t)
    t = t.lower()
    t = re.sub(r"[^\w\s]|_", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_LATIN = re.compile(r"[a-z0-9]")
_ARABIC = re.compile(r"[؀-ۿ]")


@lru_cache(maxsize=4096)
def _latin_re(term: str) -> re.Pattern:
    return re.compile(r"(^|\s)" + re.escape(term) + r"(s|es)?(\s|$)")


def contains(text: str, term: str) -> bool:
    """مطابقة كلمة كاملة للاتيني، ومطابقة جزئية للعربي (تسمح بالسوابق و/ب/ال)."""
    if not term:
        return False
    if _LATIN.search(term) and not _ARABIC.search(term):
        return bool(_latin_re(term).search(text))
    return term in text


# ---------------------------------------------------------------- القواعد
@dataclass
class Term:
    raw: str
    norm: str


def _compile(terms) -> list[Term]:
    out = []
    for raw in terms:
        n = normalize(raw)
        if n:
            out.append(Term(raw, n))
    return out


def _any(text: str, terms: list[Term]) -> bool:
    return any(contains(text, t.norm) for t in terms)


def _remove(text: str, terms: list[Term]) -> str:
    for t in terms:
        if contains(text, t.norm):
            text = " ".join(text.split(t.norm))
    return text


@dataclass
class Rules:
    version: str
    th: dict
    priorities: list
    indicators: list
    neutralizers: list[Term]
    exclusions: list[Term]
    jordan: list[Term]
    strong_oman: list[Term]
    weak_oman: list[Term]
    foreign: list[Term]
    denial: list[Term]
    blocking: set
    labels: dict
    sub_confirm: dict


@lru_cache(maxsize=1)
def load_rules() -> Rules:
    r = json.loads((HERE / "rules.json").read_text(encoding="utf-8"))
    ref = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
    priorities = [{"id": pid, "terms": _compile(terms)} for pid, terms in r["priority_terms"].items()]
    indicators = []
    sub_confirm = {}
    for ind in ref["indicators"]:
        alias = r["indicator_aliases"].get(ind["stableId"], {"strong": []})
        for s in ind.get("subItems", []):
            sub_confirm[(ind["stableId"], s["key"])] = s.get("needsStructureConfirmation", False)
        indicators.append({
            "id": ind["stableId"],
            "priority": ind["priorityStableId"],
            "strong": _compile([ind["nameAr"], ind["nameEn"], *alias.get("strong", [])]),
            "combos": [[_compile(g) for g in combo] for combo in alias.get("combos", [])],
            "negations": _compile(alias.get("negations", [])),
            "subs": [(k, _compile(v)) for k, v in alias.get("subItemTerms", {}).items()],
        })
    return Rules(
        version=r["version"], th=r["thresholds"], priorities=priorities, indicators=indicators,
        neutralizers=_compile(r["global_neutralizers"]), exclusions=_compile(r["general_exclusions"]),
        jordan=_compile(r["jordan_markers"]), strong_oman=_compile(r["strong_oman_markers"]),
        weak_oman=_compile(r["weak_oman_markers"]), foreign=_compile(r["foreign_markers"]),
        denial=_compile(r["denial_terms"]), blocking=set(r["blocking_review_reasons"]),
        labels=r["review_reason_labels"], sub_confirm=sub_confirm,
    )


# ---------------------------------------------------------------- التصنيف
@dataclass
class Result:
    outcome: str
    oman_context: str
    priorities: list = field(default_factory=list)   # [{"id","score","terms"}]
    indicators: list = field(default_factory=list)   # [{"id","priority","score","evidence","terms","subItems"}]
    review_reasons: list = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return any(r in load_rules().blocking for r in self.review_reasons)


def oman_context(text: str, title: str, omani_outlet: bool) -> str:
    R = load_rules()
    if _any(text, R.strong_oman):
        return "strong"
    if _any(text, R.weak_oman) and not _any(text, R.jordan):
        return "weak"
    # سياق المصدر: خبر من صحيفة عمانية يُعدّ عمانيًا ما لم يذكر عنوانه بلدًا أجنبيًا.
    if omani_outlet and not _any(title, R.foreign):
        return "source"
    return "none"


def _score_indicators(title: str, body: str) -> list:
    R = load_rules()
    hits = []
    for ind in R.indicators:
        t = _remove(title, ind["negations"])
        b = _remove(body, ind["negations"])
        score, matched, strong = 0, [], False
        for term in ind["strong"]:
            if contains(t, term.norm):
                score += 3; matched.append(term.raw); strong = True
            elif contains(b, term.norm):
                score += 2; matched.append(term.raw); strong = True
        for combo in ind["combos"]:
            if not all(_any(t, g) or _any(b, g) for g in combo):
                continue
            score += 2 if any(_any(t, g) for g in combo) else 1
            matched.append(" + ".join(next((x.raw for x in g if contains(t, x.norm) or contains(b, x.norm)), "") for g in combo))
        if score == 0:
            continue
        full = f"{t} {b}"
        subs = [k for k, terms in ind["subs"] if _any(full, terms)]
        hits.append({"id": ind["id"], "priority": ind["priority"], "score": score,
                     "evidence": "strong" if strong else "combo", "terms": matched, "subItems": subs})
    hits.sort(key=lambda h: -h["score"])  # ترتيب مستقر مثل JS
    return hits


def classify(raw_title: str, raw_content: str = "", omani_outlet: bool = False) -> Result:
    R = load_rules()
    th = R.th
    title = _remove(normalize(clean_text(raw_title)), R.neutralizers)
    body = _remove(normalize(clean_text(raw_content)), R.neutralizers)
    ctx = oman_context(f"{title} {body}", title, omani_outlet)

    all_ind = _score_indicators(title, body)
    linked = [h for h in all_ind if h["score"] >= th["INDICATOR_MIN_SCORE"]][: th["MAX_INDICATORS_PER_ARTICLE"]]

    pr = []
    for p in R.priorities:
        score, matched = 0, []
        for term in p["terms"]:
            if contains(title, term.norm):
                score += 2; matched.append(term.raw)
            elif contains(body, term.norm):
                score += 1; matched.append(term.raw)
        score += sum(h["score"] for h in linked if h["priority"] == p["id"])
        if score > 0:
            pr.append({"id": p["id"], "score": score, "terms": matched})
    pr.sort(key=lambda p: -p["score"])

    has_strong = any(h["evidence"] == "strong" for h in linked)
    if _any(title, R.exclusions) and not has_strong:
        return Result("excluded_general", ctx, pr, [])
    if ctx == "none":
        return Result("no_oman_context", ctx, pr, [])

    rel = [p for p in pr if p["score"] >= th["PRIORITY_MIN_SCORE"] or any(h["priority"] == p["id"] for h in linked)]
    if not rel:
        outcome = "uncertain" if (pr or all_ind) else "no_match"
        return Result(outcome, ctx, pr, [])

    reasons = []
    top = rel[0]
    second = rel[1] if len(rel) > 1 else None
    if second and second["score"] >= top["score"] * th["CLOSE_RATIO"]:
        reasons.append("multi_priority_close")
    if ctx == "weak":
        reasons.append("weak_oman_context")
    if ctx == "source" and top["score"] < th["PRIORITY_MIN_SCORE"] + 1 and not has_strong:
        reasons.append("source_context_only")
    if any(h["evidence"] == "combo" for h in linked):
        reasons.append("weak_indicator_evidence")
    if not linked:
        reasons.append("priority_only")
    if any(R.sub_confirm.get((h["id"], k)) for h in linked for k in h["subItems"]):
        reasons.append("subitem_structure_unconfirmed")
    if _any(f"{title} {body}", R.denial):
        reasons.append("denial_or_rumor")
    return Result("relevant", ctx, rel, linked, reasons)
