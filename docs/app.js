// رادار سيارة البر — واجهة العرض
const LABELS = { "فرصة": "good", "يستحق السؤال": "mid", "ضعيف": "weak", "مستبعد": "bad", "مغلق": "bad" };
const STATUSES = ["جديد", "تواصلت", "بانتظار رد", "معاينة", "فحص", "تفاوض", "مستبعد يدويًا", "تم الشراء", "مباع"];
const BREAK = { price_value: "السعر", model_fit: "الموديل", condition: "الحالة", mileage: "الممشى", year: "السنة", distance: "المسافة" };

const REPO = (() => {
  const h = location.hostname, seg = location.pathname.split("/").filter(Boolean);
  if (h.endsWith(".github.io")) return `${h.split(".")[0]}/${seg[0] || h}`;
  return window.REPO_OVERRIDE || "salotaibi511/Offroad-finder";
})();
const GH = `https://github.com/${REPO}`;
const API = (window.API_URL || "").trim();

let DB = { listings: [] }, EDITS = { pending: [], overrides: {} }, RAW = [];
let activeLabels = new Set(["فرصة", "يستحق السؤال"]);
let watching = { sids: new Set(), refresh: false, editAt: 0 };

const $ = (s) => document.querySelector(s);
const fmt = (n) => (n == null || n === "" ? "؟" : Number(n).toLocaleString("en-US"));
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
const store = {
  get: (k) => { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};

/* ---------------- API bridge ---------------- */
async function api(action, payload = {}, method = "POST") {
  if (!API) throw new Error("no-api");
  let r;
  if (method === "GET") {
    r = await fetch(`${API}?action=${action}&t=${Date.now()}`);
  } else {
    const body = { action, by: store.get("offroad_name") || "زائر", code: store.get("offroad_code"), ...payload };
    r = await fetch(API, { method: "POST", body: JSON.stringify(body) }); // text/plain → no CORS preflight
  }
  const j = await r.json();
  if (!j.ok && j.need_code) {
    const c = prompt("هذا الموقع محمي برمز للتعديل. اكتب الرمز:");
    if (c) { store.set("offroad_code", c); return api(action, payload, method); }
  }
  if (!j.ok) throw new Error(j.error || "خطأ");
  return j;
}

function askName() {
  let n = store.get("offroad_name");
  if (!n) {
    n = (prompt("اكتب اسمك (يظهر بجانب إضافاتك وملاحظاتك):") || "").trim().slice(0, 40);
    if (n) store.set("offroad_name", n);
  }
  return n || "زائر";
}

/* ---------------- data ---------------- */
function applyEdits() {
  const ov = EDITS.overrides || {};
  DB.listings = RAW.map((x) => {
    const l = { ...x }, o = ov[l.id];
    if (!o) return l;
    Object.entries(o.fields || {}).forEach(([k, v]) => { if (v !== null && v !== "") l[k] = v; });
    if ((o.fields || {}).price) l.price_type = "asking";
    if ((o.fields || {}).model_key && DB.stats_names) l.model_name = DB.stats_names[o.fields.model_key] || l.model_name;
    if (o.status) l.status = o.status;
    if (o.notes) l.web_notes = o.notes;
    if (o.hidden) l._hidden = true;
    if (o.likes && Object.keys(o.likes).length) l.likes = o.likes;
    if (Object.keys(o.fields || {}).length) l.edited = { by: o.by, at: o.at };
    return l;
  }).filter((l) => !l._hidden);
}

async function fetchData() {
  if (API) {
    try {
      const j = await api("data", {}, "GET");
      if (j.data && j.data.listings) DB = j.data;
      EDITS = j.edits || EDITS;
      return;
    } catch (e) { console.warn("bridge failed, falling back", e); }
  }
  try {
    const r = await fetch(`data/listings.json?t=${Date.now()}`);
    if (r.ok) DB = await r.json();
    const e = await fetch(`data/edits.json?t=${Date.now()}`);
    if (e.ok) EDITS = await e.json();
  } catch (e) { /* empty */ }
}

async function load(first = false) {
  await fetchData();
  RAW = DB.listings || [];
  applyEdits();
  $("#updated").textContent = DB.updated_at ? `آخر تحديث ${ago(DB.updated_at)} · ${DB.listings.length} عرض` : "لا توجد بيانات بعد";
  if (first) initFilters(); else refreshFilterOptions();
  render();
  checkWatches();
}

/* ---------------- filters ---------------- */
function refreshFilterOptions() {
  const keep = (sel, opts, first) => {
    const v = $(sel).value;
    $(sel).innerHTML = `<option value="">${first}</option>` + opts.map((m) => `<option>${esc(m)}</option>`).join("");
    $(sel).value = v;
  };
  keep("#f-model", [...new Set(DB.listings.map((l) => l.model_name).filter(Boolean))].sort(), "كل الموديلات");
  keep("#f-region", [...new Set(DB.listings.map((l) => l.region).filter(Boolean))].sort(), "كل المناطق");
}

function initFilters() {
  refreshFilterOptions();
  $("#f-status").innerHTML = `<option value="">كل الحالات</option>` + STATUSES.map((s) => `<option>${s}</option>`).join("");
  ["#f-q", "#f-model", "#f-region", "#f-dist", "#f-status", "#f-sort", "#f-all", "#f-fav"].forEach((s) => $(s).addEventListener("input", render));
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
  // header buttons
  if (API) {
    $("#btn-add").removeAttribute("href"); $("#btn-add").onclick = openAdd;
    $("#btn-run").removeAttribute("href"); $("#btn-run").onclick = runRefresh;
  } else {
    $("#btn-add").href = `${GH}/issues/new?template=add-offer.yml`;
    $("#btn-run").href = `${GH}/actions/workflows/collect.yml`;
  }
  $("#btn-config").href = `${GH}/edit/main/config.yaml`;
}

function filtered() {
  const q = $("#f-q").value.trim(), model = $("#f-model").value, region = $("#f-region").value;
  const dist = +$("#f-dist").value || 0, st = $("#f-status").value, all = $("#f-all").checked, sort = $("#f-sort").value;
  const favOnly = $("#f-fav").checked;
  const xs = DB.listings.filter((l) => {
    if (favOnly) return likeCount(l) > 0 && (!q || `${l.title} ${l.body} ${l.city}`.includes(q));
    if (!all && (l.archived || l.label === "مستبعد" || l.label === "مغلق")) return false;
    if (activeLabels.size && !activeLabels.has(l.label) && !(all && (l.label === "مستبعد" || l.label === "مغلق"))) return false;
    if (model && l.model_name !== model) return false;
    if (region && l.region !== region) return false;
    if (dist && (l.distance_km == null || l.distance_km > dist)) return false;
    if (st && l.status !== st) return false;
    if (q && !`${l.title} ${l.body} ${l.city}`.includes(q)) return false;
    return true;
  });
  const key = {
    score: (a, b) => b.score - a.score,
    likes: (a, b) => likeCount(b) - likeCount(a) || b.score - a.score,
    new: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""),
    price: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9),
    km: (a, b) => (a.mileage_km ?? 1e9) - (b.mileage_km ?? 1e9),
    year: (a, b) => (b.year ?? 0) - (a.year ?? 0),
  }[sort];
  return xs.sort(key);
}

/* ---------------- rendering ---------------- */
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
  const likers = Object.entries(l.likes || {});
  const me = store.get("offroad_name");
  const iLike = !!(l.likes && me && l.likes[me]);
  const likeLine = likers.length ? `<div class="likers">❤️ ${likers.map(([n, v]) => `<b>${esc(n)}</b>${v.note ? `: ${esc(v.note)}` : ""}`).join(" · ")}</div>` : "";
  const likeBtn = API ? `<button class="btn sm like ${iLike ? "on" : ""}" data-like="${esc(l.id)}" title="${iLike ? "إلغاء الإعجاب" : "أعجبني"}">${iLike ? "❤️" : "🤍"} ${likers.length || ""}</button>` : (likers.length ? `<span class="btn sm like">❤️ ${likers.length}</span>` : "");
  const notes = [...(l.notes || []), ...(l.web_notes || [])].map((n) => `<div>📝 <b>${esc(n.by)}</b> (${esc(n.date)}): ${esc(n.text)}</div>`).join("");
  const ph = (l.price_history || []).length > 1 ? `<div class="meta">تاريخ السعر: ${l.price_history.map((p) => fmt(p.price)).join(" ← ")}</div>` : "";
  const statusCtl = API
    ? `<select class="status-sel" data-status="${esc(l.id)}">${STATUSES.map((s) => `<option ${s === l.status ? "selected" : ""}>${s}</option>`).join("")}</select>`
    : `<span class="status">${esc(l.status)}</span>`;
  const editBtn = API
    ? `<button class="btn sm" data-edit="${esc(l.id)}">✏️ تعديل</button>`
    : `<a class="btn sm" href="${GH}/issues/new?template=update-status.yml&offer_id=${encodeURIComponent(l.id)}" target="_blank">تحديث الحالة</a>`;
  return `<article class="card ${l.archived || cls === "bad" ? "dim" : ""}" id="c-${esc(l.id).replace(/[^\w-]/g, "_")}">
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
        <span class="spec loc">📍 ${esc(l.city || "المدينة ؟")}${l.region ? " · " + esc(l.region) : ""}${l.distance_km != null ? (l.distance_km === 0 ? " · في جدة" : ` · ~${fmt(l.distance_km)} كم من جدة`) : ""}</span>
      </div>
      ${l.ai_summary ? `<div class="ai">🤖 ${esc(l.ai_summary)}</div>` : ""}
      <ul class="reasons">${reasons}</ul>
      <details><summary>تفصيل الدرجة والوصف</summary><div class="bars">${bars}</div><p class="muted">${esc(l.body || "")}</p></details>
      ${ph}
      ${likeLine}
      ${notes ? `<div class="notes">${notes}</div>` : ""}
      <div class="meta">${statusCtl}<span>${esc(l.source)} · ${ago(l.first_seen)}${l.added_by && l.added_by !== "auto" ? " · أضافه " + esc(String(l.added_by).replace("auto+", "")) : ""}${l.edited ? ` · ✏️ عدّله ${esc(l.edited.by)}` : ""}</span></div>
    </div>
    <div class="cardfoot">
      <a class="btn sm primary" href="${esc(l.url)}" target="_blank">فتح الإعلان</a>
      ${likeBtn}
      ${editBtn}
      <button class="btn sm" data-msg="${esc(l.id)}">رسالة للبائع</button>
    </div></article>`;
}

function pendingCards() {
  const done = DB.submissions || {};
  const ps = (EDITS.pending || []).filter((p) => !done[p.sid] && Date.now() - new Date(p.at) < 2 * 3600e3);
  return ps.map((p) => `<article class="card pending"><div class="body"><h3 class="title">⏳ جارِ إضافة العرض…</h3>
      <p class="muted" style="word-break:break-all">${esc(p.url)}</p><p class="muted">أضافه ${esc(p.by)} · ${ago(p.at)} — يظهر هنا خلال دقيقة إلى دقيقتين</p></div></article>`).join("");
}

function render() {
  const xs = filtered();
  $("#list").innerHTML = pendingCards() + xs.map(card).join("");
  $("#empty").classList.toggle("hidden", xs.length > 0);
  $("#empty").textContent = DB.listings.length ? "لا توجد عروض مطابقة للفلاتر." : "لا توجد عروض بعد. اضغط «تحديث» أو «أضف عرض».";
  renderTiles(); renderBoard(); renderMarket(); renderFavs();
}

function likeCount(l) { return Object.keys(l.likes || {}).length; }

function renderFavs() {
  const liked = DB.listings.filter((l) => likeCount(l) > 0).sort((a, b) => likeCount(b) - likeCount(a) || b.score - a.score);
  $("#fav-count").textContent = liked.length ? `(${liked.length})` : "";
  if (!liked.length) {
    $("#favs").innerHTML = `<p class="empty">لا توجد عروض في المفضلة بعد. اضغط 🤍 على أي عرض يعجبك ليظهر هنا للجميع.</p>`;
    return;
  }
  const members = {};
  liked.forEach((l) => Object.keys(l.likes).forEach((n) => (members[n] = members[n] || []).push(l)));
  const row = (l) => `<div class="fav-row">
      <div class="score sm" style="background:${scoreColor(l.score)}">${l.score}</div>
      <div class="fav-main">
        <a href="${esc(l.url)}" target="_blank"><b>${esc(l.title)}</b></a>
        <div class="muted">${l.price ? fmt(l.price) + " ريال" : "السعر ؟"} · ${esc(l.model_name || "")} ${l.year || ""} · ${l.mileage_km ? fmt(l.mileage_km) + " كم" : "ممشى ؟"} · 📍 ${esc(l.city || "؟")} · <span class="status">${esc(l.status)}</span></div>
        <div class="likers">❤️ ${Object.entries(l.likes).map(([n, v]) => `<b>${esc(n)}</b>${v.note ? `: ${esc(v.note)}` : ""}`).join(" · ")}</div>
      </div>
      ${API ? `<button class="btn sm like ${l.likes[store.get("offroad_name")] ? "on" : ""}" data-like="${esc(l.id)}">${l.likes[store.get("offroad_name")] ? "❤️" : "🤍"} ${likeCount(l)}</button>` : `<span class="btn sm">❤️ ${likeCount(l)}</span>`}
    </div>`;
  $("#favs").innerHTML = `<h3>الأكثر إعجابًا</h3><div class="fav-list">${liked.map(row).join("")}</div>
    <h3>قائمة كل عضو</h3><div class="members">${Object.entries(members).sort((a, b) => b[1].length - a[1].length).map(([n, xs]) =>
      `<div class="col"><h4>${esc(n)} (${xs.length})</h4>${xs.map((l) => `<div class="mini"><b>${l.score}</b> · <a href="${esc(l.url)}" target="_blank">${esc(l.title)}</a><br>${l.price ? fmt(l.price) + " ريال" : ""} ${esc(l.city || "")}${l.likes[n].note ? `<br>💬 ${esc(l.likes[n].note)}` : ""}</div>`).join("")}</div>`).join("")}</div>`;
}

function renderTiles() {
  const live = DB.listings.filter((l) => !l.archived);
  const c = (f) => live.filter(f).length;
  const tiles = [
    ["🟢 فرص", c((l) => l.label === "فرصة"), "فرصة"],
    ["🟡 تستحق السؤال", c((l) => l.label === "يستحق السؤال"), "يستحق السؤال"],
    ["⚪ ضعيفة", c((l) => l.label === "ضعيف"), "ضعيف"],
    ["⛔ خارج المواصفات", c((l) => l.label === "مستبعد"), "مستبعد"],
    ["❤️ في المفضلة", c((l) => likeCount(l) > 0), "__fav"],
    ["📌 قيد المتابعة", c((l) => !["جديد", "مستبعد يدويًا"].includes(l.status)), null],

  ];
  $("#tiles").innerHTML = tiles.map(([t, n, l]) => `<div class="tile" ${l ? `data-l="${l}"` : ""}><b>${n}</b><span>${t}</span></div>`).join("");
  $("#tiles").onclick = (e) => {
    const l = e.target.closest(".tile")?.dataset.l; if (!l) return;
    if (l === "__fav") return document.querySelector('.tab[data-tab="favs"]').click();
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
    return `<div class="col"><h4>${s} (${xs.length})</h4>${xs.map((l) => {
      const n = [...(l.notes || []), ...(l.web_notes || [])].at(-1);
      return `<div class="mini"><b>${l.score}</b> · <a href="${esc(l.url)}" target="_blank">${esc(l.title)}</a><br>${l.price ? fmt(l.price) + " ريال" : ""} ${esc(l.city || "")}${n ? `<br>📝 ${esc(n.text)}` : ""}</div>`;
    }).join("") || '<p class="muted">—</p>'}</div>`;
  }).join("");
}

function renderMarket() {
  const s = DB.stats || {}, names = DB.stats_names || {};
  const rows = Object.entries(s).sort((a, b) => b[1].n - a[1].n);
  $("#market-tbl").innerHTML = `<tr><th>الموديل</th><th>عدد العروض المسعّرة</th><th>متوسط السعر (الوسيط)</th></tr>` +
    (rows.map(([k, v]) => `<tr><td>${esc(names[k] || k)}</td><td>${v.n}</td><td>${fmt(v.median)} ريال</td></tr>`).join("") || `<tr><td colspan="3" class="muted">لا تكفي البيانات بعد</td></tr>`);
  const kind = (r) => r.trigger === "issue" || r.trigger === "web" ? "من الموقع" + (r.by ? ` (${esc(r.by)})` : "") : r.trigger === "rescore" ? "إعادة تقييم" : "بحث تلقائي";
  $("#runs-tbl").innerHTML = `<tr><th>الوقت</th><th>النوع</th><th>جديد</th><th>محدّث</th><th>تنبيهات</th></tr>` +
    (DB.runs || []).map((r) => `<tr><td>${ago(r.at)}</td><td>${kind(r)}</td><td>${r.added ?? ""}</td><td>${r.updated ?? ""}</td><td>${r.notified ?? ""}</td></tr>`).join("");
}

/* ---------------- toasts & banner ---------------- */
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`; t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 6000);
}
function banner(msg) {
  $("#banner").classList.toggle("hidden", !msg);
  $("#banner").innerHTML = msg ? `<span class="spin"></span> ${msg}` : "";
}

/* ---------------- add ---------------- */
function openAdd() {
  askName();
  $("#add-urls").value = ""; $("#add-note").value = "";
  $("#add-dlg").showModal();
}
async function submitAdd(e) {
  e.preventDefault();
  const urls = $("#add-urls").value.trim();
  if (!/https?:\/\//.test(urls)) { toast("الصق رابطًا صحيحًا يبدأ بـ https://", "err"); return; }
  $("#add-save").disabled = true;
  try {
    const j = await api("add", { urls, note: $("#add-note").value.trim() });
    $("#add-dlg").close();
    j.added.forEach((a) => { watching.sids.add(a.sid); EDITS.pending.push({ sid: a.sid, url: a.url, by: store.get("offroad_name"), at: new Date().toISOString() }); });
    render();
    toast("✓ استلمت الرابط — يظهر العرض مع تقييمه خلال دقيقة إلى دقيقتين", "ok");
    startPolling();
  } catch (err) { toast("تعذر الإرسال: " + err.message, "err"); }
  finally { $("#add-save").disabled = false; }
}

/* ---------------- edit ---------------- */
let editing = null;
function openEdit(id) {
  const l = DB.listings.find((x) => x.id === id); if (!l) return;
  askName();
  editing = l;
  $("#e-title").value = l.title || "";
  $("#e-price").value = l.price || "";
  $("#e-year").value = l.year || "";
  $("#e-km").value = l.mileage_km || "";
  $("#e-city").value = l.city || "";
  const names = DB.stats_names || {};
  $("#e-model").innerHTML = `<option value="">— كما هو —</option>` + Object.entries(names).map(([k, n]) => `<option value="${k}" ${k === l.model_key ? "selected" : ""}>${esc(n)}</option>`).join("");
  $("#e-4x4").value = l.is_4x4 === true ? "true" : l.is_4x4 === false ? "false" : "";
  $("#e-trans").value = l.transmission || "";
  $("#e-status").innerHTML = STATUSES.map((s) => `<option ${s === l.status ? "selected" : ""}>${s}</option>`).join("");
  $("#e-note").value = "";
  $("#e-hide").checked = false;
  $("#edit-dlg").showModal();
}
async function submitEdit(e) {
  e.preventDefault();
  const l = editing; if (!l) return;
  const f = {};
  const set = (k, v, old) => { if (String(v ?? "") !== String(old ?? "")) f[k] = v; };
  set("title", $("#e-title").value.trim(), l.title);
  set("price", $("#e-price").value, l.price || "");
  set("year", $("#e-year").value, l.year || "");
  set("mileage_km", $("#e-km").value, l.mileage_km || "");
  set("city", $("#e-city").value.trim(), l.city || "");
  if ($("#e-model").value) set("model_key", $("#e-model").value, l.model_key);
  if ($("#e-4x4").value) set("is_4x4", $("#e-4x4").value === "true", l.is_4x4);
  if ($("#e-trans").value) set("transmission", $("#e-trans").value, l.transmission);
  const payload = { id: l.id, fields: f };
  if ($("#e-status").value !== l.status) payload.status = $("#e-status").value;
  if ($("#e-note").value.trim()) payload.note = $("#e-note").value.trim();
  if ($("#e-hide").checked) payload.hidden = true;
  if (!Object.keys(f).length && !payload.status && !payload.note && !payload.hidden) { $("#edit-dlg").close(); return; }
  $("#e-save").disabled = true;
  try {
    const j = await api("edit", payload);
    EDITS.overrides[l.id] = j.override;
    applyEdits(); render();
    $("#edit-dlg").close();
    toast(Object.keys(f).length ? "✓ تم الحفظ — يُعاد حساب التقييم خلال دقيقة" : "✓ تم الحفظ", "ok");
    if (Object.keys(f).length) { watching.editAt = Date.now(); startPolling(); }
  } catch (err) { toast("تعذر الحفظ: " + err.message, "err"); }
  finally { $("#e-save").disabled = false; }
}
async function quickStatus(id, status) {
  askName();
  try {
    const j = await api("edit", { id, status });
    EDITS.overrides[id] = j.override;
    applyEdits(); render();
    toast(`✓ الحالة: ${status}`, "ok");
  } catch (err) { toast("تعذر الحفظ: " + err.message, "err"); render(); }
}

/* ---------------- likes ---------------- */
let liking = null;
async function toggleLike(id) {
  const l = DB.listings.find((x) => x.id === id); if (!l) return;
  const me = askName();
  if (me === "زائر") { toast("اكتب اسمك أولًا حتى يعرف الأعضاء من أعجبه العرض", "err"); return; }
  if (l.likes && l.likes[me]) {
    if (!confirm("إلغاء إعجابك بهذا العرض؟")) return;
    return saveLike(id, false, "");
  }
  liking = id;
  $("#like-title").textContent = l.title;
  $("#like-note").value = "";
  $("#like-dlg").showModal();
}
async function saveLike(id, liked, note) {
  try {
    const j = await api("like", { id, liked, note });
    EDITS.overrides[id] = { ...(EDITS.overrides[id] || {}), likes: j.likes };
    applyEdits(); render();
    toast(liked ? "❤️ أُضيف للمفضلة — يراه كل الأعضاء" : "أُزيل من مفضلتك", "ok");
  } catch (err) {
    toast(/غير معروف/.test(err.message) ? "يلزم تحديث كود الجسر في Google لتفعيل الإعجاب" : "تعذر الحفظ: " + err.message, "err");
  }
}

/* ---------------- refresh (search now) ---------------- */
async function runRefresh() {
  try {
    await api("refresh");
    watching.refresh = Date.now();
    banner("جارِ البحث في حراج الآن… يستغرق عادة 5 إلى 10 دقائق، والصفحة تتحدث وحدها");
    startPolling();
  } catch (err) { toast("تعذر بدء البحث: " + err.message, "err"); }
}

/* ---------------- polling ---------------- */
let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    if (watching.refresh) {
      try {
        const j = await api("status", {}, "GET");
        const run = (j.runs || []).find((r) => /collect\.yml$/.test(r.path) && new Date(r.created_at) >= watching.refresh - 120e3);
        if (run && run.status !== "completed") banner(`جارِ البحث في حراج… (${run.status === "queued" ? "في الانتظار" : "يعمل الآن"} منذ ${ago(run.created_at).replace("قبل ", "")})`);
        if (run && run.status === "completed") {
          watching.refresh = false; banner("");
          toast(run.conclusion === "success" ? "✓ اكتمل البحث وتحدّثت العروض" : "⚠️ انتهى البحث بخطأ — جرّب لاحقًا", run.conclusion === "success" ? "ok" : "err");
          await load();
        }
      } catch (e) { /* keep polling */ }
    }
    if (watching.sids.size || (watching.editAt && Date.now() - watching.editAt < 5 * 60e3)) await load();
    if (!watching.refresh && !watching.sids.size && !(watching.editAt && Date.now() - watching.editAt < 5 * 60e3)) {
      clearInterval(pollTimer); pollTimer = null;
    }
  }, 20000);
}
function checkWatches() {
  const subs = DB.submissions || {};
  for (const sid of [...watching.sids]) {
    const r = subs[sid]; if (!r) continue;
    watching.sids.delete(sid);
    if (r.error && !r.ids.length) toast(`⚠️ ${r.error}`, "err");
    else if (r.hidden && r.hidden.length && !r.ids.length) toast(`لم يُضف: ${r.hidden[0]}`, "err");
    else toast(`✓ أُضيف ${r.ids.length} عرض`, "ok");
  }
  if (watching.editAt && DB.updated_at && new Date(DB.updated_at) > watching.editAt) watching.editAt = 0;
}

/* ---------------- seller message ---------------- */
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

/* ---------------- events ---------------- */
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-msg],[data-edit],[data-like]"); if (!t) return;
  if (t.dataset.edit) return openEdit(t.dataset.edit);
  if (t.dataset.like) return toggleLike(t.dataset.like);
  const l = DB.listings.find((x) => x.id === t.dataset.msg);
  const txt = sellerMessage(l);
  $("#msg-text").value = txt;
  $("#msg-wa").href = `https://wa.me/?text=${encodeURIComponent(txt)}`;
  $("#msg-dlg").showModal();
});
document.addEventListener("change", (e) => {
  if (e.target.matches(".status-sel")) quickStatus(e.target.dataset.status, e.target.value);
});
$("#msg-copy").onclick = () => { navigator.clipboard?.writeText($("#msg-text").value); $("#msg-copy").textContent = "تم النسخ ✓"; };
$("#add-form").addEventListener("submit", submitAdd);
$("#edit-form").addEventListener("submit", submitEdit);
$("#like-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#like-dlg").close();
  await saveLike(liking, true, $("#like-note").value.trim());
});
document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = () => b.closest("dialog").close()));

load(true);
