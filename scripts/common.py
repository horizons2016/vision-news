"""أدوات مشتركة: المسارات، قراءة/كتابة البيانات، توحيد الروابط، التواريخ."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from taxonomy.classify import clean_text, normalize, load_rules  # noqa: E402

DATA = ROOT / "data"
ARTICLES = DATA / "articles"
STATE = DATA / "state"
CONFIG = ROOT / "config"
SITE = ROOT / "site"
REPORTS = ROOT / "reports"
TAXONOMY = ROOT / "taxonomy"

MUSCAT = timezone(timedelta(hours=4))
TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid", "source", "campaign", "oc"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_muscat(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(MUSCAT)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data, indent=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


def url_key(raw: str) -> str:
    """صيغة موحّدة للرابط لكشف التكرار: بلا http/www/وسوم التتبع/الشرطة الأخيرة."""
    raw = (raw or "").strip()
    try:
        u = urlsplit(raw)
        host = (u.hostname or "").lower().removeprefix("www.")
        path = "/".join(p for p in u.path.split("/") if p != "") if u.path else ""
        q = sorted((k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith("utm_") and k.lower() not in TRACKING)
        return f"{host}/{path}" + (f"?{urlencode(q)}" if q else "")
    except ValueError:
        return raw.lower().rstrip("/")


def article_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def title_key(title: str) -> str:
    """بصمة العنوان لكشف نفس الخبر بروابط مختلفة."""
    return hashlib.sha1(normalize(clean_text(title)).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- الأرشيف (ملف لكل شهر)
def shard_for(article: dict) -> Path:
    month = (article.get("publishedAt") or article["collectedAt"])[:7]
    return ARTICLES / f"{month}.jsonl"


def load_articles() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(ARTICLES.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = json.loads(line)
                out[a["id"]] = a
    return out


def save_articles(articles: dict[str, dict]) -> None:
    shards: dict[Path, list] = {}
    for a in articles.values():
        shards.setdefault(shard_for(a), []).append(a)
    ARTICLES.mkdir(parents=True, exist_ok=True)
    keep = set()
    for path, rows in shards.items():
        rows.sort(key=lambda a: (a.get("publishedAt") or a["collectedAt"], a["id"]))
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        keep.add(path)
    for f in ARTICLES.glob("*.jsonl"):
        if f not in keep:
            f.unlink()


def short_code(stable_id: str) -> str:
    """vision_priority_06 → P06 ، indicator_19 → I19"""
    n = stable_id.rsplit("_", 1)[-1]
    return ("P" if "priority" in stable_id else "I") + n


def classification_fields(result, method: str = "rules") -> dict:
    """تحويل نتيجة المصنف إلى حقول الخبر المحفوظة."""
    rules = load_rules()
    pr = [{"id": short_code(p["id"]), "score": p["score"]} for p in result.priorities]
    ind = [{"id": short_code(h["id"]), "score": h["score"], "evidence": h["evidence"]} for h in result.indicators]
    terms = []
    for h in result.indicators:
        terms += h["terms"]
    for p in result.priorities[:2]:
        terms += p["terms"]
    seen, uniq = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    if result.outcome == "relevant":
        status = "review" if result.needs_review else "auto"
    else:
        status = "uncertain"
    return {
        "outcome": result.outcome,
        "status": status,
        "method": method,
        "context": result.oman_context,
        "priorities": pr,
        "indicators": ind,
        "terms": uniq[:8],
        "reasons": result.review_reasons,
        "rulesVersion": rules.version,
    }


def legislation_boost(result, title: str, excerpt: str):
    """المراسيم السلطانية والقرارات تُحفظ دائمًا (إن كانت عُمانية) وتُربط بأولوية التشريع والقضاء والرقابة."""
    from newstype import news_type
    if result.oman_context == "none" or news_type(title, excerpt) not in ("decree", "decision"):
        return result
    if not any(p["id"] == "vision_priority_11" for p in result.priorities):
        result.priorities = result.priorities + [{"id": "vision_priority_11", "score": 3, "terms": ["تشريع"]}]
    if result.outcome != "relevant":
        result.outcome = "relevant"
        result.priorities = [p for p in result.priorities if p["id"] == "vision_priority_11"] + \
            [p for p in result.priorities if p["id"] != "vision_priority_11" and p["score"] >= 3]
        result.indicators = []
        result.review_reasons = ["priority_only"]
    return result
