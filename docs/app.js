// رادار سيارة البر — واجهة العرض (تقرأ data/listings.json)
const LABELS = { "فرصة": "good", "يستحق السؤال": "mid", "ضعيف": "weak", "مستبعد": "bad", "مغلق": "bad" };
const STATUSES = ["جديد", "تواصلت", "بانتظار رد", "معاينة", "فحص", "تفاوض", "مستبعد يدويًا", "تم الشراء", "مباع"];
const BREAK = { price_value: "السعر", model_fit: "الموديل", condition: "الحالة", mileage: "الممشى", year: "السنة", distance: "المسافة" };

// owner/repo: من رابط GitHub Pages تلقائيًا، أو عدّلها يدويًا هنا
const REPO = (() => {
  const h = location.hostname, seg = location.pathname.split("/").filter(Boolean);
  if (h.endsWith(".github.io")) return `${h.split(".")[0]}/${seg[0] || h}`;
  return window.REPO_OVERRIDE || "OWNER/REPO";
})();
const GH = `https://github.com/${REPO}`;

let DB = { listings: [] }, activeLabels = new Set(["فرصة", "يستحق السؤال"]);
const $ = (s) => document.querySelector(s);
const fmt = (n) => (n == null ? "؟" : Number(n).toLocaleString("en-US"));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ago = (iso) => {
  if (!iso) return "";
  const m = (Date.now() - new Date(iso)) / 60000;
  if (m < 1) return "الآن";
  if (m < 60) return `قبل ${Math.round(m)} دقيقة`;
  if (m < 1440) return `قبل ${Math.round(m / 60)} ساعة`;
  return `قبل ${Math.round(m / 1440)} يوم`;
};
const scoreColor = (s) => (s >= 70 ? "var(--good)" : s >= 50 ? "var(--mid)" : "var(--weak)");

async function load() {
  $("#btn-add").href = `${GH}/issues/new?template=add-offer.yml`;
  $("#btn-run").href = `${GH}/actions/workflows/collect.yml`;
  $("#btn-config").href = `${GH}/edit/main/config.yaml`;
  try {
    const r = await fetch(`data/listings.json?t=${Date.now()}`);
    if (r.ok) DB = await r.json();
  } catch (e) { /* empty state */ }
  $("#updated").textContent = DB.updated_at ? `آخر تحديث ${ago(DB.updated_at)} · ${DB.listings.length} عرض` : "لا توجد بيانات بعد — شغّل البحث أو أضف عرضًا";
  initFilters();
  render();
}

function initFilters() {
  const models = [...new Set(DB.listings.map((l) => l.model_name).filter(Boolean))].sort();
  $("#f-model").innerHTML = `<option value="">كل الموديلات</option>` + models.map((m) => `<option>${esc(m)}</option>`).join("");
  $("#f-status").innerHTML = `<option value="">كل الحالات</option>` + STATUSES.map((s) => `<option>${s}</option>`).join("");
  ["#f-q", "#f-model", "#f-dist", "#f-status", "#f-sort", "#f-all"].forEach((s) => $(s).addEventListener("input", render));
  const chips = Object.keys(LABELS).filter((l) => l !== "مغلق");
  $("#label-chips").innerHTML = chips.map((l) => `<button class="chip ${activeLabels.has(l) ? "on" : ""}" data-l="${l}">${l}</button>`).join("");
  $("#label-chips").onclick = (e) => {
    const l = e.target.dataset.l; if (!l) return;
    activeLabels.has(l) ? activeLabels.delete(l) : activeLabels.add(l);
    e.target.classList.toggle("on"); render();
  };
  document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => {
    document.querySelectorAll(".tab,.panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active"); $("#" + t.dataset.tab).classList.add("active");
  }));
}

function filtered() {
  const q = $("#f-q").value.trim(), model = $("#f-model").value, dist = +$("#f-dist").value || 0;
  const st = $("#f-status").value, all = $("#f-all").checked, sort = $("#f-sort").value;
  let xs = DB.listings.filter((l) => {
    if (!all && (l.archived || l.label === "مستبعد" || l.label === "مغلق")) return false;
    if (activeLabels.size && !activeLabels.has(l.label) && !(all && (l.label === "مستبعد" || l.label === "مغلق"))) return false;
    if (model && l.model_name !== model) return false;
    if (dist && (l.distance_km == null || l.distance_km > dist)) return false;
    if (st && l.status !== st) return false;
    if (q && !`${l.title} ${l.body} ${l.city}`.includes(q)) return false;
    return true;
  });
  const key = {
    score: (a, b) => b.score - a.score,
    new: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""),
    price: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9),
    km: (a, b) => (a.mileage_km ?? 1e9) - (b.mileage_km ?? 1e9),
    year: (a, b) => (b.year ?? 0) - (a.year ?? 0),
  }[sort];
  return xs.sort(key);
}

function card(l) {
  const img = (l.images || [])[0];
  const cls = LABELS[l.label] || "weak";
  const priceTxt = l.price ? `${fmt(l.price)} ريال${l.price_type === "bid" ? " (سوم)" : ""}` : l.price_type === "negotiable" ? "على السوم" : "السعر ؟";
  const reasons = [
    ...(l.exclude_reasons || []).map((r) => `<li class="exc">⛔ ${esc(r)}</li>`),
    ...(l.reasons_pos || []).slice(0, 3).map((r) => `<li class="pos">✓ ${esc(r)}</li>`),
    ...(l.reasons_neg || []).slice(0, 3).map((r) => `<li class="neg">! ${esc(r)}</li>`),
  ].join("");
  const bars = Object.entries(l.breakdown || {}).map(([k, v]) => `<span>${BREAK[k] || k}</span><div class="bar"><i style="width:${v}%"></i></div>`).join("");
  const notes = (l.notes || []).map((n) => `<div>📝 <b>${esc(n.by)}</b> (${esc(n.date)}): ${esc(n.text)}</div>`).join("");
  const ph = (l.price_history || []).length > 1 ? `<div class="meta">تاريخ السعر: ${l.price_history.map((p) => fmt(p.price)).join(" ← ")}</div>` : "";
  const statusUrl = `${GH}/issues/new?template=update-status.yml&title=${encodeURIComponent("تحديث: " + (l.title || "").slice(0, 40))}&offer_id=${encodeURIComponent(l.id)}`;
  return `<article class="card ${l.archived || cls === "bad" ? "dim" : ""}">
    <div class="thumb" ${img ? `style="background-image:url('${esc(img)}')"` : ""}>${img ? "" : '<div class="noimg">🚙</div>'}
      <div class="score" style="background:${scoreColor(l.score)}">${l.score}</div>
      <span class="badge l-${cls}">${esc(l.label)}</span></div>
    <div class="body">
      <h3 class="title">${esc(l.title)}</h3>
      <div class="specs">
        <span class="spec price">${priceTxt}</span>
        <span class="spec">${esc(l.model_name || "موديل ؟")}${l.year ? " · " + l.year : ""}</span>
        <span class="spec">${l.mileage_km ? fmt(l.mileage_km) + " كم" : "ممشى ؟"}</span>
        <span class="spec">${l.is_4x4 === true ? "دبل ✓" : l.is_4x4 === false ? "غير دبل" : "دبل ؟"}</span>
        ${l.transmission ? `<span class="spec">${esc(l.transmission)}</span>` : ""}
        ${l.fuel ? `<span class="spec">${esc(l.fuel)}</span>` : ""}
        <span class="spec">📍 ${esc(l.city || "؟")}${l.distance_km ? ` (${fmt(l.distance_km)} كم)` : ""}</span>
      </div>
      ${l.ai_summary ? `<div class="ai">🤖 ${esc(l.ai_summary)}</div>` : ""}
      <ul class="reasons">${reasons}</ul>
      <details><summary>تفصيل الدرجة والوصف</summary><div class="bars">${bars}</div><p class="muted">${esc(l.body || "")}</p></details>
      ${ph}
      ${notes ? `<div class="notes">${notes}</div>` : ""}
      <div class="meta"><span class="status">${esc(l.status)}</span><span>${esc(l.source)} · ${ago(l.first_seen)}${l.added_by && l.added_by !== "auto" ? " · أضافه " + esc(l.added_by) : ""}</span></div>
    </div>
    <div class="cardfoot">
      <a class="btn sm primary" href="${esc(l.url)}" target="_blank">فتح الإعلان</a>
      <a class="btn sm" href="${statusUrl}" target="_blank">تحديث الحالة</a>
      <button class="btn sm" data-msg="${esc(l.id)}">رسالة للبائع</button>
      <button class="btn sm" data-copy="${esc(l.id)}" title="نسخ رقم العرض">#</button>
    </div></article>`;
}

function render() {
  const xs = filtered();
  $("#list").innerHTML = xs.map(card).join("");
  $("#empty").classList.toggle("hidden", xs.length > 0);
  $("#empty").textContent = DB.listings.length ? "لا توجد عروض مطابقة للفلاتر." : "لا توجد عروض بعد. اضغط «بحث الآن» أو «أضف عرض».";
  renderTiles(); renderBoard(); renderMarket();
}

function renderTiles() {
  const live = DB.listings.filter((l) => !l.archived);
  const c = (f) => live.filter(f).length;
  const tiles = [
    ["🟢 فرص", c((l) => l.label === "فرصة"), "فرصة"],
    ["🟡 تستحق السؤال", c((l) => l.label === "يستحق السؤال"), "يستحق السؤال"],
    ["⚪ ضعيفة", c((l) => l.label === "ضعيف"), "ضعيف"],
    ["⛔ مستبعدة", c((l) => l.label === "مستبعد"), "مستبعد"],
    ["📌 قيد المتابعة", c((l) => !["جديد", "مستبعد يدويًا"].includes(l.status)), null],
    ["🆕 آخر 24 ساعة", c((l) => Date.now() - new Date(l.first_seen) < 864e5), null],
  ];
  $("#tiles").innerHTML = tiles.map(([t, n, l]) => `<div class="tile" ${l ? `data-l="${l}"` : ""}><b>${n}</b><span>${t}</span></div>`).join("");
  $("#tiles").onclick = (e) => {
    const l = e.target.closest(".tile")?.dataset.l; if (!l) return;
    activeLabels = new Set([l]);
    if (l === "مستبعد") $("#f-all").checked = true;
    document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", activeLabels.has(c.dataset.l)));
    render();
  };
}

function renderBoard() {
  const cols = STATUSES.filter((s) => s !== "جديد");
  $("#board").innerHTML = cols.map((s) => {
    const xs = DB.listings.filter((l) => l.status === s);
    return `<div class="col"><h4>${s} (${xs.length})</h4>${xs.map((l) => `<div class="mini"><b>${l.score}</b> · <a href="${esc(l.url)}" target="_blank">${esc(l.title)}</a><br>${l.price ? fmt(l.price) + " ريال" : ""} ${esc(l.city || "")}${(l.notes || []).length ? `<br>📝 ${esc(l.notes.at(-1).text)}` : ""}</div>`).join("") || '<p class="muted">—</p>'}</div>`;
  }).join("");
}

function renderMarket() {
  const s = DB.stats || {}, names = DB.stats_names || {};
  const rows = Object.entries(s).sort((a, b) => b[1].n - a[1].n);
  $("#market-tbl").innerHTML = `<tr><th>الموديل</th><th>عدد العروض المسعّرة</th><th>متوسط السعر (الوسيط)</th></tr>` +
    (rows.map(([k, v]) => `<tr><td>${esc(names[k] || k)}</td><td>${v.n}</td><td>${fmt(v.median)} ريال</td></tr>`).join("") || `<tr><td colspan="3" class="muted">لا تكفي البيانات بعد</td></tr>`);
  $("#runs-tbl").innerHTML = `<tr><th>الوقت</th><th>النوع</th><th>جديد</th><th>محدّث</th><th>تنبيهات</th><th>أخطاء</th></tr>` +
    (DB.runs || []).map((r) => `<tr><td>${ago(r.at)}</td><td>${r.trigger === "issue" ? "إضافة يدوية (" + esc(r.by) + ")" : r.trigger === "rescore" ? "إعادة تقييم" : "بحث تلقائي"}</td><td>${r.added ?? ""}</td><td>${r.updated ?? ""}</td><td>${r.notified ?? ""}</td><td>${r.errors ?? ""}</td></tr>`).join("");
}

function sellerMessage(l) {
  const ask = [];
  if (!l.price) ask.push("كم السعر المطلوب؟");
  if (!l.mileage_km) ask.push("كم الممشى؟");
  ask.push(l.is_4x4 ? "الدبل شغال بدون مشاكل؟" : "هل هي دبل (دفع رباعي) والدبل شغال؟");
  ask.push("الماكينة والقير مفتوحة أو وكالة؟");
  ask.push("فيها حوادث أو رش؟");
  ask.push("الفحص الدوري والاستمارة سارية؟");
  if (!l.city || (l.distance_km ?? 999) > 100) ask.push("وين موقع السيارة بالضبط؟");
  return `السلام عليكم، بخصوص إعلانك: ${l.title}\n${l.url}\n\nودي أسأل:\n` + ask.map((q, i) => `${i + 1}. ${q}`).join("\n") + "\n\nوشكرًا لك.";
}

document.addEventListener("click", (e) => {
  const id = e.target.dataset?.msg || e.target.dataset?.copy;
  if (!id) return;
  const l = DB.listings.find((x) => x.id === id);
  if (e.target.dataset.copy) { navigator.clipboard?.writeText(id); e.target.textContent = "✓"; return; }
  const txt = sellerMessage(l);
  $("#msg-text").value = txt;
  $("#msg-wa").href = `https://wa.me/?text=${encodeURIComponent(txt)}`;
  $("#msg-dlg").showModal();
});
$("#msg-copy").onclick = () => { navigator.clipboard?.writeText($("#msg-text").value); $("#msg-copy").textContent = "تم النسخ ✓"; };

load();
