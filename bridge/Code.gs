/**
 * جسر رادار سيارة البر — Google Apps Script (مجاني)
 * يستقبل طلبات الموقع (إضافة رابط، تعديل عرض، بحث الآن) وينفذها على GitHub
 * باستخدام مفتاح GitHub محفوظ هنا بشكل خاص (لا يظهر في الموقع).
 *
 * الإعداد: Project Settings → Script properties:
 *   GITHUB_TOKEN = مفتاح GitHub (fine-grained, Contents + Actions: Read and write)
 *   EDIT_CODE    = (اختياري) رمز يطلبه الموقع قبل أي تعديل
 */
const REPO = 'salotaibi511/Offroad-finder';
const BRANCH = 'main';
const EDITS_PATH = 'docs/data/edits.json';
const DATA_PATH = 'docs/data/listings.json';
const STATUSES = ['جديد', 'تواصلت', 'بانتظار رد', 'معاينة', 'فحص', 'تفاوض', 'مستبعد يدويًا', 'تم الشراء', 'مباع'];
const EDITABLE = ['title', 'price', 'year', 'mileage_km', 'city', 'is_4x4', 'transmission', 'fuel', 'model_key'];

function doGet(e) { return handle_((e && e.parameter) || {}); }
function doPost(e) {
  let p = {};
  try { p = JSON.parse(e.postData.contents); } catch (_) {}
  return handle_(p);
}

function handle_(p) {
  try {
    const props = PropertiesService.getScriptProperties();
    const writes = ['add', 'edit', 'refresh', 'like'];
    if (writes.indexOf(p.action) >= 0) {
      const code = props.getProperty('EDIT_CODE');
      if (code && String(p.code || '') !== code) return out_({ ok: false, error: 'رمز التعديل غير صحيح', need_code: true });
    }
    switch (p.action) {
      case 'ping': return out_({ ok: true, need_code: !!props.getProperty('EDIT_CODE') });
      case 'data': return out_({ ok: true, data: JSON.parse(gh_('GET', `/contents/${DATA_PATH}?ref=${BRANCH}`, null, true) || '{}'), edits: readEdits_().data });
      case 'edits': return out_({ ok: true, edits: readEdits_().data });
      case 'status': return out_({ ok: true, runs: runs_() });
      case 'add': return out_(add_(p));
      case 'edit': return out_(edit_(p));
      case 'refresh': dispatch_('collect.yml'); return out_({ ok: true });
      case 'like': return out_(like_(p));
      default: return out_({ ok: false, error: 'طلب غير معروف' });
    }
  } catch (err) {
    return out_({ ok: false, error: String(err && err.message || err) });
  }
}

/* ---------- actions ---------- */
function add_(p) {
  const urls = String(p.urls || p.url || '').match(/https?:\/\/[^\s<>"']+/g) || [];
  if (!urls.length) return { ok: false, error: 'لم أجد رابطًا صحيحًا' };
  const by = clean_(p.by, 40) || 'زائر';
  const note = clean_(p.note, 500);
  const added = [];
  withEdits_(function (d) {
    urls.slice(0, 10).forEach(function (u) {
      const sid = 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      d.pending.push({ sid: sid, url: u.slice(0, 500), by: by, note: note, at: now_() });
      added.push({ sid: sid, url: u });
    });
    d.pending = d.pending.slice(-300);
  }, 'إضافة رابط من الموقع');
  dispatch_('api.yml');
  return { ok: true, added: added };
}

function edit_(p) {
  const id = clean_(p.id, 80);
  if (!id) return { ok: false, error: 'رقم العرض مفقود' };
  const by = clean_(p.by, 40) || 'زائر';
  let result;
  withEdits_(function (d) {
    const ov = d.overrides[id] || {};
    const f = p.fields || {};
    ov.fields = ov.fields || {};
    EDITABLE.forEach(function (k) {
      if (!(k in f)) return;
      let v = f[k];
      if (v === '' || v === null) { delete ov.fields[k]; return; }
      if (['price', 'year', 'mileage_km'].indexOf(k) >= 0) v = Number(String(v).replace(/[^\d.]/g, '')) || null;
      if (k === 'is_4x4') v = v === true || v === 'true' ? true : v === false || v === 'false' ? false : null;
      if (typeof v === 'string') v = clean_(v, 120);
      if (v !== null) ov.fields[k] = v; else delete ov.fields[k];
    });
    if (p.status) {
      if (STATUSES.indexOf(p.status) < 0) throw new Error('حالة غير معروفة');
      ov.status = p.status;
    }
    if (p.note) {
      ov.notes = (ov.notes || []).concat([{ by: by, date: now_().slice(0, 10), text: clean_(p.note, 500) }]).slice(-30);
    }
    if ('hidden' in p) ov.hidden = !!p.hidden;
    ov.by = by; ov.at = now_();
    d.overrides[id] = ov;
    result = ov;
  }, 'تعديل عرض من الموقع');
  dispatch_('api.yml');
  return { ok: true, override: result };
}

/** إعجاب/إلغاء إعجاب مع ملاحظة اختيارية — لا يحتاج إعادة تقييم فلا يشغّل GitHub Actions */
function like_(p) {
  const id = clean_(p.id, 80);
  const by = clean_(p.by, 40);
  if (!id) return { ok: false, error: 'رقم العرض مفقود' };
  if (!by || by === 'زائر') return { ok: false, error: 'اكتب اسمك أولًا' };
  let likes;
  withEdits_(function (d) {
    const ov = d.overrides[id] || {};
    ov.likes = ov.likes || {};
    if (p.liked === false || p.liked === 'false') delete ov.likes[by];
    else ov.likes[by] = { at: now_(), note: clean_(p.note, 300) };
    d.overrides[id] = ov;
    likes = ov.likes;
  }, (p.liked === false ? 'إلغاء إعجاب' : 'إعجاب') + ' من الموقع');
  return { ok: true, likes: likes };
}

function runs_() {
  const r = JSON.parse(gh_('GET', '/actions/runs?per_page=8&branch=' + BRANCH));
  return (r.workflow_runs || []).map(function (x) {
    return { name: x.name, path: x.path, status: x.status, conclusion: x.conclusion, created_at: x.created_at, updated_at: x.updated_at };
  });
}

/* ---------- GitHub helpers ---------- */
function gh_(method, path, body, raw) {
  const token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('GITHUB_TOKEN غير مضاف في إعدادات السكربت');
  const opts = {
    method: method,
    muteHttpExceptions: true,
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: raw ? 'application/vnd.github.raw+json' : 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    }
  };
  if (body) { opts.contentType = 'application/json'; opts.payload = JSON.stringify(body); }
  const res = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + path, opts);
  const code = res.getResponseCode();
  if (code === 404 && method === 'GET') return null;
  if (code >= 300) {
    const e = new Error('GitHub ' + code + ': ' + res.getContentText().slice(0, 200));
    e.code = code;
    throw e;
  }
  return res.getContentText('UTF-8');
}

function readEdits_() {
  const txt = gh_('GET', `/contents/${EDITS_PATH}?ref=${BRANCH}`);
  if (!txt) return { data: { pending: [], overrides: {} }, sha: null };
  const j = JSON.parse(txt);
  const content = Utilities.newBlob(Utilities.base64Decode(j.content.replace(/\n/g, ''))).getDataAsString('UTF-8');
  const data = JSON.parse(content || '{}');
  data.pending = data.pending || [];
  data.overrides = data.overrides || {};
  return { data: data, sha: j.sha };
}

function withEdits_(mutate, message) {
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    for (let attempt = 0; attempt < 4; attempt++) {
      const cur = readEdits_();
      mutate(cur.data);
      const body = {
        message: message,
        branch: BRANCH,
        content: Utilities.base64Encode(JSON.stringify(cur.data, null, 1), Utilities.Charset.UTF_8),
        committer: { name: 'offroad-site', email: 'offroad-site@users.noreply.github.com' }
      };
      if (cur.sha) body.sha = cur.sha;
      try {
        gh_('PUT', `/contents/${EDITS_PATH}`, body);
        return;
      } catch (e) {
        if (e.code !== 409 && e.code !== 422) throw e;  // sha conflict → retry
        Utilities.sleep(800);
      }
    }
    throw new Error('تعذر الحفظ، حاول مرة ثانية');
  } finally {
    lock.releaseLock();
  }
}

function dispatch_(workflow) {
  gh_('POST', `/actions/workflows/${workflow}/dispatches`, { ref: BRANCH });
}

/* ---------- utils ---------- */
function clean_(s, n) { return String(s == null ? '' : s).replace(/[<>]/g, '').trim().slice(0, n); }
function now_() { return new Date().toISOString().replace(/\.\d+Z$/, 'Z'); }
function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** جدولة احتياطية: GitHub يؤخر الجدولة أحيانًا، فهذا يشغّل البحث كل ساعة بشكل مضمون */
function hourly() { dispatch_('collect.yml'); }

/** شغّل هذه الدالة مرة واحدة من المحرر: تختبر المفتاح وتفعّل التشغيل كل ساعة */
function setup() {
  Logger.log('GitHub: ' + JSON.parse(gh_('GET', '')).full_name + ' ✓');
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('hourly').timeBased().everyHours(1).create();
  Logger.log('تم تفعيل البحث كل ساعة ✓');
}

function test() {
  Logger.log(gh_('GET', ''));
  Logger.log(JSON.stringify(readEdits_().data).slice(0, 200));
}
