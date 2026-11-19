const state = { offers: [], lastResult: null };
const form = document.querySelector('#campaign-form');
const offerIdInput = form.elements.offer_id;
const offerSearch = document.querySelector('#offer-search');
const suggestions = document.querySelector('#offer-suggestions');
const formError = document.querySelector('#form-error');
const submitButton = document.querySelector('#submit-button');
const status = document.querySelector('#connection-status');

function optionLabel(item) { return `${item.name || 'Без названия'} · #${item.id}`; }
function fillSelect(id, items, emptyText) {
  const select = document.querySelector(`#${id}`);
  select.innerHTML = `<option value="">${emptyText}</option>`;
  items.forEach((item) => { const option = document.createElement('option'); option.value = item.id; option.textContent = optionLabel(item); select.append(option); });
  if (items.length === 1) select.value = items[0].id;
}
function setError(message) { formError.textContent = message || ''; formError.hidden = !message; }
function updatePreview() {
  document.querySelector('#preview-name').textContent = form.elements.name.value.trim() || 'Без названия';
  const geo = form.elements.geo_code.value.trim().toUpperCase() || '—';
  document.querySelector('#preview-geo').textContent = geo;
  document.querySelector('#preview-filter').textContent = geo;
  document.querySelector('#preview-offer').textContent = offerIdInput.value || '—';
}
function showSuggestions() {
  const query = offerSearch.value.trim().toLowerCase();
  const items = state.offers.filter((offer) => optionLabel(offer).toLowerCase().includes(query)).slice(0, 8);
  suggestions.innerHTML = '';
  items.forEach((offer) => {
    const row = document.createElement('div'); row.className = 'suggestion';
    row.innerHTML = `<span class="suggestion-name">${escapeHtml(offer.name || 'Без названия')}</span><span class="suggestion-id">#${offer.id}</span>`;
    row.addEventListener('click', () => { offerIdInput.value = offer.id; offerSearch.value = optionLabel(offer); suggestions.hidden = true; updatePreview(); });
    suggestions.append(row);
  });
  suggestions.hidden = items.length === 0;
}
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
async function loadLookups() {
  try {
    const response = await fetch('/api/lookups'); const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Не удалось загрузить справочники');
    state.offers = data.offers || [];
    fillSelect('domain-select', data.domains || [], 'Выбери домен'); fillSelect('group-select', data.groups || [], 'Выбери группу'); fillSelect('source-select', data.traffic_sources || [], 'Выбери источник');
    status.innerHTML = '<span class="status-dot green"></span>Keitaro подключён';
  } catch (error) { status.innerHTML = '<span class="status-dot"></span>API не настроен'; setError(`Не удалось загрузить справочники: ${error.message}. Проверь KEITARO_API_KEY в .env.`); }
}
async function submit(event) {
  event.preventDefault(); setError(''); const body = Object.fromEntries(new FormData(form).entries());
  ['offer_id', 'domain_id', 'group_id', 'traffic_source_id'].forEach((key) => { if (body[key]) body[key] = Number(body[key]); }); body.geo_code = body.geo_code.trim().toUpperCase();
  submitButton.disabled = true; submitButton.querySelector('.button-label').hidden = true; submitButton.querySelector('.button-loader').hidden = false;
  try {
    const response = await fetch('/api/campaigns', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); const data = await response.json();
    if (!response.ok) {
      const details = data.errors
        ? `: ${typeof data.errors === 'string' ? data.errors : JSON.stringify(data.errors)}`
        : '';
      throw new Error(`${data.detail || 'Keitaro не принял запрос'}${details}`);
    }
    state.lastResult = data;
    document.querySelector('#success-title').textContent = data.campaign.name || body.name; document.querySelector('#success-description').textContent = `Создано 2 потока. ID кампании: ${data.campaign.id || '—'}.`; document.querySelector('#success-card').hidden = false; document.querySelector('#success-card').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) { setError(error.message); } finally { submitButton.disabled = false; submitButton.querySelector('.button-label').hidden = false; submitButton.querySelector('.button-loader').hidden = true; }
}
form.addEventListener('input', updatePreview); form.addEventListener('submit', submit); offerSearch.addEventListener('focus', showSuggestions); offerSearch.addEventListener('input', showSuggestions); document.addEventListener('click', (event) => { if (!event.target.closest('.autocomplete-wrap')) suggestions.hidden = true; });
document.querySelector('#copy-result').addEventListener('click', async () => { if (!state.lastResult) return; await navigator.clipboard.writeText(JSON.stringify(state.lastResult, null, 2)); document.querySelector('#copy-result').textContent = 'Скопировано'; setTimeout(() => { document.querySelector('#copy-result').textContent = 'Скопировать JSON'; }, 1400); });
updatePreview(); loadLookups();
