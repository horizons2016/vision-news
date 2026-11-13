/* رصد الرؤية — واجهة ثابتة تقرأ ملفات data/*.json التي يبنيها scripts/build.py */
"use strict";

const S = { meta: null, series: null, articles: null, uncertain: null, excluded: null, reports: {} };
const AX_COLORS = { axis_1: "var(--ax1)", axis_2: "var(--ax2)", axis_3: "var(--ax3)", axis_4: "var(--ax4)" };
const STATUS = { auto: "معتمد آليًا", confirmed: "مؤكد", review: "بانتظار التأكيد", uncertain: "محتمل", rejected: "مرفوض" };
const METHOD = { rules: "القواعد", ai: "الذكاء الاصطناعي", manual: "الفريق" };
const KIND_DAYS = { daily: 2, weekly: 9, irregular: 30 };
const DRAFT_KEY = "vision-news-decisions";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n || 0).toLocaleString("en-US");
const P = (c) => S.meta.priorities.find((p) => p.code === c);
const I = (c) => S.meta.indicators.find((i) => i.code === c);
const srcName = (id) => S.meta.sources.find((s) => s.id === id)?.nameAr || id;
const dateAr = (d) => (d ? new Date(d + (d.length === 10 ? "T12:00:00" : "")).toLocaleDateString("ar-OM-u-nu-latn", { day: "numeric", month: "long", year: "numeric" }) : "");

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

/* ------------------------------------------------------------ مسودات القرارات (محلية) */
function drafts() { try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || "[]"); } catch { return []; } }
function saveDrafts(d) {
  try { localStorage.setItem(DRAFT_KEY, JSON.stringify(d)); } catch { /* التخزين غير متاح */ }
  const n = d.length, el = $("#draftCount");
  el.textContent = fmt(n); el.classList.toggle("hidden", !n);
}
function addDraft(rec) {
  const d = drafts().filter((x) => x.id !== rec.id);
  d.push({ ...rec, at: new Date().toISOString() });
  saveDrafts(d);
  toast("حُفظ القرار في المسودات — انسخه من صفحة المراجعة");
  route();
}
function draftFor(id) { return drafts().find((d) => d.id === id); }
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* ------------------------------------------------------------ رسوم SVG بسيطة */
function spark(vals, color = "var(--brand2)", w = 110, h = 26) {
  const max = Math.max(1, ...vals), step = w / Math.max(1, vals.length - 1);
  const pts = vals.map((v, i) => `${(w - i * step).toFixed(1)},${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`).join(" ");
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${color}" stroke-width="1.8" points="${pts}"/></svg>`;
}
function stackChart(weeks, layers, h = 190) {
  const W = 900, pad = 28, n = weeks.length, bw = (W - pad * 2) / n;
  const totals = weeks.map((_, i) => layers.reduce((s, l) => s + (l.vals[i] || 0), 0));
  const max = Math.max(1, ...totals);
  let bars = "";
  weeks.forEach((w, i) => {
    let y = h - 22; const x = W - pad - (i + 1) * bw + 3;  // من اليمين لليسار
    layers.forEach((l) => {
      const v = l.vals[i] || 0, bh = (v / max) * (h - 40);
      if (v) bars += `<rect x="${x.toFixed(1)}" y="${(y - bh).toFixed(1)}" width="${(bw - 6).toFixed(1)}" height="${bh.toFixed(1)}" fill="${l.color}" rx="2"><title>${esc(l.name)}: ${v}</title></rect>`;
      y -= bh;
    });
    if (i % 4 === n % 4 || i === n - 1) {
      const d = new Date(w + "T12:00:00");
      bars += `<text x="${(x + bw / 2 - 3).toFixed(1)}" y="${h - 6}" font-size="11" fill="#888" text-anchor="middle">${d.getDate()}/${d.getMonth() + 1}</text>`;
    }
    if (totals[i]) bars += `<text x="${(x + bw / 2 - 3).toFixed(1)}" y="${(h - 26 - (totals[i] / max) * (h - 40)).toFixed(1)}" font-size="10" fill="#666" text-anchor="middle">${totals[i]}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${W} ${h}" role="img" aria-label="الحراك الأسبوعي">${bars}</svg>`;
}

/* ------------------------------------------------------------ عناصر مشتركة */
function chipsP(codes) { return codes.map((c) => `<a class="chip" href="#/p/${c}" title="${esc(P(c)?.nameAr)}">${c} ${esc(P(c)?.nameAr || "")}</a>`).join(""); }
function chipsI(codes) { return codes.map((c) => `<a class="chip i" href="#/news?i=${c}" title="${esc(I(c)?.nameAr)}">${c} ${esc(trim(I(c)?.nameAr, 48))}</a>`).join(""); }
function trim(s, n) { s = s || ""; return s.length > n ? s.slice(0, n - 1) + "…" : s; }

function newsItem(a, opts = {}) {
  const d = draftFor(a.id);
  const showReasons = a.st === "review" || a.st === "uncertain";
  const reasons = showReasons ? (a.r || []).filter((r) => r !== "priority_only").map((r) => `<span class="chip r">${esc(S.meta.reasonLabels[r] || r)}</span>`).join("") : "";
  const acts = opts.actions && (a.st === "review" || a.st === "uncertain") ? `
    <div class="acts noprint">
      ${a.p.length ? `<button class="btn sm ok" data-act="confirm" data-id="${a.id}">✓ تأكيد</button>` : ""}
      <button class="btn sm" data-act="assign" data-id="${a.id}">تعديل الربط</button>
      <button class="btn sm no" data-act="reject" data-id="${a.id}">✗ غير مرتبط</button>
      ${d ? `<span class="chip t">مسودة: ${esc(d.decision)}</span>` : ""}
    </div>` : "";
  return `<li>
    <a class="h" dir="auto" href="${esc(a.u)}" target="_blank" rel="noopener">${esc(a.t)}</a>
    <div class="m">${opts.noType ? "" : typeChip(a.ty)}<span>${esc(a.pub || srcName(a.s))}</span><span>${dateAr(a.d)}</span>${a.st !== "auto" && a.st !== "confirmed" ? `<span class="st ${a.st}">${STATUS[a.st]}</span>` : ""}</div>
    ${opts.compact || opts.noP ? "" : `<div class="pchips">${chipsP(a.p)}</div>`}
    ${a.x && opts.excerpt !== false && !opts.compact && !a.x.startsWith(a.t.slice(0, 40)) ? `<div class="x" dir="auto">${esc(trim(a.x, 200))}</div>` : ""}
    ${a.ai && showReasons ? `<div class="ai">🤖 ${esc(a.ai)} <span class="muted">(ثقة ${Math.round((a.ac || 0) * 100)}%)</span></div>` : ""}
    ${reasons ? `<div>${reasons}</div>` : ""}
    ${acts}
  </li>`;
}

function bindActions(root) {
  root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
    const a = findArticle(b.dataset.id); if (!a) return;
    if (b.dataset.act === "confirm") addDraft({ id: a.id, decision: "تأكيد", p: "", i: "", title: a.t });
    else if (b.dataset.act === "reject") addDraft({ id: a.id, decision: "رفض", p: "", i: "", title: a.t });
    else assignDialog(a);
  }));
}
function findArticle(id) { return S.articles.find((a) => a.id === id) || (S.uncertain || []).find((a) => a.id === id); }

function assignDialog(a) {
  const dlg = $("#dlg");
  const opts = S.meta.priorities.map((p) => `<option value="${p.code}" ${a.p[0] === p.code ? "selected" : ""}>${p.code} — ${esc(p.nameAr)}</option>`).join("");
  dlg.innerHTML = `<h3>تعديل ربط الخبر</h3><p class="muted" style="font-size:13px">${esc(a.t)}</p>
    <label>الأولوية</label><select id="dp">${opts}</select>
    <label>المؤشرات (اختياري — فقط المؤشرات التي يمسّها الخبر مباشرة)</label><div class="checks" id="di"></div>
    <label>ملاحظة (اختياري)</label><input id="dn">
    <div class="row" style="margin-top:16px"><button class="btn p" id="ds">حفظ في المسودات</button><button class="btn" id="dc">إلغاء</button></div>`;
  const fill = () => {
    const pc = $("#dp", dlg).value;
    $("#di", dlg).innerHTML = S.meta.indicators.filter((i) => i.priority === pc).map((i) =>
      `<label><input type="checkbox" value="${i.code}" ${a.i.includes(i.code) ? "checked" : ""}> ${i.code} — ${esc(i.nameAr)}</label>`).join("") || `<span class="muted">لا مؤشرات لهذه الأولوية</span>`;
  };
  fill();
  $("#dp", dlg).onchange = fill;
  $("#dc", dlg).onclick = () => dlg.close();
  $("#ds", dlg).onclick = () => {
    const i = [...dlg.querySelectorAll("#di input:checked")].map((x) => x.value).join(" ");
    addDraft({ id: a.id, decision: "تعديل", p: $("#dp", dlg).value, i, note: $("#dn", dlg).value, title: a.t });
    dlg.close();
  };
  dlg.showModal();
}

/* ------------------------------------------------------------ الصفحات */
function weeksVals(code, kind = "priorities") { return (S.series[kind][code] || []).slice(); }
function lastN(arr, n) { return arr.slice(-n).reduce((s, v) => s + v, 0); }

async function report(id) { return S.reports[id] || (S.reports[id] = await getJSON(`data/reports/${id}.json`)); }
function typeChip(ty) { const t = S.meta.types[ty] || S.meta.types.other; return `<span class="chip ty">${t.icon} ${esc(t.label)}</span>`; }

/* الخلاصة: نقاط مع روابط مصادرها */
function digestHTML(dg, opts = {}) {
  if (!dg || !dg.bullets.length) return `<p class="muted">لا أخبار في هذه الفترة.</p>`;
  const byId = (id) => S.articles.find((a) => a.id === id);
  return `<ul class="digest">${dg.bullets.slice(0, opts.limit || 8).map((b) => {
    const refs = (b.refs || []).map(byId).filter(Boolean);
    const t = b.type ? S.meta.types[b.type] : null;
    return `<li>${t ? `<span class="dg-ic" title="${esc(t.label)}">${t.icon}</span>` : `<span class="dg-ic">•</span>`}<div><span dir="auto" class="dg-t">${esc(b.text)}</span>${refs.length ? `<span class="refs">${[...new Map(refs.map((a) => [a.pub || srcName(a.s), a])).values()].slice(0, 4).map((a) => `<a href="${esc(a.u)}" target="_blank" rel="noopener">${esc(a.pub || srcName(a.s))}</a>`).join(" · ")}</span>` : ""}</div></li>`;
  }).join("")}</ul>${opts.note !== false ? `<p class="dg-src">${dg.source === "ai" ? "صياغة تحريرية بالذكاء الاصطناعي من الأخبار المرفقة" : "مستخلصة آليًا من عناوين الأخبار، وتُصاغ تحريريًا عند تفعيل الذكاء الاصطناعي"}</p>` : ""}`;
}

const SUBST = new Set(["decree", "decision", "agreement", "international", "figures"]);
const counted = (a) => a.st === "auto" || a.st === "confirmed";
function weekRange() { const r = S.meta.digestPeriods[0]; return r ? [S.reports[r.id]?.start, S.reports[r.id]?.end] : [null, null]; }
function chg(v) { if (v == null) return `<span class="muted">—</span>`; return `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "▲" : "▼"} ${fmt(Math.abs(v))}%</span>`; }

async function viewHome() {
  const m = S.meta, A = S.analysis;
  const cur = m.digestPeriods[0], last = m.digestPeriods[1];
  const r = cur ? await report(cur.id) : null;
  const rl = last ? await report(last.id) : null;
  const wk = r ? S.articles.filter((a) => counted(a) && a.d >= r.start && a.d <= r.end) : [];
  const wkl = rl ? S.articles.filter((a) => counted(a) && a.d >= rl.start && a.d <= rl.end) : [];
  const cnt = (l, f) => l.filter(f).length;
  const legisW = cnt(wk, (a) => a.ty === "decree" || a.ty === "decision"), legisL = cnt(wkl, (a) => a.ty === "decree" || a.ty === "decision");
  const agrW = cnt(wk, (a) => a.ty === "agreement"), agrL = cnt(wkl, (a) => a.ty === "agreement");
  const topP = r ? r.priorities.slice().sort((a, b) => b.count - a.count)[0] : null;
  const diff = (a, b) => (b ? `<span class="${a >= b ? "up" : "down"}">${a >= b ? "+" : "−"}${fmt(Math.abs(a - b))}</span> عن الأسبوع الماضي` : `الأسبوع الماضي ${fmt(b)}`);
  const legis = S.articles.filter((a) => counted(a) && (a.ty === "decree" || a.ty === "decision")).slice(0, 5);
  const pCard = (c, ax) => {
    const pr = r?.priorities.find((x) => x.code === c);
    const st = A.priorities[c];
    const head = (pr?.headlines || [])[0];
    return `<a class="ptile" href="#/p/${c}" style="--ax:${AX_COLORS[ax.id]}">
      <div class="pt-top"><span class="pt-code">${c}</span><span class="pt-n">${fmt(pr?.count || 0)}<small>هذا الأسبوع</small></span></div>
      <div class="pt-name">${esc(P(c).nameAr)}</div>
      <div class="pt-meta"><span>حصة الحراك ${fmt(st.share)}%</span><span>جوهري ${fmt(Math.round(st.subRatio * 100))}%</span></div>
      <div class="pt-bar"><i style="width:${Math.min(100, st.share * 3)}%"></i></div>
      <div class="pt-head" dir="auto">${head ? esc(trim(head.title, 90)) : `<span class="muted">لا أخبار هذا الأسبوع</span>`}</div></a>`;
  };
  return `<section class="hero">
    <div><h1>حراك الرؤية هذا الأسبوع</h1><p>${esc(cur?.label || "")} · آخر تحديث ${dateAr(m.builtAt.slice(0, 10))}</p></div>
  </section>
  <div class="grid g4 kpis">
    <div class="kpi c1"><div class="l">أخبار الرؤية</div><div class="v">${fmt(wk.length)}</div><div class="d">${diff(wk.length, wkl.length)}</div></div>
    <a class="kpi c2" href="#/legislation"><div class="l">📜 مراسيم وقرارات</div><div class="v">${fmt(legisW)}</div><div class="d">${diff(legisW, legisL)}</div></a>
    <div class="kpi c3"><div class="l">🤝 اتفاقيات ومذكرات</div><div class="v">${fmt(agrW)}</div><div class="d">${diff(agrW, agrL)}</div></div>
    <a class="kpi c4" href="${topP ? `#/p/${topP.code}` : "#/"}"><div class="l">الأولوية الأنشط</div><div class="v sm">${topP && topP.count ? esc(topP.nameAr) : "—"}</div><div class="d">${topP && topP.count ? `${fmt(topP.count)} خبرًا هذا الأسبوع` : ""}</div></a>
  </div>
  <div class="grid g32" style="margin-top:18px">
    <div class="card"><div class="row"><h2>خلاصة الأسبوع</h2><span class="spacer"></span>${cur ? `<a href="#/reports?id=${cur.id}">التقرير الكامل ←</a>` : ""}</div>${digestHTML(r?.digest, { limit: 7 })}</div>
    <div class="card"><div class="row"><h2>📜 أحدث المراسيم والقرارات</h2><span class="spacer"></span><a href="#/legislation">الكل ←</a></div>
      <ul class="news slim">${legis.map((a) => newsItem(a, { compact: true })).join("") || `<li class="muted">لا يوجد بعد.</li>`}</ul></div>
  </div>
  ${m.axes.map((ax) => { const st = A.axes[ax.id]; return `<section class="axis-sec" style="--ax:${AX_COLORS[ax.id]}">
    <div class="axis-h"><h2>المحور ${ax.number}: ${esc(ax.nameAr)}</h2><span class="muted">حصته من حراك الربع ${fmt(st.share)}% · ${fmt(st.events)} حدثًا منها ${fmt(st.substantive)} جوهريًا</span></div>
    <div class="ptiles">${ax.priorities.map((c) => pCard(c, ax)).join("")}</div></section>`; }).join("")}
  <p class="note" style="margin-top:16px">«حصة الحراك» و«جوهري» محسوبتان على آخر 13 أسبوعًا — التفاصيل والمنهجية في <a href="#/analysis">تحليل الحراك</a>.</p>`;
}

/* --- صفحة الأولوية */
async function viewPriority(code) {
  const p = P(code); if (!p) return `<div class="card">أولوية غير معروفة.</div>`;
  const ax = S.meta.axes.find((a) => a.id === p.axis);
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  const per = q.get("per") || S.meta.digestPeriods[0]?.id;
  const perObj = S.meta.digestPeriods.find((x) => x.id === per) || S.meta.digestPeriods[0];
  const r = perObj ? await report(perObj.id) : null;
  const pr = r?.priorities.find((x) => x.code === code);
  const st = S.analysis.priorities[code];
  const inPer = S.articles.filter((a) => counted(a) && a.p.includes(code) && r && a.d >= r.start && a.d <= r.end);
  const pending = S.articles.filter((a) => a.st === "review" && a.p.includes(code));
  const order = ["decree", "decision", "international", "agreement", "figures", "project", "other", "event"];
  const groups = order.map((ty) => [ty, inPer.filter((a) => (a.ty || "other") === ty)]).filter(([, l]) => l.length);
  const inds = S.meta.indicators.filter((i) => i.priority === code);
  return `<div class="crumb"><a href="#/">الرئيسية</a> ← <a href="#/taxonomy">الأولويات</a> ← المحور ${ax.number}</div>
  <section class="hero" style="--ax:${AX_COLORS[ax.id]}"><div><h1>${code} — ${esc(p.nameAr)}</h1><p>محور ${esc(ax.nameAr)} · رابط هذه الصفحة ثابت ويمكن مشاركته مع مختص الأولوية</p></div></section>
  <div class="grid g4 kpis">
    <div class="kpi c1"><div class="l">أخبار الفترة</div><div class="v">${fmt(inPer.length)}</div><div class="d">الفترة السابقة ${fmt(pr?.prev || 0)}</div></div>
    <div class="kpi c2"><div class="l">حصة الحراك (13 أسبوعًا)</div><div class="v">${fmt(st.share)}%</div><div class="d">${fmt(st.events)} حدثًا</div></div>
    <div class="kpi c3"><div class="l">نسبة الجوهري</div><div class="v">${fmt(Math.round(st.subRatio * 100))}%</div><div class="d">مراسيم وقرارات واتفاقيات وأرقام</div></div>
    <div class="kpi c4"><div class="l">اتجاه آخر 4 أسابيع</div><div class="v">${chg(st.change4)}</div><div class="d">مقابل الأربعة قبلها</div></div>
  </div>
  <div class="tabs" style="margin-top:16px">${S.meta.digestPeriods.map((d) => `<button class="${d.id === perObj?.id ? "on" : ""}" onclick="location.hash='#/p/${code}?per=${d.id}'">${esc(d.name)}</button>`).join("")}</div>
  <div class="grid g32">
    <div class="card"><h2>الخلاصة — ${esc(perObj?.label || "")}</h2>${digestHTML(pr?.digest)}</div>
    <div class="card"><h2>المؤشرات والحراك حولها</h2><p class="muted" style="font-size:12.5px;margin-top:-6px">آخر 13 أسبوعًا: الأحداث (منها الجوهرية)</p>
      <table class="mini">${inds.map((i) => { const s = S.analysis.indicators[i.code]; return `<tr class="ind-row" data-go="#/news?i=${i.code}"><td>${i.code}</td><td>${esc(i.nameAr)}</td><td class="n">${fmt(s.events)}${s.substantive ? ` <b class="up">(${fmt(s.substantive)})</b>` : ""}</td></tr>`; }).join("")}</table></div>
  </div>
  ${pending.length ? `<div class="note" style="margin-top:12px">⏳ ${fmt(pending.length)} خبرًا لهذه الأولوية بانتظار التأكيد — <a href="#/news?st=review&p=${code}">راجعها</a></div>` : ""}
  ${groups.map(([ty, list]) => `<div class="card" style="margin-top:14px"><h3>${S.meta.types[ty].icon} ${esc(ty === "other" ? "أخبار أخرى" : S.meta.types[ty].label)} <span class="muted">(${fmt(list.length)})</span></h3>
     <ul class="news">${list.map((a) => newsItem(a, { actions: true, noType: true, noP: a.p.length === 1 })).join("")}</ul></div>`).join("")}`;
}

/* --- المراسيم والقرارات */
function viewLegislation(q) {
  const ty = q.get("ty") || "";
  const list = S.articles.filter((a) => (counted(a) || a.st === "review") && (ty ? a.ty === ty : a.ty === "decree" || a.ty === "decision"));
  const n = +(q.get("n") || 60);
  return `<section class="hero"><div><h1>📜 المراسيم والقرارات</h1><p>المراسيم السلطانية والقرارات واللوائح ذات الصلة بالرؤية، من المصادر الرسمية والصحف ومنها قانون عُمان</p></div></section>
  <div class="tabs"><button class="${!ty ? "on" : ""}" onclick="location.hash='#/legislation'">الكل</button><button class="${ty === "decree" ? "on" : ""}" onclick="location.hash='#/legislation?ty=decree'">مراسيم سلطانية</button><button class="${ty === "decision" ? "on" : ""}" onclick="location.hash='#/legislation?ty=decision'">قرارات ولوائح</button></div>
  <div class="card"><ul class="news">${list.slice(0, n).map((a) => newsItem(a, { actions: true })).join("") || `<li class="muted">لا يوجد بعد — تمتلئ بعد تشغيل الجمع من قانون عُمان والمصادر الرسمية.</li>`}</ul>
  ${list.length > n ? `<div class="row" style="justify-content:center"><a class="btn" href="#/legislation?${ty ? `ty=${ty}&` : ""}n=${n + 100}">عرض المزيد</a></div>` : ""}</div>`;
}

/* --- الأولويات: الهيكل */
function viewTaxonomy() {
  const m = S.meta, A = S.analysis;
  return `<section class="hero"><div><h1>المحاور والأولويات والمؤشرات</h1><p>4 محاور ← 12 أولوية ← 38 مؤشرًا (القائمة المحدثة). الأرقام: أحداث آخر 13 أسبوعًا، وبين قوسين الجوهرية منها.</p></div></section>
  ${m.axes.map((ax) => `<section class="axis-sec" style="--ax:${AX_COLORS[ax.id]}"><div class="axis-h"><h2>المحور ${ax.number}: ${esc(ax.nameAr)}</h2></div>
    <div class="grid g2">${ax.priorities.map((c) => { const st = A.priorities[c]; return `<div class="card pcard">
      <a class="pc-h" href="#/p/${c}"><span class="pt-code">${c}</span> ${esc(P(c).nameAr)}<span class="spacer"></span><b>${fmt(st.events)}</b> <span class="muted">(${fmt(st.substantive)})</span></a>
      <table class="mini">${m.indicators.filter((i) => i.priority === c).map((i) => { const s = A.indicators[i.code]; return `<tr class="ind-row" data-go="#/news?i=${i.code}"><td>${i.code}</td><td>${esc(i.nameAr)}</td><td class="n">${fmt(s.events)}${s.substantive ? ` <span class="up">(${fmt(s.substantive)})</span>` : ""}</td></tr>`; }).join("")}</table></div>`; }).join("")}</div></section>`).join("")}`;
}

/* --- تحليل الحراك */
function heat(weeks, rows) {
  const max = Math.max(1, ...rows.flatMap((r) => r.vals));
  return `<div class="heat"><table><thead><tr><th></th>${weeks.map((w) => { const d = new Date(w + "T12:00:00"); return `<th>${d.getDate()}/${d.getMonth() + 1}</th>`; }).join("")}</tr></thead><tbody>
  ${rows.map((r) => `<tr><td class="hl-name"><a href="#/p/${r.code}">${esc(trim(r.name, 30))}</a></td>${r.vals.map((v, i) => `<td title="${esc(r.name)} — أسبوع ${weeks[i]}: وزن ${v}" style="background:${v ? `color-mix(in srgb, ${r.color} ${Math.round(12 + 88 * (v / max))}%, white)` : "#f6f5f9"}">${v ? Math.round(v) : ""}</td>`).join("")}</tr>`).join("")}
  </tbody></table></div>`;
}
function viewAnalysis() {
  const m = S.meta, A = S.analysis, W = A.window;
  const typesOrder = ["decree", "decision", "international", "agreement", "figures", "project", "other", "event"];
  const typeColor = { decree: "#5b2a86", decision: "#7b4fb0", international: "#1f6fb2", agreement: "#0f8a8a", figures: "#2fa37a", project: "#9ab83a", other: "#c9c6d6", event: "#e6e3ee" };
  const prs = Object.entries(A.priorities).sort((a, b) => b[1].weight - a[1].weight);
  const maxW = Math.max(1, ...prs.map(([, s]) => s.weight));
  const stack = (s) => { const tot = Object.values(s.types).reduce((x, y) => x + y, 0) || 1; return typesOrder.filter((t) => s.types[t]).map((t) => `<i title="${esc(A.typeLabels[t])}: ${s.types[t]}" style="width:${(100 * s.types[t]) / tot}%;background:${typeColor[t]}"></i>`).join(""); };
  const gaps = A.gaps.map((c) => I(c));
  const silent = gaps.filter((i) => A.indicators[i.code].events === 0);
  const noAction = gaps.filter((i) => A.indicators[i.code].events > 0);
  const inds = Object.entries(A.indicators).filter(([, s]) => s.events).sort((a, b) => b[1].weight - a[1].weight).slice(0, 12);
  return `<section class="hero"><div><h1>تحليل الحراك</h1><p>أين يتركز الحراك الإخباري للرؤية، وما نوعيته، وكيف يتغير — آخر 13 أسبوعًا (${dateAr(W.start)} – ${dateAr(W.end)})</p></div></section>
  <div class="grid g4 kpis">
    <div class="kpi c1"><div class="l">أحداث الربع</div><div class="v">${fmt(A.totals.events)}</div><div class="d">من ${fmt(A.totals.articles)} خبرًا بعد دمج التغطيات المكررة</div></div>
    <div class="kpi c2"><div class="l">أحداث جوهرية</div><div class="v">${fmt(A.totals.substantive)}</div><div class="d">${fmt(Math.round((100 * A.totals.substantive) / Math.max(1, A.totals.events)))}% من الحراك</div></div>
    <div class="kpi c3"><div class="l">مراسيم وقرارات</div><div class="v">${fmt((A.totals.types.decree || 0) + (A.totals.types.decision || 0))}</div><div class="d">اتفاقيات ${fmt(A.totals.types.agreement || 0)}</div></div>
    <div class="kpi c4"><div class="l">مؤشرات بلا إجراء جوهري</div><div class="v">${fmt(A.gaps.length)} <small>من 38</small></div><div class="d"><a href="#gaps">عرض الفجوات</a></div></div>
  </div>
  <div class="grid g4" style="margin-top:16px">${m.axes.map((ax) => { const s = A.axes[ax.id]; return `<div class="card axcard" style="--ax:${AX_COLORS[ax.id]}"><div class="l">${esc(ax.nameAr)}</div><div class="v">${fmt(s.share)}%</div><div class="d">${fmt(s.events)} حدثًا · جوهري ${fmt(Math.round(s.subRatio * 100))}% · ${chg(s.change4)}</div></div>`; }).join("")}</div>

  <div class="card" style="margin-top:16px"><h2>الأولويات: حجم الحراك ونوعيته</h2>
    <p class="muted" style="font-size:13px">طول الشريط = وزن الحراك؛ ألوانه = توزيع الأحداث حسب النوع. «جوهري» = مراسيم وقرارات واتفاقيات وتقييمات دولية وأرقام. الاتجاه = آخر 4 أسابيع مكتملة مقابل الأربعة قبلها.</p>
    <div class="legend" style="margin-bottom:10px">${typesOrder.map((t) => `<span><i style="background:${typeColor[t]}"></i>${esc(A.typeLabels[t])}</span>`).join("")}</div>
    <table class="prio"><thead><tr><th>الأولوية</th><th style="width:40%">الحراك ونوعيته</th><th class="n">الحصة</th><th class="n">الأحداث</th><th class="n">جوهري</th><th class="n">الاتجاه</th></tr></thead><tbody>
    ${prs.map(([c, s]) => `<tr class="ind-row" data-go="#/p/${c}"><td><span class="pt-code" style="--ax:${AX_COLORS[A.axisOf[c]]}">${c}</span> ${esc(P(c).nameAr)}</td>
      <td><div class="stk" style="width:${Math.max(4, (100 * s.weight) / maxW)}%">${stack(s)}</div></td><td class="n">${fmt(s.share)}%</td><td class="n">${fmt(s.events)}</td><td class="n">${fmt(Math.round(s.subRatio * 100))}%</td><td class="n">${chg(s.change4)}</td></tr>`).join("")}
    </tbody></table></div>

  <div class="card" style="margin-top:16px"><h2>خريطة الحراك الأسبوعية</h2><p class="muted" style="font-size:13px">وزن حراك كل أولوية في كل أسبوع؛ اللون الأغمق = حراك أكبر. يكشف متى تحركت كل أولوية ومتى صمتت.</p>
    ${heat(W.weeks, m.axes.flatMap((ax) => ax.priorities.map((c) => ({ code: c, name: P(c).nameAr, color: AX_COLORS[ax.id].replace("var(", "var(").replace(")", ")"), vals: A.priorities[c].series }))))}</div>

  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h2>المؤشرات الأكثر حراكًا</h2><table class="mini">${inds.map(([c, s]) => `<tr class="ind-row" data-go="#/news?i=${c}"><td>${c}</td><td>${esc(I(c).nameAr)}<div class="muted" style="font-size:12px" dir="auto">${s.top[0] ? esc(trim(s.top[0].t, 80)) : ""}</div></td><td class="n">${fmt(s.events)}${s.substantive ? ` <b class="up">(${fmt(s.substantive)})</b>` : ""}</td></tr>`).join("")}</table></div>
    <div class="card"><h2>أولويات تتحرك معًا</h2><p class="muted" style="font-size:13px">أحداث خدمت أولويتين في الوقت نفسه — تكشف الترابط الفعلي بين الأولويات.</p>
      <table class="mini">${A.cross.slice(0, 10).map((x) => `<tr><td>${esc(P(x.a).nameAr)}</td><td class="muted">↔</td><td>${esc(P(x.b).nameAr)}</td><td class="n">${fmt(x.events)}</td></tr>`).join("") || `<tr><td class="muted">لا يوجد</td></tr>`}</table></div>
  </div>

  <div class="card" style="margin-top:16px" id="gaps"><h2>الفجوات: مؤشرات بلا إجراء جوهري خلال 13 أسبوعًا</h2>
    <p class="muted" style="font-size:13px">لا مرسوم ولا قرار ولا اتفاقية ولا تقييم دولي ولا أرقام مرتبطة بها في الأخبار. الفجوة الإخبارية لا تعني غياب العمل، لكنها سؤال يستحق المتابعة.</p>
    <h3>بلا أي خبر (${fmt(silent.length)})</h3><div>${silent.map((i) => `<span class="chip i">${i.code} ${esc(trim(i.nameAr, 70))}</span>`).join("")}</div>
    <h3 style="margin-top:12px">أخبار عامة أو فعاليات فقط (${fmt(noAction.length)})</h3><div>${noAction.map((i) => `<a class="chip" href="#/news?i=${i.code}">${i.code} ${esc(trim(i.nameAr, 70))} (${fmt(A.indicators[i.code].events)})</a>`).join("")}</div></div>

  <div class="card" style="margin-top:16px"><h2>المنهجية</h2><ol class="method">
    <li><b>الحدث لا الخبر:</b> تغطيات الحدث نفسه (عناوين متشابهة خلال 7 أيام) تُدمج في حدث واحد.</li>
    <li><b>وزن النوعية:</b> ${typesOrder.map((t) => `${esc(A.typeLabels[t])} ${A.weights[t]}`).join("، ")}؛ ويزيد الوزن 25% لكل مصدر إضافي غطّى الحدث (حتى 75%).</li>
    <li><b>الحصة:</b> وزن حراك الأولوية ÷ مجموع أوزان الحراك. الحدث الذي يخدم أولويتين يُحسب لكلتيهما.</li>
    <li><b>الاتجاه:</b> آخر 4 أسابيع مكتملة مقابل الأربعة قبلها${W.prevComplete ? "" : " (مقارنة الربع بالربع السابق تُتاح بعد اكتمال 6 أشهر من الرصد)"}.</li>
    <li><b>الحدود:</b> الأرقام تقيس ما نُشر لا كل ما يحدث، والتصنيف آلي قد يخطئ. هي دليل <b>ارتباط</b> وتوقيت، لا قياس <b>أثر</b> على قيمة المؤشر.</li></ol></div>`;
}

/* --- الأخبار */
async function viewNews(q) {
  const st = q.get("st") || "counted";
  let list = S.articles;
  if (st === "uncertain") list = await loadUncertain();
  const f = { q: q.get("q") || "", ax: q.get("ax") || "", p: q.get("p") || "", i: q.get("i") || "", s: q.get("s") || "", days: q.get("days") || "", st };
  const axP = f.ax ? new Set(S.meta.axes.find((a) => a.id === f.ax)?.priorities) : null;
  const since = f.days ? new Date(Date.now() - f.days * 864e5).toISOString().slice(0, 10) : "";
  const needle = f.q.trim().toLowerCase();
  const res = list.filter((a) =>
    (st === "counted" ? a.st === "auto" || a.st === "confirmed" : st === "all" || a.st === st) &&
    (!axP || a.p.some((c) => axP.has(c))) && (!f.p || a.p.includes(f.p)) && (!f.i || a.i.includes(f.i)) &&
    (!f.s || a.s === f.s) && (!since || a.d >= since) &&
    (!needle || (a.t + " " + (a.x || "") + " " + (a.k || []).join(" ")).toLowerCase().includes(needle)));
  const page = +(q.get("n") || 60);
  const opt = (v, label, cur) => `<option value="${v}" ${v === cur ? "selected" : ""}>${esc(label)}</option>`;
  const inds = S.meta.indicators.filter((i) => !f.p || i.priority === f.p);
  const html = `<h1>الأخبار</h1><p class="sub">${fmt(res.length)} خبرًا مطابقًا${f.i ? ` — المؤشر: ${esc(I(f.i)?.nameAr)}` : ""}${f.p && !f.i ? ` — الأولوية: ${esc(P(f.p)?.nameAr)}` : ""}</p>
  <div class="filters card flat">
    <input id="fq" placeholder="بحث في العناوين والمقتطفات…" value="${esc(f.q)}">
    <select id="fst">${opt("counted", "المحتسبة", st)}${opt("review", "بانتظار التأكيد", st)}${opt("uncertain", "المحتملة", st)}${opt("all", "الكل", st)}</select>
    <select id="fax">${opt("", "كل المحاور", f.ax)}${S.meta.axes.map((a) => opt(a.id, a.nameAr, f.ax)).join("")}</select>
    <select id="fp">${opt("", "كل الأولويات", f.p)}${S.meta.priorities.map((p) => opt(p.code, `${p.code} ${p.nameAr}`, f.p)).join("")}</select>
    <select id="fi">${opt("", "كل المؤشرات", f.i)}${inds.map((i) => opt(i.code, `${i.code} ${trim(i.nameAr, 60)}`, f.i)).join("")}</select>
    <select id="fs">${opt("", "كل المصادر", f.s)}${S.meta.sources.map((s) => opt(s.id, s.nameAr, f.s)).join("")}</select>
  </div>
  <div class="row noprint" style="margin:-4px 0 12px"><span class="muted">الفترة:</span>${[["", "الكل"], ["7", "7 أيام"], ["30", "30 يومًا"], ["90", "90 يومًا"]].map(([v, l]) => `<button class="btn sm ${f.days === v ? "p" : ""}" data-days="${v}">${l}</button>`).join("")}
    <span class="spacer"></span><button class="btn sm" id="csv">تنزيل CSV</button></div>
  <div class="card"><ul class="news">${res.slice(0, page).map((a) => newsItem(a, { actions: true })).join("") || `<li class="muted">لا توجد نتائج.</li>`}</ul>
  ${res.length > page ? `<div class="row" style="justify-content:center;margin-top:12px"><button class="btn" id="more">عرض المزيد (${fmt(res.length - page)})</button></div>` : ""}</div>`;
  setTimeout(() => {
    const set = (k, v) => { const p = new URLSearchParams(q); v ? p.set(k, v) : p.delete(k); if (k === "p") p.delete("i"); p.delete("n"); location.hash = "#/news?" + p.toString(); };
    $("#fq").addEventListener("change", (e) => set("q", e.target.value));
    $("#fst").onchange = (e) => set("st", e.target.value === "counted" ? "" : e.target.value);
    $("#fax").onchange = (e) => set("ax", e.target.value);
    $("#fp").onchange = (e) => set("p", e.target.value);
    $("#fi").onchange = (e) => set("i", e.target.value);
    $("#fs").onchange = (e) => set("s", e.target.value);
    document.querySelectorAll("[data-days]").forEach((b) => (b.onclick = () => set("days", b.dataset.days)));
    $("#more")?.addEventListener("click", () => { const p = new URLSearchParams(q); p.set("n", page + 100); location.hash = "#/news?" + p.toString(); });
    $("#csv").onclick = () => downloadCSV(res);
  });
  return html;
}
function downloadCSV(rows) {
  const head = ["التاريخ", "العنوان", "المصدر", "الحالة", "الأولويات", "المؤشرات", "الرابط", "المعرف"];
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [head.join(",")].concat(rows.map((a) => [a.d, a.t, a.pub || srcName(a.s), STATUS[a.st], a.p.join(" "), a.i.join(" "), a.u, a.id].map(q).join(",")));
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "اخبار-الرؤية.csv"; link.click();
}

/* --- التقارير */
async function viewReports(q) {
  const id = q.get("id");
  if (id) return viewReport(id);
  const reps = S.meta.reports;
  const list = (t) => reps.filter((r) => r.type === t).slice().reverse().map((r) => `<a href="#/reports?id=${r.id}"><span>${esc(r.label)}${r.partial ? ' <span class="chip t">جارٍ</span>' : ""}</span><b>${fmt(r.total)} خبر</b></a>`).join("");
  return `<h1>التقارير</h1><p class="sub">تُبنى تلقائيًا بعد كل تحديث. الأسبوع يبدأ الأحد. يمكن طباعة أي تقرير أو حفظه PDF من زر الطباعة.</p>
  <div class="grid g2"><div class="card rep-list"><h2>التقارير الأسبوعية</h2>${list("week")}</div><div class="card rep-list"><h2>التقارير الشهرية</h2>${list("month")}</div></div>`;
}
async function viewReport(id) {
  const r = S.reports[id] || (S.reports[id] = await getJSON(`data/reports/${id}.json`));
  const kind = r.type === "week" ? "الأسبوعي" : "الشهري";
  const ch = (a, b) => (b ? `<span class="${a >= b ? "up" : "down"}">${a >= b ? "+" : ""}${fmt(a - b)}</span>` : "");
  const pr = r.priorities.slice().sort((a, b) => b.count - a.count);
  setTimeout(() => ($("#print").onclick = () => window.print()));
  return `<div class="row noprint"><a href="#/reports">→ كل التقارير</a><span class="spacer"></span><button class="btn p" id="print">طباعة / PDF</button></div>
  <div class="card rep" style="margin-top:10px">
    <h1>حراك أخبار رؤية عُمان 2040 — التقرير ${kind}</h1><p class="sub">${esc(r.label)}${r.partial ? " — حتى الآن" : ""}</p>
    <div class="grid g3"><div class="kpi"><div class="l">أخبار مرتبطة بالرؤية</div><div class="v">${fmt(r.total)}</div><div class="d">السابقة ${fmt(r.prevTotal)} ${ch(r.total, r.prevTotal)}</div></div>
      <div class="kpi"><div class="l">بانتظار تأكيد الفريق</div><div class="v">${fmt(r.awaiting)}</div></div>
      <div class="kpi"><div class="l">أولويات بلا أخبار</div><div class="v">${fmt(r.silentPriorities.length)}</div></div></div>
    <h2>الخلاصة</h2>${digestHTML(r.digest)}
    ${r.highlights.length ? `<h2>أرقام الحراك</h2><ul class="hl">${r.highlights.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}
    <h2>حسب المحاور</h2><table><tr><th>المحور</th><th class="n">الأخبار</th><th class="n">السابقة</th><th class="n">التغير</th></tr>
      ${r.axes.map((a) => `<tr><td>${esc(a.nameAr)}</td><td class="n">${fmt(a.count)}</td><td class="n">${fmt(a.prev)}</td><td class="n">${ch(a.count, a.prev)}</td></tr>`).join("")}</table>
    <h2>حسب الأولويات</h2>
    ${pr.filter((p) => p.count).map((p) => `<div style="margin:14px 0 18px"><h3><a href="#/p/${p.code}?per=${r.id}">${p.code} — ${esc(p.nameAr)}</a> <span class="muted" style="font-weight:500">(${fmt(p.count)}، السابقة ${fmt(p.prev)})</span></h3>
      ${digestHTML(p.digest, { limit: 4, note: false })}
      ${p.indicators.length ? `<div>${p.indicators.map((i) => `<span class="chip i">${i.code} ${esc(trim(i.nameAr, 55))} (${fmt(i.count)})</span>`).join("")}</div>` : `<div class="muted" style="font-size:13px">ارتباط على مستوى الأولوية دون مؤشر محدد.</div>`}
      <details><summary class="muted" style="font-size:13px;cursor:pointer">المصادر (${fmt(p.headlines.length)})</summary><ul>${p.headlines.map((h) => `<li><a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a> <span class="muted" style="font-size:12px">— ${esc(srcName(h.source))}، ${dateAr(h.date)}</span></li>`).join("")}</ul></details></div>`).join("")}
    ${r.silentPriorities.length ? `<h2>أولويات بلا أخبار</h2><p>${r.silentPriorities.map((c) => esc(P(c).nameAr)).join("، ")}</p>` : ""}
    <h2>المصادر</h2><p>${r.sources.map((s) => `${esc(s.nameAr)} (${fmt(s.count)})`).join("، ") || "—"}</p>
    <p class="note">رصد إخباري لما نُشر عن أولويات رؤية عُمان 2040، مصنَّف وفق قواعد موثقة (الإصدار ${esc(S.meta.rulesVersion)}). الخلاصة مستخلصة من الأخبار المرفقة روابطها.</p>
  </div>`;
}

/* --- المراجعة */
async function viewReview(q) {
  const tab = q.get("tab") || "review";
  const tabs = [["review", `بانتظار التأكيد (${fmt(S.meta.totals.review)})`], ["uncertain", `محتملة (${fmt(S.meta.totals.uncertain)})`], ["excluded", "المستبعدة مؤخرًا"], ["drafts", `قراراتي (${fmt(drafts().length)})`]];
  let body = "";
  if (tab === "review" || tab === "uncertain") {
    const list = tab === "review" ? S.articles.filter((a) => a.st === "review") : await loadUncertain();
    const n = +(q.get("n") || 50);
    body = `<p class="note">${tab === "review" ? "أخبار ربطتها القواعد بأولوية لكن فيها ما يستدعي نظرة بشرية (السبب ظاهر تحت كل خبر). لا تُحتسب في التقارير حتى تُؤكَّد." : "أخبار عُمانية فيها إشارة لموضوع من مواضيع الرؤية لكن دون حد الإثبات. إن فُعّل الذكاء الاصطناعي يحسم أغلبها تلقائيًا؛ وإلا يمكن تأكيد المهم منها هنا."}</p>
      <div class="card" style="margin-top:12px"><ul class="news">${list.slice(0, n).map((a) => newsItem(a, { actions: true })).join("") || `<li class="muted">لا يوجد.</li>`}</ul>
      ${list.length > n ? `<div class="row" style="justify-content:center"><a class="btn" href="#/review?tab=${tab}&n=${n + 100}">عرض المزيد</a></div>` : ""}</div>`;
  } else if (tab === "excluded") {
    const ex = S.excluded || (S.excluded = await getJSON("data/excluded.json"));
    const why = { no_match: "لا علاقة بالأولويات", no_oman_context: "لا يخص عُمان", excluded_general: "خبر عام", ai_not_relevant: "الذكاء الاصطناعي: غير مرتبط", duplicate: "مكرر" };
    body = `<p class="note">آخر ما استُبعد خلال 14 يومًا، لفحص جودة القواعد. إن وجدت خبرًا مهمًا استُبعد خطأً فأبلغ مسؤول القواعد بالعنوان لإضافة المصطلح الناقص.</p>
      <div class="card" style="margin-top:12px"><table><tr><th>العنوان</th><th>المصدر</th><th>السبب</th></tr>
      ${ex.slice(0, 300).map((x) => `<tr><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a></td><td>${esc(srcName(x.source))}</td><td class="muted">${esc(why[x.why] || x.why)}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">لا يوجد بعد — يمتلئ بعد أول تشغيل للجمع.</td></tr>`}</table></div>`;
  } else {
    const d = drafts();
    const csv = d.map((x) => [x.id, x.decision, x.p || "", x.i || "", "", (x.note || "").replace(/[,\n]/g, " ")].join(",")).join("\n");
    body = `<div class="card"><h2>القرارات المحفوظة على هذا الجهاز</h2>
      <p>لتثبيت القرارات: انسخ الأسطر، ثم افتح الملف <b>data/decisions.csv</b> في GitHub ← أيقونة القلم ✏️ ← الصق في آخر الملف ← Commit changes. بعد دقائق يُعاد البناء وتظهر القرارات في التقارير.</p>
      <p class="muted" style="font-size:13px">اكتب اسمك في العمود الخامس (بواسطة) إن رغبت.</p>
      <textarea class="code" id="csvout" readonly>${esc(csv)}</textarea>
      <div class="row" style="margin-top:10px"><button class="btn p" id="copy" ${d.length ? "" : "disabled"}>نسخ الأسطر</button><button class="btn no" id="clear" ${d.length ? "" : "disabled"}>مسح المسودات</button></div>
      <table style="margin-top:14px">${d.map((x) => `<tr><td>${esc(x.decision)}</td><td>${esc(x.title)}</td><td>${esc(x.p)} ${esc(x.i)}</td><td><button class="btn sm" data-del="${x.id}">حذف</button></td></tr>`).join("")}</table></div>`;
    setTimeout(() => {
      $("#copy")?.addEventListener("click", async () => { try { await navigator.clipboard.writeText($("#csvout").value); toast("نُسخت الأسطر"); } catch { $("#csvout").select(); document.execCommand("copy"); toast("نُسخت الأسطر"); } });
      $("#clear")?.addEventListener("click", () => { if (confirm("مسح كل المسودات؟ تأكد أنك لصقتها في decisions.csv أولًا.")) { saveDrafts([]); route(); } });
      document.querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { saveDrafts(drafts().filter((x) => x.id !== b.dataset.del)); route(); }));
    });
  }
  return `<h1>المراجعة</h1><p class="sub">قرارات الفريق تُحفظ مسودةً على جهازك، ثم تُثبَّت في GitHub ليراها الجميع.</p>
    <div class="tabs">${tabs.map(([k, l]) => `<button class="${k === tab ? "on" : ""}" onclick="location.hash='#/review?tab=${k}'">${l}</button>`).join("")}</div>${body}`;
}

/* --- المصادر */
function viewSources() {
  const m = S.meta, today = new Date(m.today + "T12:00:00");
  const rows = m.sources.map((s) => {
    let dot = "ok-dot", state = "يعمل";
    if (!s.active) { dot = "warn-dot"; state = "موقوف"; }
    else if (!s.lastRunAt) { dot = "warn-dot"; state = "لم يُجرَّب بعد"; }
    else if (s.consecutiveFailures) { dot = "bad-dot"; state = `فشل ${fmt(s.consecutiveFailures)} مرة متتالية`; }
    else if (s.lastArticle && (today - new Date(s.lastArticle + "T12:00:00")) / 864e5 > (KIND_DAYS[s.publishes] || 3) * 3) { dot = "warn-dot"; state = "يعمل لكن بلا أخبار مرتبطة مؤخرًا"; }
    return `<tr><td><span class="${dot}"></span><b>${esc(s.nameAr)}</b><div class="muted" style="font-size:12px">${esc(s.kind || "")}</div></td>
      <td>${state}${s.method ? `<div class="muted" style="font-size:12px">${s.method === "rss" ? "RSS" : "قراءة الصفحة"}</div>` : ""}${(s.consecutiveFailures && s.errors?.length) ? `<div class="err">${esc(s.errors.slice(0, 2).join(" | "))}</div>` : ""}</td>
      <td class="n">${fmt(s.articles)}</td><td>${s.lastArticle ? dateAr(s.lastArticle) : "—"}</td><td class="n">${s.found != null ? `${fmt(s.found)} / ${fmt(s.new)} / ${fmt(s.kept)}` : "—"}</td></tr>`;
  }).join("");
  const lr = m.lastRun;
  return `<h1>المصادر</h1><p class="sub">${lr ? `آخر تشغيل للجمع: ${new Date(lr.at).toLocaleString("ar-OM-u-nu-latn")} — جديد ${fmt(lr.new)}، مرتبط بالرؤية ${fmt(lr.kept)}، مستبعد ${fmt(lr.excluded)}` : "لم يعمل الجمع التلقائي بعد على GitHub."}</p>
  <div class="card"><table><thead><tr><th>المصدر</th><th>الحالة</th><th class="n">أخبار محتسبة</th><th>آخر خبر مرتبط</th><th class="n">آخر تشغيل: موجود / جديد / مرتبط</th></tr></thead><tbody>${rows}</tbody></table></div>
  <p class="note" style="margin-top:12px">إضافة مصدر أو إيقافه من الملف <b>config/sources.json</b>. لكل مصدر روابط RSS تُجرَّب بالترتيب، ثم قراءة صفحة الأخبار إن فشلت.</p>`;
}

function viewAbout() {
  const m = S.meta;
  return `<div class="card" style="max-width:860px"><h1>عن الرصد</h1>
  <p>رصد إخباري لحراك رؤية عُمان 2040: يجمع الأخبار والمراسيم والقرارات، ويُبقي فقط ما يرتبط بأولويات الرؤية، ويوزعه على الأولويات حتى يعرف مختص كل أولوية ما حدث فيها. البيانات الإحصائية للمؤشرات مكانها داشبورد «مؤشرات الرؤية»، وليست هنا.</p>
  <h2 style="margin-top:16px">المصادر</h2><p>الصحف العُمانية ووكالة الأنباء، وقانون عُمان للمراسيم والقرارات، وما تنشره المصادر العالمية عن عُمان. يُجمع كل 3 ساعات.</p>
  <h2>التصنيف</h2><ol>
    <li><b>السياق العُماني:</b> ذكر عُمان أو محافظاتها أو مؤسساتها، أو أن الخبر من صحيفة عمانية ولا يتحدث عن بلد آخر.</li>
    <li><b>الأولوية:</b> مصطلحات لكل أولوية؛ للعنوان وزن مضاعف. المراسيم والقرارات تُحفظ دائمًا وتُربط بأولوية التشريع والقضاء والرقابة، إضافة لأي أولوية يمسّها موضوعها.</li>
    <li><b>المؤشر:</b> وسم إضافي حين يتناول الخبر موضوع المؤشر مباشرة.</li>
    <li><b>نوع الخبر:</b> مرسوم، قرار، تقييم دولي، اتفاقية، أرقام، مشروع، فعالية.</li>
    <li><b>الاستبعاد:</b> الرياضة والطقس والحوادث والتعازي والأخبار الخارجية.</li>
    <li><b>بانتظار التأكيد:</b> حالات ملتبسة لا تُحتسب حتى يؤكدها الفريق.</li></ol>
  <h2>تحليل الحراك</h2><p>لكل محور وأولوية ومؤشر: عدد الأحداث (بعد دمج التغطيات المكررة)، ووزنها حسب النوع، ونسبة الجوهري منها، واتجاهها. التفاصيل في صفحة <a href="#/analysis">تحليل الحراك</a>.</p>
  <h2>الخلاصة</h2><p>لكل أولوية ولكل فترة: أهم ما حدث في نقاط. بدون ذكاء اصطناعي تُستخلص بتجميع تغطيات الحدث الواحد وترتيبها حسب النوع وعدد المصادر. ومع تفعيله تُصاغ تحريريًا («وقّعت… صدر… ارتفع…») من الأخبار نفسها، مع روابطها.</p>
  <h2>ما يُحفظ</h2><p>العنوان ومقتطف قصير ورابط المصدر والتصنيف. لا يُعاد نشر نص الخبر.</p>
  <p class="muted">إصدار القواعد: ${esc(m.rulesVersion)} · آخر بناء: ${new Date(m.builtAt).toLocaleString("ar-OM-u-nu-latn")}</p></div>`;
}

/* ------------------------------------------------------------ التوجيه */
async function loadUncertain() { return S.uncertain || (S.uncertain = await getJSON("data/uncertain.json")); }

const VIEWS = { admin: viewAdmin, home: viewHome, news: viewNews, taxonomy: viewTaxonomy, analysis: viewAnalysis, legislation: viewLegislation, reports: viewReports, review: viewReview, sources: viewSources, about: viewAbout };
async function route() {
  const [path, qs] = (location.hash.slice(2) || "").split("?");
  const isP = /^p\/P\d\d$/.test(path || "");
  const name = isP ? "taxonomy" : VIEWS[path] ? path : "home";
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === name));
  const app = $("#app");
  try {
    app.innerHTML = isP ? await viewPriority(path.slice(2)) : await VIEWS[name](new URLSearchParams(qs || ""));
  } catch (e) {
    app.innerHTML = `<div class="card"><h2>تعذر عرض الصفحة</h2><p class="muted">${esc(e.message)}</p></div>`;
  }
  app.querySelectorAll("[data-go]").forEach((el) => el.addEventListener("click", () => (location.hash = el.dataset.go)));
  bindActions(app);
}

async function boot() {
  try {
    [S.meta, S.series, S.articles, S.analysis] = await Promise.all([getJSON("data/meta.json"), getJSON("data/series.json"), getJSON("data/articles.json"), getJSON("data/analysis.json")]);
  } catch (e) {
    $("#app").innerHTML = `<div class="card"><h2>لم تُبنَ البيانات بعد</h2><p>شغّل <code>python scripts/build.py</code> أو انتظر أول تشغيل في GitHub Actions.</p><p class="muted">${esc(e.message)}</p></div>`;
    return;
  }
  document.title = `${S.meta.siteTitle} — حراك أخبار رؤية عُمان 2040`;
  $("#foot").innerHTML = `آخر تحديث للبيانات: ${new Date(S.meta.builtAt).toLocaleString("ar-OM-u-nu-latn")} · ${fmt(S.meta.totals.counted)} خبرًا محتسبًا · قواعد ${esc(S.meta.rulesVersion)}`;
  saveDrafts(drafts());
  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
  route();
}
boot();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
