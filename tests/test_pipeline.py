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
    for f in ("settings.json",):
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
    monkeypatch.setattr(collect, "get", lambda url, verify=True: Resp(RSS))
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


def test_news_types_and_legislation():
    import sys
    from newstype import news_type, rule_digest
    from common import legislation_boost
    assert news_type("صدور مرسوم سلطاني بإصدار قانون العمل") == "decree"
    assert news_type("قرار وزاري بتنظيم مزاولة المهنة") == "decision"
    assert news_type("World Bank raises Oman's 2026 GDP growth forecast to 3.1%") == "international"
    assert news_type("Oman signs two pacts for green hydrogen projects") == "agreement"
    assert news_type("Oman port cargo jumps to 146 million tonnes") == "figures"
    assert news_type("يتوقع نمو الاقتصاد") != "agreement"
    r = legislation_boost(classify("مرسوم سلطاني رقم 5/2026 بإنشاء هيئة", "", True), "مرسوم سلطاني رقم 5/2026 بإنشاء هيئة", "")
    assert r.outcome == "relevant" and r.priorities[0]["id"] == "vision_priority_11"
    arts = [{"id": "a", "t": "توقيع 10 اتفاقيات استثمارية في الظاهرة", "s": "x", "d": "2026-11-01", "ty": "agreement", "lang": "ar"},
            {"id": "b", "t": "توقيع 10 اتفاقيات استثمارية بمحافظة الظاهرة", "s": "y", "d": "2026-11-01", "ty": "agreement", "lang": "ar"},
            {"id": "c", "t": "ملتقى للشباب", "s": "x", "d": "2026-11-02", "ty": "event", "lang": "ar"}]
    d = rule_digest(arts)
    assert d[0]["sources"] == 2 and set(d[0]["refs"]) == {"a", "b"} and len(d) == 2


def test_newsletter(repo, monkeypatch):
    tmp, collect, build, ai, common = repo
    import newsletter
    collect.run()
    monkeypatch.setenv("BUILD_TODAY", "2026-11-14")
    assert build.main() == 0
    monkeypatch.setattr(newsletter, "SITE", common.SITE)
    monkeypatch.setattr(newsletter, "STATE", common.STATE)
    sent = []
    monkeypatch.setattr(newsletter, "smtp_send", lambda msgs: sent.extend(msgs))
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("RECIPIENTS", "a@x.om, P10\nb@x.om, ALL\nbad-line\nc@x.om, P99")
    recips, errs = newsletter.parse_recipients(__import__("os").environ["RECIPIENTS"], {f"P{n:02d}" for n in range(1, 13)})
    assert [r["email"] for r in recips] == ["a@x.om", "b@x.om"] and len(errs) == 2
    assert newsletter.main(["preview", "--week", "2026-11-08"]) == 0
    assert sent[-1]["To"] == "me@gmail.com" and sent[-1]["Subject"].startswith("[معاينة]")
    assert newsletter.main(["send", "--week", "2026-11-08"]) == 0
    a_msg = next(m for m in sent if m["To"] == "a@x.om")
    body = a_msg.get_body(("html",)).get_content()
    assert "الهيدروجين" in body and "ex.om" in body and "<img" not in body
    with pytest.raises(SystemExit):  # لا إرسال مكرر لنفس الأسبوع
        newsletter.main(["send", "--week", "2026-11-08"])


def test_newsletter_encrypted_list(repo, monkeypatch):
    tmp, collect, build, ai, common = repo
    import shutil
    import newsletter
    collect.run()
    monkeypatch.setenv("BUILD_TODAY", "2026-11-14")
    assert build.main() == 0
    monkeypatch.setattr(newsletter, "SITE", common.SITE)
    monkeypatch.setattr(newsletter, "STATE", common.STATE)
    (tmp / "data").mkdir(exist_ok=True)
    shutil.copy(ROOT / "tests" / "fixtures" / "recipients.enc", tmp / "data" / "recipients.enc")  # أُنشئ بكود صفحة الإدارة (JS)
    sent = []
    monkeypatch.setattr(newsletter, "smtp_send", lambda msgs: sent.extend(msgs))
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.delenv("RECIPIENTS", raising=False)
    monkeypatch.setenv("RECIPIENTS_KEY", "test-passphrase-123")
    assert newsletter.main(["send", "--week", "2026-11-08"]) == 0
    assert sorted(m["To"] for m in sent) == ["ahmed@example.om", "boss@example.om"]  # الموقوف لا يُرسل له
    monkeypatch.setenv("RECIPIENTS_KEY", "wrong-pass")
    with pytest.raises(SystemExit):  # كلمة سر خاطئة = لا مستلمين = لا إرسال
        newsletter.main(["send", "--week", "2026-11-08", "--force"])
