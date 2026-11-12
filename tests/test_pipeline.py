"""اختبارات المسار كاملًا على بيانات تجريبية (بلا إنترنت).  python -m pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from taxonomy.classify import classify, clean_text  # noqa: E402

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>سلطنة عُمان توقع اتفاقيتين لمشروعات الهيدروجين الأخضر بالدقم</title><link>https://ex.om/a/1?utm_source=x</link>
<description>وقعت هيدروم اتفاقيتين لتطوير الطاقة المتجددة</description><pubDate>Tue, 10 Nov 2026 06:00:00 GMT</pubDate></item>
<item><title>المنتخب الوطني لكرة القدم يفوز في مباراة ودية</title><link>https://ex.om/a/2</link><description>رياضة</description></item>
<item><title>Trump says US will act on Hormuz</title><link>https://ex.om/a/3</link><description>Washington</description></item>
<item><title>سلطنة عُمان توقع اتفاقيتين لمشروعات الهيدروجين الأخضر بالدقم</title><link>https://other.om/x</link><description>نفس الخبر برابط آخر</description></item>
<item><title>البنك المركزي العماني يرفع سعر الفائدة</title><link>https://ex.om/a/4</link><description>قرار نقدي</description></item>
</channel></rss>"""


def test_classifier_basics():
    r = classify("Oman signs two pacts for green hydrogen projects", "", omani_outlet=True)
    assert r.outcome == "relevant" and r.indicators[0]["id"] == "indicator_34"
    assert classify("المنتخب الوطني لكرة القدم يفوز في مباراة", "", True).outcome == "excluded_general"
    assert classify("Trump says US will act on Hormuz", "", True).outcome == "no_oman_context"
    assert clean_text("Oman&amp;#039;s &quot;plan&quot;") == "Oman's \"plan\""
    # "طاقة" (ولاية) يجب ألا تُعدّ سياقًا عمانيًا داخل «الطاقة»
    assert classify("أسعار الطاقة في أوروبا", "", False).oman_context == "none"


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    import common
    for name in ("DATA", "ARTICLES", "STATE"):
        pass
    monkeypatch.setattr(common, "DATA", tmp_path / "data")
    monkeypatch.setattr(common, "ARTICLES", tmp_path / "data" / "articles")
    monkeypatch.setattr(common, "STATE", tmp_path / "data" / "state")
    monkeypatch.setattr(common, "SITE", tmp_path / "site")
    monkeypatch.setattr(common, "REPORTS", tmp_path / "reports")
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.json").write_text(json.dumps({"sources": [{"id": "ex", "nameAr": "مثال", "nameEn": "Ex", "lang": "ar",
        "omaniOutlet": True, "publishes": "daily", "active": True, "feeds": ["https://ex.om/rss"], "pages": []}]}), encoding="utf-8")
    for f in ("settings.json", "indicator_links.csv"):
        (cfg / f).write_bytes((ROOT / "config" / f).read_bytes())
    monkeypatch.setattr(common, "CONFIG", cfg)
    import collect, build, ai
    for mod in (collect, build, ai):
        for name in ("DATA", "STATE", "CONFIG", "SITE", "REPORTS"):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, getattr(common, name))

    class Resp:
        def __init__(self, body): self.content = body.encode(); self.text = body; self.status_code = 200; self.url = "https://ex.om/rss"
        def raise_for_status(self): pass
    monkeypatch.setattr(collect, "get", lambda url: Resp(RSS))
    monkeypatch.setattr(collect, "fetch_body", lambda url: "")
    return tmp_path, collect, build, ai, common


def test_collect_build_and_decisions(repo):
    tmp, collect, build, ai, common = repo
    t = collect.run()
    assert t["found"] == 5 and t["kept"] == 2 and t["duplicates"] == 1 and t["excluded"] == 2
    arts = common.load_articles()
    hyd = next(a for a in arts.values() if "الهيدروجين" in a["title"])
    assert hyd["status"] == "auto" and hyd["priorities"][0]["id"] == "P10"
    assert any(i["id"] == "I34" for i in hyd["indicators"])
    # تشغيل ثانٍ: لا شيء جديد (الروابط محفوظة في seen)
    assert collect.run()["new"] == 0

    assert build.main() == 0
    meta = json.loads((tmp / "site" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["totals"]["counted"] == 1

    # قرار صحيح: تعديل الخبر المحتمل إلى P05
    cb = next(a for a in arts.values() if "المركزي" in a["title"])
    (tmp / "data" / "decisions.csv").write_text(f"معرف الخبر,القرار,الأولوية,المؤشرات,بواسطة,ملاحظة\n{cb['id']},تعديل,P05,,محمد,\n", encoding="utf-8")
    assert build.main() == 0
    meta = json.loads((tmp / "site" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["totals"]["counted"] == 2

    # قرار خاطئ: مؤشر لا يتبع الأولوية → يتوقف البناء
    (tmp / "data" / "decisions.csv").write_text(f"x,القرار,ا,ا,ا,ا\n{cb['id']},تعديل,P05,I34,محمد,\n", encoding="utf-8")
    assert build.main() == 1
    assert "لا تتبع الأولوية" in (tmp / "data" / "build_report.md").read_text(encoding="utf-8")


def test_ai_result_rules():
    import ai
    valid_p = {f"P{n:02d}" for n in range(1, 13)}
    valid_i = {"I19": "P06", "I34": "P10"}
    a = {"id": "1"}
    assert ai.apply_result(a, {"relevant": True, "priority": "P06", "indicators": ["I19", "I34"], "confidence": 0.9}, "m", valid_p, valid_i) == "auto"
    assert [i["id"] for i in a["indicators"]] == ["I19"]  # I34 لا يتبع P06
    assert ai.apply_result({"id": "2"}, {"relevant": True, "priority": "P06", "confidence": 0.6}, "m", valid_p, valid_i) == "review"
    assert ai.apply_result({"id": "3"}, {"relevant": False, "confidence": 0.9}, "m", valid_p, valid_i) == "drop"
    assert ai.apply_result({"id": "4"}, {"relevant": True, "priority": "P99", "confidence": 0.9}, "m", valid_p, valid_i) == "drop"
    assert ai.parse('خطأ {"results":[{"i":0,"relevant":true}]} ') == [{"i": 0, "relevant": True}]
