const state = { offers: [], lastResult: null, editor: { campaign: null, selectedOffer: null } };
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

const editorCampaignSelect = document.querySelector('#editor-campaign-select');
const editorCampaignId = document.querySelector('#editor-campaign-id');
const editorFetchButton = document.querySelector('#editor-fetch');
const editorOfferSearch = document.querySelector('#editor-offer-search');
const editorOfferSuggestions = document.querySelector('#editor-offer-suggestions');
const editorSelectedOffer = document.querySelector('#editor-selected-offer');
const editorMessage = document.querySelector('#editor-message');
const streamsList = document.querySelector('#streams-list');

function setEditorMessage(message, kind = 'error', action = null) {
  editorMessage.innerHTML = '';
  editorMessage.className = `editor-message${kind === 'success' ? ' success' : ''}`;
  if (message) {
    editorMessage.append(document.createTextNode(message));
    if (action) {
      const button = document.createElement('button');
      button.className = 'small-button warn-small editor-conflict';
      button.type = 'button'; button.textContent = action.label;
      button.addEventListener('click', action.handler);
      editorMessage.append(document.createElement('br'), button);
    }
    editorMessage.hidden = false;
  } else { editorMessage.hidden = true; }
}

async function editorRequest(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail || 'Запрос редактора не выполнен';
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    error.status = response.status; error.payload = data;
    throw error;
  }
  return data;
}

async function loadEditorCampaigns() {
  try {
    const data = await editorRequest('/api/editor/campaigns');
    const campaigns = data.campaigns || [];
    editorCampaignSelect.innerHTML = '<option value="">Выбери кампанию</option>';
    campaigns.forEach((campaign) => {
      const option = document.createElement('option');
      option.value = campaign.id; option.textContent = `${campaign.name || 'Без названия'} · #${campaign.id}`;
      editorCampaignSelect.append(option);
    });
  } catch (error) {
    editorCampaignSelect.innerHTML = '<option value="">Не удалось загрузить список</option>';
    setEditorMessage(`Не удалось загрузить кампании: ${error.message}`);
  }
}

function currentEditorCampaignId() {
  return Number(editorCampaignId.value || editorCampaignSelect.value || 0);
}

function setEditorCampaign(campaign) {
  state.editor.campaign = campaign;
  editorCampaignId.value = campaign.id || '';
  const option = [...editorCampaignSelect.options].find((item) => item.value === String(campaign.id));
  if (option) editorCampaignSelect.value = String(campaign.id);
  renderEditorStreams();
}

async function fetchEditorCampaign(discardPending = false) {
  const campaignId = currentEditorCampaignId();
  if (!campaignId) { setEditorMessage('Укажи ID кампании или выбери её из списка.'); return; }
  editorFetchButton.disabled = true; setEditorMessage('');
  try {
    const data = await editorRequest(`/api/editor/campaigns/${campaignId}/fetch`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ discard_pending: discardPending }),
    });
    setEditorCampaign(data); setEditorMessage('Потоки синхронизированы. Локальные изменения Keitaro не затронуты.', 'success');
  } catch (error) {
    if (error.status === 409) {
      setEditorMessage(error.message, 'error', { label: 'Сбросить черновик и повторить Fetch', handler: () => fetchEditorCampaign(true) });
    } else setEditorMessage(error.message);
  } finally { editorFetchButton.disabled = false; }
}

function replaceEditorStream(stream) {
  if (!state.editor.campaign) return;
  state.editor.campaign.streams = state.editor.campaign.streams.map((item) => item.id === stream.id ? stream : item);
  renderEditorStreams();
}

function streamViewUrl(streamId) {
  return `https://tlgk.host/admin/#/campaigns/${currentEditorCampaignId()}/streams/${streamId}`;
}

function renderEditorStreams() {
  const campaign = state.editor.campaign;
  if (!campaign) { streamsList.innerHTML = '<div class="empty-editor">Выбери кампанию и нажми Fetch Streams from KT.</div>'; return; }
  if (!campaign.streams || !campaign.streams.length) { streamsList.innerHTML = '<div class="empty-editor">В кампании нет потоков.</div>'; return; }
  streamsList.innerHTML = campaign.streams.map((stream) => {
    const pending = stream.has_pending_changes;
    const rows = stream.offers || [];
    const hasOffers = rows.length > 0;
    const offerRows = rows.map((offer) => {
      const removed = offer.status === 'removed';
      const pinned = offer.is_weight_pinned && !removed;
      return `<tr class="offer-row${removed ? ' removed' : ''}">
        <td class="offer-name">${escapeHtml(offer.name || `Оффер #${offer.offer_id}`)}<span class="offer-id">#${offer.offer_id}</span></td>
        <td>${removed ? '<span class="removed-label">Removed · 0%</span>' : `<span class="share-badge">${offer.share}%</span>`}</td>
        <td>—</td><td>—</td>
        <td><div class="stream-actions">
          ${removed ? `<button class="small-button primary-small" data-editor-action="bring-back" data-stream-id="${stream.id}" data-offer-id="${offer.offer_id}">Bring Back</button>` : `<button class="small-button" data-editor-action="remove" data-stream-id="${stream.id}" data-offer-id="${offer.offer_id}">Remove</button>`}
          ${!removed ? `<button class="small-button pin-button" data-editor-action="pin" data-pinned="${pinned ? 'false' : 'true'}" data-stream-id="${stream.id}" data-offer-id="${offer.offer_id}">${pinned ? 'Unpin' : 'Pin Weight'}</button>` : ''}
        </div></td>
      </tr>`;
    }).join('');
    const addButton = hasOffers ? `<button class="small-button primary-small" data-editor-action="add" data-stream-id="${stream.id}">Add</button>` : '<span class="stream-meta">Поток без офферов не изменяется</span>';
    return `<article class="stream-card${pending ? ' pending' : ''}">
      <div class="stream-card-header"><div><div class="stream-title"><span class="status-dot ${pending ? '' : 'green'}"></span>${escapeHtml(stream.name)} <span class="stream-meta">#${stream.id}</span></div><div class="stream-status${pending ? ' pending' : ''}">${pending ? 'Есть неопубликованные изменения' : 'Опубликовано'}</div></div>
        <div class="stream-actions"><a class="small-button" href="${streamViewUrl(stream.id)}" target="_blank" rel="noreferrer">View in KT</a>${addButton}<button class="small-button primary-small" data-editor-action="push" data-stream-id="${stream.id}" ${pending ? '' : 'disabled'}>Push to KT</button><button class="small-button" data-editor-action="cancel" data-stream-id="${stream.id}" ${pending ? '' : 'disabled'}>Cancel</button></div>
      </div>
      ${hasOffers ? `<div class="stream-table-wrap"><table class="stream-table"><thead><tr><th>Offer</th><th>Share</th><th>Stats</th><th>Trends</th><th>Actions</th></tr></thead><tbody>${offerRows}</tbody></table></div>` : '<div class="no-offers">Поток импортирован и будет сохранён без изменений. Фильтры и редирект не разбираются и не перезаписываются.</div>'}
    </article>`;
  }).join('');
}

async function editorAction(action, streamId, offerId, pinned) {
  setEditorMessage('');
  const routes = {
    remove: `/api/editor/streams/${streamId}/offers/${offerId}/remove`,
    'bring-back': `/api/editor/streams/${streamId}/offers/${offerId}/bring-back`,
    pin: `/api/editor/streams/${streamId}/offers/${offerId}/pin`,
    cancel: `/api/editor/streams/${streamId}/cancel`,
    push: `/api/editor/streams/${streamId}/push`,
  };
  try {
    let options = { method: 'POST' };
    if (action === 'pin') { options.headers = { 'Content-Type': 'application/json' }; options.body = JSON.stringify({ pinned }); }
    const data = await editorRequest(routes[action], options);
    replaceEditorStream(data.stream);
    setEditorMessage(action === 'push' ? 'Изменения опубликованы в Keitaro.' : 'Локальный черновик обновлён.', 'success');
  } catch (error) { setEditorMessage(error.message); }
}

async function addEditorOffer(streamId) {
  const offer = state.editor.selectedOffer;
  if (!offer) { setEditorMessage('Сначала найди и выбери оффер для добавления.'); return; }
  try {
    const data = await editorRequest(`/api/editor/streams/${streamId}/offers`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ offer_id: offer.id }),
    });
    replaceEditorStream(data.stream); setEditorMessage('Оффер добавлен только в локальный черновик.', 'success');
  } catch (error) { setEditorMessage(error.message); }
}

streamsList.addEventListener('click', (event) => {
  const button = event.target.closest('[data-editor-action]'); if (!button) return;
  const action = button.dataset.editorAction; const streamId = Number(button.dataset.streamId); const offerId = Number(button.dataset.offerId);
  if (action === 'add') addEditorOffer(streamId); else editorAction(action, streamId, offerId, button.dataset.pinned === 'true');
});
editorFetchButton.addEventListener('click', () => fetchEditorCampaign(false));
editorCampaignSelect.addEventListener('change', () => { editorCampaignId.value = editorCampaignSelect.value; });
editorOfferSearch.addEventListener('input', async () => {
  const query = editorOfferSearch.value.trim();
  if (!query) { editorOfferSuggestions.hidden = true; return; }
  try {
    const data = await editorRequest(`/api/editor/offers?query=${encodeURIComponent(query)}`);
    editorOfferSuggestions.innerHTML = (data.offers || []).map((offer) => `<div class="suggestion" data-offer-id="${offer.id}"><span class="suggestion-name">${escapeHtml(offer.name || 'Без названия')}</span><span class="suggestion-id">#${offer.id}</span></div>`).join('');
    editorOfferSuggestions.hidden = !(data.offers || []).length;
  } catch (error) { setEditorMessage(error.message); }
});
editorOfferSuggestions.addEventListener('click', (event) => {
  const row = event.target.closest('[data-offer-id]'); if (!row) return;
  const offerId = Number(row.dataset.offerId); const label = row.querySelector('.suggestion-name').textContent;
  state.editor.selectedOffer = { id: offerId, name: label }; editorOfferSearch.value = `${label} · #${offerId}`; editorSelectedOffer.textContent = `Выбран: ${label} · #${offerId}`; editorOfferSuggestions.hidden = true;
});
document.addEventListener('click', (event) => { if (!event.target.closest('.editor-offer-search')) editorOfferSuggestions.hidden = true; });
updatePreview(); loadLookups(); loadEditorCampaigns();
