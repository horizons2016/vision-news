"""تحليل الحراك: أين يتركز الحراك الإخباري للرؤية، وما نوعيته، وكيف يتغير.

المنهجية (موثقة في صفحة «تحليل الحراك»):
1. الحدث لا الخبر: تغطيات الحدث الواحد (عناوين متشابهة خلال 7 أيام) تُدمج في حدث واحد،
   حتى لا يتضخم حدث غطته صحف كثيرة.
2. وزن النوعية: لكل نوع وزن (مرسوم 3، قرار 2.5، اتفاقية 2، تقييم دولي 2، أرقام 1.5، مشروع 1.5، خبر 1، فعالية 0.5)،
   ويزيد 25% لكل مصدر إضافي غطّى الحدث (حتى 75%).
3. الحدث «جوهري» إن كان مرسومًا أو قرارًا أو اتفاقية أو تقييمًا دوليًا أو أرقامًا.
4. الفترة: آخر 13 أسبوعًا (ربع سنة) مقابل الـ13 التي قبلها، مع سلسلة أسبوعية.
الأرقام تقيس الحراك الإخباري (ما نُشر)، وهي دليل ارتباط لا قياس أثر.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from newstype import TYPES, tokens

WEIGHTS = {"decree": 3, "decision": 2.5, "agreement": 2, "international": 2, "figures": 1.5, "project": 1.5, "other": 1, "event": 0.5}
SUBSTANTIVE = {"decree", "decision", "agreement", "international", "figures"}
WINDOW_WEEKS = 13
MERGE_DAYS = 7


def build_events(arts: list[dict]) -> list[dict]:
    """يدمج الأخبار (بالصيغة المختصرة) في أحداث."""
    events: list[dict] = []
    open_ev: list[dict] = []
    for a in sorted(arts, key=lambda x: x["d"]):
        d = date.fromisoformat(a["d"])
        tk = tokens(a["t"])
        open_ev = [e for e in open_ev if (d - e["last"]).days <= MERGE_DAYS]
        hit = None
        for e in open_ev:
            inter = len(tk & e["tk"])
            union = len(tk | e["tk"]) or 1
            if inter >= 4 or (inter >= 2 and inter / union >= 0.5):
                hit = e
                break
        if hit:
            hit["arts"].append(a)
            hit["tk"] |= tk
            hit["last"] = d
        else:
            e = {"tk": set(tk), "arts": [a], "first": d, "last": d}
            open_ev.append(e)
            events.append(e)
    out = []
    for e in events:
        types = [x.get("ty", "other") for x in e["arts"]]
        ty = max(types, key=lambda t: WEIGHTS[t])
        sources = len({x["s"] for x in e["arts"]})
        lead = next((x for x in e["arts"] if x.get("lang") == "ar"), e["arts"][0])
        out.append({
            "d": e["first"].isoformat(), "ty": ty, "sources": sources, "n": len(e["arts"]),
            "w": round(WEIGHTS[ty] * min(1.75, 1 + 0.25 * (sources - 1)), 2),
            "p": sorted({c for x in e["arts"] for c in x["p"]}), "i": sorted({c for x in e["arts"] for c in x["i"]}),
            "t": lead["t"], "u": lead["u"], "ids": [x["id"] for x in e["arts"]][:8],
        })
    return out


def analyse(compact_arts: list[dict], meta_axes: list, pri: dict, ind: dict, today: date, week_start) -> dict:
    ws = week_start(today)
    weeks = [ws - timedelta(weeks=k) for k in range(WINDOW_WEEKS - 1, -1, -1)]
    cur_start = weeks[0]
    prev_start = cur_start - timedelta(weeks=WINDOW_WEEKS)
    counted = [a for a in compact_arts if a["st"] in ("auto", "confirmed")]
    events = build_events([a for a in counted if a["d"] >= prev_start.isoformat()])
    cur = [e for e in events if e["d"] >= cur_start.isoformat()]
    prev = [e for e in events if e["d"] < cur_start.isoformat()]
    wi = {w.isoformat(): n for n, w in enumerate(weeks)}
    axis_of = {c: p["axis"] for c, p in pri.items()}

    def node_stats(sel_cur, sel_prev):
        w = sum(e["w"] for e in sel_cur)
        pw = sum(e["w"] for e in sel_prev)
        comp = Counter(e["ty"] for e in sel_cur)
        series = [0.0] * WINDOW_WEEKS
        for e in sel_cur:
            k = wi.get(week_start(date.fromisoformat(e["d"])).isoformat())
            if k is not None:
                series[k] += e["w"]
        sub = sum(1 for e in sel_cur if e["ty"] in SUBSTANTIVE)
        r4, p4 = sum(series[-5:-1]), sum(series[-9:-5])  # آخر 4 أسابيع مكتملة مقابل الأربعة قبلها
        return {
            "events": len(sel_cur), "articles": sum(e["n"] for e in sel_cur), "weight": round(w, 1),
            "prevWeight": round(pw, 1), "prevEvents": len(sel_prev),
            "change": (round(100 * (w - pw) / pw) if pw else None),
            "recent": round(r4, 1), "recentPrev": round(p4, 1),
            "change4": (round(100 * (r4 - p4) / p4) if p4 >= 2 else None),
            "substantive": sub, "subRatio": round(sub / len(sel_cur), 2) if sel_cur else 0,
            "types": dict(comp), "series": [round(x, 1) for x in series],
            "lastSubstantive": max((e["d"] for e in sel_cur + sel_prev if e["ty"] in SUBSTANTIVE), default=None),
        }

    total_w = sum(e["w"] for e in cur) or 1
    pri_out = {}
    for c in pri:
        sc = [e for e in cur if c in e["p"]]
        sp = [e for e in prev if c in e["p"]]
        st = node_stats(sc, sp)
        st["share"] = round(100 * st["weight"] / total_w, 1)
        top = sorted([e for e in sc if e["ty"] in SUBSTANTIVE], key=lambda e: (-e["w"], e["d"]))[:6]
        st["top"] = [{k: e[k] for k in ("d", "ty", "t", "u", "sources")} for e in top]
        pri_out[c] = st
    axes_out = {}
    for ax in meta_axes:
        ids = set(ax["priorities"])
        sc = [e for e in cur if set(e["p"]) & ids]
        sp = [e for e in prev if set(e["p"]) & ids]
        st = node_stats(sc, sp)
        st["share"] = round(100 * st["weight"] / total_w, 1)
        axes_out[ax["id"]] = st
    ind_out = {}
    for c in ind:
        sc = [e for e in cur if c in e["i"]]
        sp = [e for e in prev if c in e["i"]]
        st = node_stats(sc, sp)
        st.pop("series")
        top = sorted(sc, key=lambda e: (-e["w"], e["d"]))[:3]
        st["top"] = [{k: e[k] for k in ("d", "ty", "t", "u")} for e in top]
        ind_out[c] = st

    # الأولويات المتقاطعة: أحداث تخدم أولويتين أو أكثر
    pairs = Counter()
    for e in cur:
        ps = e["p"]
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                pairs[(ps[i], ps[j])] += 1
    cross = [{"a": a, "b": b, "events": n} for (a, b), n in pairs.most_common(12)]

    gaps = [c for c in ind if ind_out[c]["substantive"] == 0]
    first_data = min((a["d"] for a in counted), default=today.isoformat())
    return {
        "window": {"start": cur_start.isoformat(), "end": (ws + timedelta(days=6)).isoformat(), "weeks": [w.isoformat() for w in weeks],
                   "prevStart": prev_start.isoformat(), "prevComplete": first_data <= prev_start.isoformat()},
        "weights": WEIGHTS, "substantiveTypes": sorted(SUBSTANTIVE), "typeLabels": {k: v["label"] for k, v in TYPES.items()},
        "totals": {"events": len(cur), "articles": sum(e["n"] for e in cur), "weight": round(total_w, 1),
                   "substantive": sum(1 for e in cur if e["ty"] in SUBSTANTIVE), "prevEvents": len(prev),
                   "types": dict(Counter(e["ty"] for e in cur))},
        "axes": axes_out, "priorities": pri_out, "indicators": ind_out, "cross": cross, "gaps": gaps,
        "axisOf": axis_of,
    }
