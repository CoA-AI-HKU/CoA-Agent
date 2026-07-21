const select = document.querySelector('#patient-select');
const daysSelect = document.querySelector('#days-select');
const statusEl = document.querySelector('#dashboard-status');
let accounts = [];
const urlToken = new URLSearchParams(location.search).get('access_token');
if (urlToken) {
  sessionStorage.setItem('coa-dashboard-token', urlToken);
  history.replaceState({}, '', location.pathname);
}
const accessToken = sessionStorage.getItem('coa-dashboard-token') || '';

function valueOrNA(value, suffix = '') { return value == null ? 'N/A' : `${Number(value).toFixed(1)}${suffix}`; }
function renderBars(container, items, valueKey, labelKey) {
  container.replaceChildren();
  if (!items?.length) { container.textContent = window.t('noData'); return; }
  const max = Math.max(1, ...items.map(x => Number(x[valueKey]) || 0));
  items.forEach(item => {
    const wrap = document.createElement('div'); wrap.className = 'bar-wrap';
    const bar = document.createElement('div'); bar.className = 'bar'; bar.style.height = `${Math.max(8, (Number(item[valueKey]) || 0) / max * 150)}px`;
    bar.title = `${item[labelKey]}: ${item[valueKey]}`;
    const label = document.createElement('span'); label.textContent = String(item[labelKey]).slice(5);
    wrap.append(bar, label); container.append(wrap);
  });
}
function renderHistory(id, items) {
  const normalized = (items || []).map(x => ({...x, label: String(x.timestamp || '').slice(0, 10)}));
  renderBars(document.querySelector(id), normalized, 'score', 'label');
}
function render(payload) {
  const m = payload.metrics; const s = payload.summary;
  const account = accounts.find(x => x.user_id === payload.user_id);
  document.querySelector('#patient-heading').textContent = `${account?.display_name || payload.user_id} · ${payload.days} ${window.t('days')}`;
  document.querySelector('[data-metric="avg_mood"]').textContent = valueOrNA(m.avg_mood);
  document.querySelector('[data-metric="avg_cognitive"]').textContent = valueOrNA(m.avg_cognitive);
  document.querySelector('[data-metric="total_interactions"]').textContent = m.total_interactions ?? 0;
  document.querySelector('[data-metric="medication_adherence"]').textContent = m.medication_adherence == null ? 'N/A' : `${Math.round(m.medication_adherence * 100)}%`;
  document.querySelectorAll('[data-summary]').forEach(el => { el.textContent = s[el.dataset.summary] || ''; });
  document.querySelectorAll('[data-screening]').forEach(el => {
    const value=m[el.dataset.screening];
    const labels={normal:'未見即時關注',no_immediate_concern:'未見即時關注',monitor:'建議留意',follow_up_suggested:'建議跟進',urgent_safety:'安全問題需即時處理'};
    el.textContent=el.dataset.screening==='latest_risk_flag'?(labels[value]||'—'):(value||'—');
  });
  renderBars(document.querySelector('#activity-bars'), payload.daily_activity.slice(-7), 'count', 'date');
  renderHistory('#mood-chart', m.mood_history); renderHistory('#cognitive-chart', m.cognitive_history);
  const alerts = document.querySelector('#alert-list'); alerts.replaceChildren();
  (payload.alerts || []).forEach(a => { const el = document.createElement('div'); el.className = `alert ${a.level}`; el.textContent = a.message; alerts.append(el); });
  const intents = document.querySelector('#intent-list'); intents.replaceChildren();
  Object.entries(m.intent_counts || {}).sort((a,b) => b[1]-a[1]).forEach(([name,count]) => { const el=document.createElement('div'); el.innerHTML=`<span>${name.replaceAll('_',' ')}</span><strong>${count}</strong>`; intents.append(el); });
  if (!intents.children.length) intents.textContent = window.t('noData');
  statusEl.textContent = '';
}
async function loadDashboard() {
  if (!select.value) return;
  statusEl.textContent = window.t('loading');
  try { const r = await fetch(`/api/dashboard?user_id=${encodeURIComponent(select.value)}&days=${daysSelect.value}&access_token=${encodeURIComponent(accessToken)}`); if(!r.ok) throw new Error(); render(await r.json()); }
  catch { statusEl.textContent = window.t('serverRequired'); }
}
async function start() {
  document.querySelector('#today').textContent = new Intl.DateTimeFormat(window.currentLang(), {dateStyle:'long'}).format(new Date());
  if (!accessToken) { statusEl.textContent = window.t('dashboardAccessRequired'); return; }
  try {
    const r = await fetch(`/api/users?access_token=${encodeURIComponent(accessToken)}`); if(!r.ok) throw new Error(); accounts = (await r.json()).users || [];
    select.replaceChildren(); accounts.forEach(u => { const o=document.createElement('option'); o.value=u.user_id; o.textContent=`${u.display_name} · ${u.user_id}`; select.append(o); });
    if (!accounts.length) { statusEl.textContent=window.t('noUsers'); return; }
    select.disabled=false; loadDashboard();
  } catch { statusEl.textContent=window.t('dashboardAccessRequired'); }
}
select.addEventListener('change', loadDashboard); daysSelect.addEventListener('change', loadDashboard);
window.addEventListener('languagechange', () => { window.applyTranslations(); document.querySelector('#today').textContent = new Intl.DateTimeFormat(window.currentLang(), {dateStyle:'long'}).format(new Date()); if(select.value) loadDashboard(); });
start();
