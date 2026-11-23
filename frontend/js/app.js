import { iconFor } from './icons.js';

const STATUS_LABEL = {
  idle: 'En attente',
  loading: 'Vérification…',
  available: 'Libre',
  taken: 'Pris',
  uncertain: 'Incertain',
  invalid: 'Invalide ici',
  unverifiable: 'Non vérifiable',
};

const RELIABILITY_LABEL = {
  high: 'Fiabilité haute',
  medium: 'Fiabilité moyenne',
  low: 'Fiabilité faible',
};

const METHOD_LABEL = {
  helix_api: 'API officielle',
  http_probe: 'Sonde du profil',
  none: 'Aucune méthode fiable',
};

const $ = (id) => document.getElementById(id);
const els = {
  form: $('search'),
  input: $('username'),
  button: $('submit'),
  error: $('form-error'),
  summary: $('summary'),
  grid: $('grid'),
  template: $('card-template'),
};

const cards = new Map(); // platform id -> { el, platform }
let inflight = null;

function normalize(raw) {
  let name = raw.trim();
  if (name.startsWith('@')) name = name.slice(1).trim();
  return name;
}

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = !message;
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const detail = body && body.detail;
    const message = typeof detail === 'string' ? detail : `Erreur serveur (HTTP ${res.status}).`;
    throw new Error(message);
  }
  return body;
}

// ---------------------------------------------------------------- cards

function createCard(platform) {
  const el = els.template.content.firstElementChild.cloneNode(true);
  el.dataset.platform = platform.id;
  el.querySelector('.card__logo').append(iconFor(platform.id, platform.label));
  el.querySelector('.card__name').textContent = platform.label;
  els.grid.append(el);
  cards.set(platform.id, { el, platform });
  setIdle(platform.id);
}

function setCard(id, state, { detail = '', url = null, reliability = undefined } = {}) {
  const card = cards.get(id);
  if (!card) return;
  const { el, platform } = card;
  if (reliability === undefined) reliability = platform.reliability;
  el.dataset.state = state;
  el.querySelector('.card__status-label').textContent = STATUS_LABEL[state] || state;
  const detailEl = el.querySelector('.card__detail');
  detailEl.textContent = detail;
  detailEl.title = detail; // full text on hover if clamped to 3 lines
  // Reliability only means something for an actual check, not for a rule violation.
  const showReliability = reliability && state !== 'invalid' && state !== 'unverifiable';
  el.querySelector('.card__reliability').textContent = showReliability ? RELIABILITY_LABEL[reliability] || '' : '';
  const link = el.querySelector('.card__link');
  link.hidden = !url;
  if (url) link.href = url;
  else link.removeAttribute('href');
}

function setIdle(id) {
  const { platform } = cards.get(id);
  const detail = platform.configured
    ? METHOD_LABEL[platform.method] || ''
    : 'Clés API manquantes : voir .env.example';
  setCard(id, 'idle', { detail, reliability: platform.reliability });
}

function applyResult(result) {
  if (!cards.has(result.platform)) {
    // A checker the page didn't know about at load time: add its card.
    createCard({ id: result.platform, label: result.label, reliability: result.reliability, method: result.method, configured: true });
  }
  setCard(result.platform, result.status, {
    detail: result.detail || '',
    url: result.url,
    reliability: result.reliability,
  });
}

function renderSummary(summary, username, elapsedMs) {
  const { available, checkable } = summary;
  const word = checkable > 1 ? 'plateformes' : 'plateforme';
  els.summary.innerHTML = '';
  const strong = document.createElement('strong');
  strong.textContent = `@${username}`;
  els.summary.append(
    strong,
    ` est libre sur ${available}/${checkable} ${word}`,
    elapsedMs != null ? ` · ${elapsedMs} ms` : '',
  );
  els.summary.dataset.tone = available === checkable && checkable > 0 ? 'good' : available === 0 ? 'bad' : 'mixed';
}

// ---------------------------------------------------------------- search

async function onSubmit(event) {
  event.preventDefault();
  const username = normalize(els.input.value);
  if (!username) {
    showError('Saisis un pseudo.');
    els.input.focus();
    return;
  }
  showError('');

  inflight?.abort();
  const controller = new AbortController();
  inflight = controller;

  els.form.dataset.busy = 'true';
  els.button.disabled = true;
  els.grid.setAttribute('aria-busy', 'true');
  els.summary.textContent = `Vérification de @${username}…`;
  delete els.summary.dataset.tone;
  for (const id of cards.keys()) setCard(id, 'loading');

  try {
    const data = await fetchJSON(`/check/${encodeURIComponent(username)}`, { signal: controller.signal });
    for (const result of data.results) applyResult(result);
    renderSummary(data.summary, data.username, data.elapsed_ms);
  } catch (err) {
    if (err.name === 'AbortError') return;
    showError(err.message || 'Impossible de contacter le serveur Claimd.');
    els.summary.innerHTML = '&nbsp;';
    for (const id of cards.keys()) setIdle(id);
  } finally {
    if (inflight === controller) {
      inflight = null;
      delete els.form.dataset.busy;
      els.button.disabled = false;
      els.grid.setAttribute('aria-busy', 'false');
    }
  }
}

async function init() {
  els.form.addEventListener('submit', onSubmit);
  els.input.addEventListener('input', () => {
    showError('');
    // The field already shows an "@" prefix: drop one typed or pasted in front.
    if (els.input.value.startsWith('@')) els.input.value = els.input.value.replace(/^@+\s*/, '');
  });
  try {
    const platforms = await fetchJSON('/platforms');
    platforms.forEach(createCard);
  } catch (err) {
    showError(`Impossible de charger les plateformes : ${err.message}`);
  }
}

init();
