"""إعادة تصنيف الأرشيف كله بالقواعد الحالية (بعد تعديل taxonomy/rules.json).

يعتمد على العنوان والمقتطف المحفوظين. لا يمس قرارات الفريق (تُطبَّق وقت البناء من decisions.csv)،
ولا الأخبار التي حسمها الذكاء الاصطناعي. ما لم يعد مرتبطًا يُحذف من الأرشيف.

python scripts/reclassify.py
"""
from collections import Counter

from common import CONFIG, classification_fields, legislation_boost, load_articles, read_json, save_articles
from taxonomy.classify import classify

omani = {s["id"]: s.get("omaniOutlet", False) for s in read_json(CONFIG / "sources.json", {"sources": []})["sources"]}
arts = load_articles()
stats = Counter()
for aid, a in list(arts.items()):
    if a.get("method") == "ai":
        stats["ai_kept"] += 1
        continue
    res = legislation_boost(classify(a["title"], a.get("excerpt", ""), omani.get(a["source"], False)), a["title"], a.get("excerpt", ""))
    if res.outcome not in ("relevant", "uncertain"):
        del arts[aid]
        stats["removed"] += 1
        continue
    a.update(classification_fields(res))
    stats[res.outcome] += 1
save_articles(arts)
print(dict(stats))
