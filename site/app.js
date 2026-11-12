/* رصد الرؤية — واجهة ثابتة تقرأ ملفات data/*.json التي يبنيها scripts/build.py */
"use strict";

const S = { meta: null, series: null, articles: null, uncertain: null, excluded: null, reports: {} };
const AX_COLORS = { axis_1: "var(--ax1)", axis_2: "var(--ax2)", axis_3: "var(--ax3)", axis_4: "var(--ax4)" };
const STATUS = { auto: "معتمد آليًا", confirmed: "مؤكد", review: "بانتظار التأكيد", uncertain: "محتمل", rejected: "مرفوض" };
const METHOD = { rules: "القواعد", ai: "الذكاء الاصطناعي", manual: "الفريق" };
const SIGNAL = { rising: "حراك متصاعد", falling: "تراجع", steady: "مستقر", none: "لا تغطية" };
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
function chipsP(codes) { return codes.map((c) => `<a class="chip" href="#/news?p=${c}" title="${esc(P(c)?.nameAr)}">${c} ${esc(P(c)?.nameAr || "")}</a>`).join(""); }
function chipsI(codes) { return codes.map((c) => `<a class="chip i" href="#/news?i=${c}" title="${esc(I(c)?.nameAr)}">${c} ${esc(trim(I(c)?.nameAr, 48))}</a>`).join(""); }
function trim(s, n) { s = s || ""; return s.length > n ? s.slice(0, n - 1) + "…" : s; }

function newsItem(a, opts = {}) {
  const d = draftFor(a.id);
  const reasons = (a.r || []).filter((r) => r !== "priority_only").map((r) => `<span class="chip r">${esc(S.meta.reasonLabels[r] || r)}</span>`).join("");
  const acts = opts.actions && (a.st === "review" || a.st === "uncertain" || opts.allActions) ? `
    <div class="acts noprint">
      ${a.p.length ? `<button class="btn sm ok" data-act="confirm" data-id="${a.id}">✓ تأكيد</button>` : ""}
      <button class="btn sm" data-act="assign" data-id="${a.id}">تعديل الربط</button>
      <button class="btn sm no" data-act="reject" data-id="${a.id}">✗ غير مرتبط</button>
      ${d ? `<span class="chip t">مسودة: ${esc(d.decision)}</span>` : ""}
    </div>` : "";
  return `<li>
    <a class="h" href="${esc(a.u)}" target="_blank" rel="noopener">${esc(a.t)}</a>
    <div class="m">${esc(a.pub || srcName(a.s))} · ${dateAr(a.d)} · <span class="st ${a.st}">${STATUS[a.st]}</span> · ${METHOD[a.m] || a.m}</div>
    <div>${chipsP(a.p)}${chipsI(a.i)}</div>
    ${a.x && opts.excerpt !== false ? `<div class="x">${esc(trim(a.x, 220))}</div>` : ""}
    ${a.ai ? `<div class="ai">🤖 ${esc(a.ai)} <span class="muted">(ثقة ${Math.round((a.ac || 0) * 100)}%)</span></div>` : ""}
    <div>${(a.k || []).map((k) => `<span class="chip t">${esc(k)}</span>`).join("")}${reasons}</div>
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

function viewHome() {
  const m = S.meta, se = S.series, n = se.total.length;
  const thisW = se.total[n - 1], lastW = se.total[n - 2] || 0;
  const r4 = lastN(se.total, 4), p4 = lastN(se.total.slice(0, -4), 4);
  const okSrc = m.sources.filter((s) => s.active && !s.consecutiveFailures && s.lastSuccessAt).length;
  const actSrc = m.sources.filter((s) => s.active).length;
  const delta = (a, b) => { if (!b) return `<span class="muted">—</span>`; const p = Math.round(((a - b) / b) * 100); return `<span class="${p >= 0 ? "up" : "down"}">${p >= 0 ? "▲" : "▼"} ${fmt(Math.abs(p))}%</span>`; };
  const first = Math.max(0, se.total.findIndex((v) => v > 0));
  const layers = m.axes.map((ax) => ({ name: ax.nameAr, color: AX_COLORS[ax.id], vals: (se.axes[ax.id] || []).slice(first) }));
  const weeksRev = se.weeks.slice(first);
  const rising = m.indicators.filter((i) => m.signals[i.code]?.level === "rising").sort((a, b) => m.signals[b.code].recent - m.signals[a.code].recent);
  const falling = m.indicators.filter((i) => m.signals[i.code]?.level === "falling");
  const latest = S.articles.filter((a) => a.st === "auto" || a.st === "confirmed").slice(0, 8);
  const maxP = Math.max(1, ...m.priorities.map((p) => lastN(weeksVals(p.code), 4)));

  return `<h1>لوحة الحراك</h1><p class="sub">أخبار مرتبطة بأولويات رؤية عُمان 2040 ومؤشراتها — آخر تحديث ${dateAr(m.builtAt.slice(0, 10))}</p>
  <div class="grid g4">
    <div class="card kpi"><div class="l">هذا الأسبوع (حتى الآن)</div><div class="v">${fmt(thisW)}</div><div class="d">الأسبوع الماضي ${fmt(lastW)}</div></div>
    <div class="card kpi"><div class="l">آخر 4 أسابيع</div><div class="v">${fmt(r4)}</div><div class="d">${delta(r4, p4)} عن الأسابيع الأربعة قبلها</div></div>
    <div class="card kpi"><div class="l">بانتظار تأكيد الفريق</div><div class="v">${fmt(m.totals.review)}</div><div class="d"><a href="#/review">مراجعة</a> · محتملة ${fmt(m.totals.uncertain)}</div></div>
    <div class="card kpi"><div class="l">المصادر العاملة</div><div class="v">${m.lastRun ? `${fmt(okSrc)} / ${fmt(actSrc)}` : "—"}</div>${m.lastRun ? "" : `<div class="d muted">لم يعمل الجمع التلقائي بعد</div>`}<div class="d"><a href="#/sources">حالة المصادر</a></div></div>
  </div>
  <div class="card" style="margin-top:16px"><div class="row"><h2>الحراك الأسبوعي حسب المحور</h2><span class="spacer"></span>
    <div class="legend">${m.axes.map((a) => `<span><i style="background:${AX_COLORS[a.id]}"></i>${esc(a.nameAr)}</span>`).join("")}</div></div>
    ${stackChart(weeksRev, layers)}</div>
  <h2 style="margin-top:22px">الأولويات — آخر 4 أسابيع</h2>
  <div class="grid g2">${m.axes.map((ax) => `<div class="card axis" style="--ax:${AX_COLORS[ax.id]}">
      <h3>${esc(ax.nameAr)} <span>${fmt(ax.priorities.reduce((s, c) => s + lastN(weeksVals(c), 4), 0))} خبر</span></h3>
      ${ax.priorities.map((c) => { const v = lastN(weeksVals(c), 4), sg = m.signals[c]; return `<div class="prow" data-go="#/news?p=${c}">
        <div><div class="pn">${esc(P(c).nameAr)}</div><span class="sig ${sg.level}">${SIGNAL[sg.level]}</span></div>
        <div>${spark(weeksVals(c).slice(-12), AX_COLORS[ax.id])}<div class="bar"><i style="width:${(v / maxP) * 100}%"></i></div></div>
        <div class="num">${fmt(v)}</div></div>`; }).join("")}
    </div>`).join("")}</div>
  <div class="grid g2" style="margin-top:16px">
    <div class="card"><h2>إشارات الحراك على المؤشرات</h2>
      <p class="note">مقارنة عدد الأخبار المرتبطة بكل مؤشر في آخر 4 أسابيع بمتوسطه في الأسابيع الـ12 السابقة. الإشارة تعكس حجم التغطية، ولا تعني أثرًا فعليًا على قيمة المؤشر.</p>
      ${rising.length ? `<h3 class="up">حراك متصاعد</h3><table>${rising.slice(0, 8).map((i) => sigRow(i)).join("")}</table>` : `<p class="muted">لا يوجد حراك متصاعد حاليًا.</p>`}
      ${falling.length ? `<h3 class="down" style="margin-top:12px">تراجع في التغطية</h3><table>${falling.slice(0, 6).map((i) => sigRow(i)).join("")}</table>` : ""}
    </div>
    <div class="card"><div class="row"><h2>أحدث الأخبار</h2><span class="spacer"></span><a href="#/news">الكل ←</a></div>
      <ul class="news">${latest.map((a) => newsItem(a, { excerpt: false })).join("")}</ul></div>
  </div>`;
}
function sigRow(i) {
  const s = S.meta.signals[i.code];
  return `<tr class="ind-row" data-go="#/news?i=${i.code}"><td>${i.code}</td><td>${esc(i.nameAr)}<div class="muted" style="font-size:12px">${esc(P(i.priority).nameAr)}</div></td>
    <td class="n">${fmt(s.recent)}<div class="muted" style="font-size:11px">المعتاد ${fmt(s.baseline)}</div></td><td>${spark(weeksVals(i.code, "indicators").slice(-12), "var(--brand2)", 80, 22)}</td></tr>`;
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

/* --- الأولويات والمؤشرات */
function viewTaxonomy() {
  const m = S.meta;
  return `<h1>الأولويات والمؤشرات</h1><p class="sub">المحاور الأربعة ← 12 أولوية ← 38 مؤشرًا (القائمة المحدثة). الأعداد للأخبار المحتسبة؛ «آخر 4 أسابيع» مع إشارة الحراك.</p>
  ${m.axes.map((ax) => `<div class="card axis" style="--ax:${AX_COLORS[ax.id]};margin-bottom:16px"><h2>المحور ${ax.number}: ${esc(ax.nameAr)}</h2>
    ${ax.priorities.map((c) => { const p = P(c), sg = m.signals[c]; const inds = m.indicators.filter((i) => i.priority === c); return `
      <h3 style="margin-top:14px" class="row"><a href="#/news?p=${c}">${c} — ${esc(p.nameAr)}</a> <span class="sig ${sg.level}">${SIGNAL[sg.level]}</span>
        <span class="spacer"></span><span class="muted" style="font-size:13px;font-weight:500">الإجمالي ${fmt(m.totals.byPriority[c])} · آخر 4 أسابيع ${fmt(sg.recent)}</span></h3>
      <table><thead><tr><th style="width:52px">الرمز</th><th>المؤشر</th><th class="n">الإجمالي</th><th class="n">آخر 4 أسابيع</th><th>الاتجاه (12 أسبوعًا)</th><th>الإشارة</th><th class="noprint">الداشبورد</th></tr></thead><tbody>
      ${inds.map((i) => { const s = m.signals[i.code]; return `<tr class="ind-row" data-go="#/news?i=${i.code}"><td>${i.code}</td><td>${esc(i.nameAr)}</td><td class="n">${fmt(m.totals.byIndicator[i.code])}</td><td class="n">${fmt(s.recent)}</td>
        <td>${spark(weeksVals(i.code, "indicators").slice(-12), AX_COLORS[ax.id], 90, 22)}</td><td><span class="sig ${s.level}">${SIGNAL[s.level]}</span></td>
        <td class="noprint">${i.dashboardCode && m.dashboardUrl ? `<a href="${esc(m.dashboardUrl)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${esc(i.dashboardCode)}</a>` : `<span class="muted">—</span>`}</td></tr>`; }).join("")}
      </tbody></table>`; }).join("")}
  </div>`).join("")}`;
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
    <h1>تقرير حراك رؤية عُمان 2040 ${kind}</h1><p class="sub">${esc(r.label)}${r.partial ? " — حتى الآن" : ""}</p>
    <div class="grid g3"><div class="kpi"><div class="l">أخبار مرتبطة بالرؤية</div><div class="v">${fmt(r.total)}</div><div class="d">السابقة ${fmt(r.prevTotal)} ${ch(r.total, r.prevTotal)}</div></div>
      <div class="kpi"><div class="l">بانتظار تأكيد الفريق</div><div class="v">${fmt(r.awaiting)}</div></div>
      <div class="kpi"><div class="l">أولويات بلا أخبار</div><div class="v">${fmt(r.silentPriorities.length)}</div></div></div>
    ${r.highlights.length ? `<ul class="hl">${r.highlights.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : ""}
    <h2>حسب المحاور</h2><table><tr><th>المحور</th><th class="n">الأخبار</th><th class="n">السابقة</th><th class="n">التغير</th></tr>
      ${r.axes.map((a) => `<tr><td>${esc(a.nameAr)}</td><td class="n">${fmt(a.count)}</td><td class="n">${fmt(a.prev)}</td><td class="n">${ch(a.count, a.prev)}</td></tr>`).join("")}</table>
    <h2>حسب الأولويات</h2>
    ${pr.filter((p) => p.count).map((p) => `<div style="margin:14px 0 18px"><h3>${p.code} — ${esc(p.nameAr)} <span class="muted" style="font-weight:500">(${fmt(p.count)}، السابقة ${fmt(p.prev)})</span></h3>
      ${p.indicators.length ? `<div>${p.indicators.map((i) => `<span class="chip i">${i.code} ${esc(trim(i.nameAr, 55))} (${fmt(i.count)})</span>`).join("")}</div>` : `<div class="muted" style="font-size:13px">ارتباط على مستوى الأولوية دون مؤشر محدد.</div>`}
      <ul>${p.headlines.map((h) => `<li><a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a> <span class="muted" style="font-size:12px">— ${esc(srcName(h.source))}، ${dateAr(h.date)}</span></li>`).join("")}</ul></div>`).join("")}
    ${r.silentPriorities.length ? `<h2>أولويات بلا أخبار</h2><p>${r.silentPriorities.map((c) => esc(P(c).nameAr)).join("، ")}</p>` : ""}
    <h2>المؤشرات</h2><table><tr><th>الرمز</th><th>المؤشر</th><th class="n">الأخبار</th><th class="n">السابقة</th></tr>
      ${r.indicators.map((i) => `<tr><td>${i.code}</td><td>${esc(i.nameAr)}</td><td class="n">${fmt(i.count)}</td><td class="n">${fmt(i.prev)}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">لا يوجد</td></tr>`}</table>
    <p class="muted" style="font-size:13px">مؤشرات بلا أي خبر في هذه الفترة: ${fmt(r.silentIndicators.length)} من 38.</p>
    <h2>المصادر</h2><p>${r.sources.map((s) => `${esc(s.nameAr)} (${fmt(s.count)})`).join("، ") || "—"}</p>
    <p class="note">يعكس التقرير حجم التغطية الإعلامية المرتبطة بأولويات الرؤية ومؤشراتها وفق قواعد تصنيف موثقة (الإصدار ${esc(S.meta.rulesVersion)}). عدد الأخبار مؤشر على الحراك، وليس قياسًا للأثر أو الإنجاز.</p>
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
  return `<div class="card" style="max-width:860px"><h1>المنهجية</h1>
  <h2 style="margin-top:16px">ماذا يُرصد؟</h2><p>الأخبار المنشورة في المصادر العُمانية الرسمية والصحفية، وما تنشره المصادر العالمية عن عُمان. لا يُحفظ أي خبر لمجرد ذكره الرؤية؛ يُحفظ فقط ما يثبت ارتباطه بأولوية من أولوياتها الـ12 أو بمؤشر من مؤشراتها الـ38 (القائمة المحدثة).</p>
  <h2>كيف يُصنَّف؟</h2><ol>
    <li><b>السياق العُماني:</b> ذكر عُمان أو محافظاتها أو ولاياتها أو مؤسساتها، أو أن الخبر من صحيفة عمانية ولا يتحدث عن بلد آخر.</li>
    <li><b>الأولوية:</b> مصطلحات موضوعية لكل أولوية؛ للعنوان وزن مضاعف. تُثبت الأولوية بثلاث نقاط فأكثر أو بمؤشر تابع لها.</li>
    <li><b>المؤشر:</b> لا يُربط الخبر بمؤشر إلا بدليل مباشر (اسم المؤشر أو مصطلح يحرّكه مباشرة). الربط بالأولوية وحدها مقبول.</li>
    <li><b>الاستبعاد:</b> الرياضة والطقس والحوادث والتعازي والأخبار الخارجية.</li>
    <li><b>بانتظار التأكيد:</b> أولويتان متقاربتان، أو سياق عماني ضعيف، أو دليل مؤشر ضعيف، أو نفي وشائعة. هذه لا تُحتسب حتى يؤكدها الفريق.</li>
    <li><b>المحتملة:</b> إشارة موضوعية دون حد الإثبات. يحسمها الذكاء الاصطناعي إن فُعّل (ثقة 75% فأكثر تُعتمد، 50–75% تُحال للتأكيد)، وإلا تبقى للفريق.</li></ol>
  <h2>إشارات الحراك</h2><p>لكل أولوية ومؤشر: عدد الأخبار في آخر 4 أسابيع مقابل متوسطه في الأسابيع الـ12 السابقة. «حراك متصاعد» إذا بلغ 3 أخبار فأكثر و1.5 ضعف المعتاد. الإشارة تقيس التغطية الإعلامية فقط، ولا تثبت أثرًا على قيمة المؤشر. هي مدخل لسؤال: هل يُتوقع أن يتحرك المؤشر؟</p>
  <h2>ما يُحفظ</h2><p>العنوان ومقتطف قصير ورابط المصدر والتصنيف وسببه. لا يُعاد نشر نص الخبر.</p>
  <p class="muted">إصدار القواعد: ${esc(m.rulesVersion)} · آخر بناء: ${new Date(m.builtAt).toLocaleString("ar-OM-u-nu-latn")}</p></div>`;
}

/* ------------------------------------------------------------ التوجيه */
async function loadUncertain() { return S.uncertain || (S.uncertain = await getJSON("data/uncertain.json")); }

const VIEWS = { home: viewHome, news: viewNews, taxonomy: viewTaxonomy, reports: viewReports, review: viewReview, sources: viewSources, about: viewAbout };
async function route() {
  const [path, qs] = (location.hash.slice(2) || "").split("?");
  const name = VIEWS[path] ? path : "home";
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === name));
  const app = $("#app");
  try {
    app.innerHTML = await VIEWS[name](new URLSearchParams(qs || ""));
  } catch (e) {
    app.innerHTML = `<div class="card"><h2>تعذر عرض الصفحة</h2><p class="muted">${esc(e.message)}</p></div>`;
  }
  app.querySelectorAll("[data-go]").forEach((el) => el.addEventListener("click", () => (location.hash = el.dataset.go)));
  bindActions(app);
}

async function boot() {
  try {
    [S.meta, S.series, S.articles] = await Promise.all([getJSON("data/meta.json"), getJSON("data/series.json"), getJSON("data/articles.json")]);
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
