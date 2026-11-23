import { ApiError, getHealth, getPlatforms, streamCheck } from './api.js';
import { brandIcon, infoIcon, statusIcon } from './icons.js';
import * as motion from './motion.js';
import { initTooltips } from './tooltip.js';

// ---------------------------------------------------------------- copy

const STATUS_LABEL = {
  idle: 'Prêt',
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
  none: 'Aucune méthode légitime',
};

const LINK_LABEL = {
  available: 'Profil ↗',
  taken: 'Profil ↗',
  uncertain: 'Vérifier ↗',
};

// ---------------------------------------------------------------- DOM

const $ = (id) => document.getElementById(id);
const els = {
  form: $('search'),
  input: $('username'),
  error: $('form-error'),
  summary: $('summary'),
  summaryText: $('summary-text'),
  summaryTime: $('summary-time'),
  segments: $('segments'),
  copy: $('copy'),
  grid: $('grid'),
  extras: $('extras'),
  pill: $('server-pill'),
  cardTemplate: $('card-template'),
  miniTemplate: $('mini-template'),
};

const state = {
  platforms: new Map(), // id -> platform info
  views: new Map(), // id -> { el, kind: 'card' | 'mini', seg? }
  run: 0, // increments on every search; stale callbacks compare against it
  controller: null,
  revealAt: 0,
  chain: Promise.resolve(),
  username: '',
};

// ---------------------------------------------------------------- helpers

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function normalize(raw) {
  let name = raw.trim();
  if (name.startsWith('@')) name = name.slice(1).trim();
  return name;
}

function validate(name) {
  if (!name) return 'Saisis un pseudo.';
  if (/^\.+$/.test(name)) return "Ce pseudo n'est valide sur aucune plateforme.";
  if (/\s/.test(name)) return "Les pseudos ne contiennent pas d'espace.";
  return '';
}

function formatMs(ms) {
  if (!ms) return ''; // instant local answers (missing keys, invalid name) need no timing
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1).replace('.', ',')} s`;
}

function showError(message) {
  els.error.textContent = message || '';
}

// ---------------------------------------------------------------- views

function createCard(platform, index) {
  const el = els.cardTemplate.content.firstElementChild.cloneNode(true);
  el.dataset.platform = platform.id;
  el.style.setProperty('--i', index);
  el.querySelector('.card__logo').append(brandIcon(platform.id, platform.label));
  el.querySelector('.card__icon').append(statusIcon());
  el.querySelector('.card__name').textContent = platform.label;
  el.querySelector('.card__method').textContent = METHOD_LABEL[platform.method] || platform.method;
  const reliability = el.querySelector('.reliability');
  reliability.dataset.tipTitle = `${platform.label} · comment c'est vérifié`;
  reliability.dataset.tip = platform.note || '';

  // Cursor spotlight
  el.addEventListener('pointermove', (event) => {
    const rect = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${event.clientX - rect.left}px`);
    el.style.setProperty('--my', `${event.clientY - rect.top}px`);
  });

  els.grid.append(el);
  return el;
}

function createMini(platform) {
  const el = els.miniTemplate.content.firstElementChild.cloneNode(true);
  el.dataset.platform = platform.id;
  el.querySelector('.mini__logo').append(brandIcon(platform.id, platform.label));
  el.querySelector('.mini__name').textContent = platform.label;
  const info = el.querySelector('.mini__info');
  info.append(infoIcon());
  info.setAttribute('aria-label', `Pourquoi ${platform.label} n'est pas vérifiable`);
  info.dataset.tipTitle = `Pourquoi ${platform.label} n'est pas vérifié`;
  info.dataset.tip = platform.note || '';
  els.extras.append(el);
  return el;
}

function createSegment(platform, index) {
  const seg = document.createElement('span');
  seg.className = 'seg';
  seg.dataset.platform = platform.id;
  seg.dataset.state = 'idle';
  seg.style.setProperty('--i', index);
  const fill = document.createElement('span');
  fill.className = 'seg__fill';
  seg.append(fill);
  els.segments.append(seg);
  return seg;
}

function addPlatform(platform) {
  state.platforms.set(platform.id, platform);
  if (platform.verifiable) {
    const index = [...state.views.values()].filter((v) => v.kind === 'card').length;
    const view = { kind: 'card', el: createCard(platform, index), seg: createSegment(platform, index) };
    state.views.set(platform.id, view);
  } else {
    state.views.set(platform.id, { kind: 'mini', el: createMini(platform) });
  }
  paintIdle(platform.id);
  return state.views.get(platform.id);
}

function paint(id, status, { detail = '', url = null, reliability, elapsed = null } = {}) {
  const view = state.views.get(id);
  if (!view) return;
  const platform = state.platforms.get(id);
  const { el } = view;
  el.dataset.state = status;

  if (view.kind === 'mini') {
    el.querySelector('.mini__pill').textContent = STATUS_LABEL[status] || status;
    el.querySelector('.mini__detail').textContent = detail;
    el.querySelector('.mini__detail').title = detail;
    return;
  }

  el.querySelector('.card__label').textContent = STATUS_LABEL[status] || status;
  const detailEl = el.querySelector('.card__detail');
  detailEl.textContent = detail;
  detailEl.title = detail; // full text on hover if clamped to 3 lines
  el.querySelector('.card__time').textContent = formatMs(elapsed);

  const level = reliability || platform.reliability;
  const rel = el.querySelector('.reliability');
  rel.dataset.level = level;
  rel.querySelector('.reliability__label').textContent = RELIABILITY_LABEL[level] || '';
  rel.setAttribute('aria-label', `${RELIABILITY_LABEL[level] || ''}. Comment ${platform.label} est vérifié`);

  const link = el.querySelector('.card__link');
  link.hidden = !url;
  if (url) {
    link.href = url;
    link.textContent = LINK_LABEL[status] || 'Profil ↗';
  } else {
    link.removeAttribute('href');
  }

  if (view.seg) view.seg.dataset.state = status;
}

function paintIdle(id) {
  const platform = state.platforms.get(id);
  if (!platform.verifiable) {
    paint(id, 'unverifiable', { detail: "Pas d'API publique : rien n'est envoyé à Google." });
    return;
  }
  const detail = platform.configured ? platform.rules || '' : 'Clés API manquantes : voir le README pour les ajouter.';
  paint(id, 'idle', { detail });
}

// ---------------------------------------------------------------- summary

function summaryIdle() {
  els.summary.dataset.state = 'idle';
  delete els.summary.dataset.tone;
  const hint = document.createElement('span');
  hint.className = 'summary__hint';
  const kbd = document.createElement('kbd');
  kbd.textContent = '/';
  hint.append('Tape un pseudo, puis Entrée.');
  if (window.matchMedia('(hover: hover)').matches) hint.append(' Raccourci ', kbd, ' pour y revenir.');
  els.summaryText.replaceChildren(hint);
  els.summaryTime.textContent = '';
}

function summaryLoading(username) {
  els.summary.dataset.state = 'loading';
  delete els.summary.dataset.tone;
  const strong = document.createElement('strong');
  strong.textContent = `@${username}`;
  els.summaryText.replaceChildren('Vérification de ', strong, '…');
  els.summaryTime.textContent = '';
  els.copy.removeAttribute('data-copied');
  els.copy.querySelector('.copy__label').textContent = 'Copier';
}

function summaryDone({ username, summary, elapsed_ms: elapsed }) {
  const { available, checkable, taken } = summary;
  els.summary.dataset.state = 'done';
  els.summary.dataset.tone =
    checkable > 0 && available === checkable ? 'good' : available > 0 ? 'mixed' : taken > 0 ? 'bad' : 'none';

  const strong = document.createElement('strong');
  strong.textContent = `@${username}`;
  const count = document.createElement('span');
  count.className = 'summary__count';
  count.textContent = String(available);
  const word = checkable > 1 ? 'plateformes' : 'plateforme';
  els.summaryText.replaceChildren(strong, ' est libre sur ', count, `/${checkable} ${word}`);
  els.summaryTime.textContent = `en ${formatMs(elapsed)}`;
  els.copy.setAttribute('aria-label', `Copier « ${username} »`);
  motion.summaryIn(els.summaryText, count, available);
}

// ---------------------------------------------------------------- search

function enqueue(run, task, delay = 0) {
  // Reveals are serialised and spaced out, so cards land one by one.
  state.chain = state.chain.then(async () => {
    if (run !== state.run) return;
    const wait = state.revealAt + delay - performance.now();
    if (wait > 0) await sleep(wait);
    if (run !== state.run) return;
    task();
    state.revealAt = performance.now() + motion.pacing().gap;
  });
}

function revealResult(result) {
  let view = state.views.get(result.platform);
  if (!view) {
    // A checker the page did not know about when it loaded.
    view = addPlatform({
      id: result.platform,
      label: result.label,
      method: result.method,
      reliability: result.reliability,
      verifiable: result.status !== 'unverifiable',
      configured: true,
    });
  }
  motion.settle(view.el);
  paint(result.platform, result.status, {
    detail: result.detail || '',
    url: result.url,
    reliability: result.reliability,
    elapsed: result.elapsed_ms,
  });
  if (view.kind === 'mini') {
    motion.miniReveal(view.el);
  } else {
    motion.reveal(view.el, result.status);
    if (view.seg) motion.segment(view.seg);
  }
}

function setBusy(busy) {
  if (busy) els.form.dataset.busy = '';
  else delete els.form.dataset.busy;
  els.form.setAttribute('aria-busy', String(busy));
  els.grid.setAttribute('aria-busy', String(busy));
}

async function runSearch(raw) {
  const username = normalize(raw);
  const problem = validate(username);
  if (problem) {
    showError(problem);
    motion.shake(els.form);
    els.input.focus();
    return;
  }
  showError('');

  state.controller?.abort();
  const controller = new AbortController();
  state.controller = controller;
  const run = ++state.run;
  state.chain = Promise.resolve();
  state.revealAt = performance.now() + motion.pacing().minLoading;
  state.username = username;

  const url = new URL(window.location.href);
  url.searchParams.set('u', username);
  window.history.replaceState(null, '', url);

  setBusy(true);
  summaryLoading(username);
  motion.finishEntrance();
  const cards = [];
  for (const [id, view] of state.views) {
    motion.settle(view.el);
    paint(id, 'loading');
    if (view.seg) view.seg.dataset.state = 'loading';
    if (view.kind === 'card') cards.push(view.el);
  }
  motion.toLoading(cards);

  let finished = false;
  try {
    await streamCheck(username, {
      signal: controller.signal,
      onEvent(event) {
        if (run !== state.run) return;
        if (event.type === 'result') enqueue(run, () => revealResult(event.result));
        if (event.type === 'done') {
          finished = true;
          enqueue(run, () => summaryDone(event), motion.pacing().summaryDelay);
        }
      },
    });
    await state.chain;
    if (!finished && run === state.run) throw new ApiError('La vérification a été interrompue. Réessaie.');
  } catch (err) {
    if (err.name === 'AbortError' || run !== state.run) return;
    showError(err instanceof ApiError ? err.message : 'Réponse inattendue du serveur Claimd.');
    motion.shake(els.form);
    for (const [id, view] of state.views) {
      if (view.el.dataset.state === 'loading') {
        paintIdle(id);
        if (view.seg) view.seg.dataset.state = 'idle';
      }
    }
    summaryIdle();
  } finally {
    if (run === state.run) setBusy(false);
  }
}

// ---------------------------------------------------------------- copy

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Clipboard API needs a secure context (fine on localhost, not on plain-HTTP servers).
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
    document.body.append(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}

let copyTimer = 0;
async function onCopy() {
  if (!state.username) return;
  const ok = await copyText(state.username);
  const label = els.copy.querySelector('.copy__label');
  clearTimeout(copyTimer);
  if (ok) {
    els.copy.dataset.copied = '';
    label.textContent = 'Copié';
    motion.copied(els.copy);
  } else {
    label.textContent = 'Échec';
  }
  copyTimer = setTimeout(() => {
    els.copy.removeAttribute('data-copied');
    label.textContent = 'Copier';
  }, 1800);
}

// ---------------------------------------------------------------- boot

async function init() {
  motion.intro();
  initTooltips($('tooltip'));
  summaryIdle();

  els.form.addEventListener('submit', (event) => {
    event.preventDefault();
    runSearch(els.input.value);
  });
  els.input.addEventListener('input', () => {
    showError('');
    // The field already shows an "@" prefix: drop one typed or pasted in front.
    if (els.input.value.startsWith('@')) els.input.value = els.input.value.replace(/^@+\s*/, '');
  });
  els.input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && els.input.value) {
      els.input.value = '';
      showError('');
    }
  });
  document.addEventListener('keydown', (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if (event.key === '/' && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      els.input.focus();
      els.input.select();
    }
  });
  els.copy.addEventListener('click', onCopy);

  getHealth()
    .then((health) => {
      els.pill.dataset.state = 'ok';
      els.pill.querySelector('.server-pill__label').textContent = `local · v${health.version}`;
    })
    .catch(() => {
      els.pill.dataset.state = 'down';
      els.pill.querySelector('.server-pill__label').textContent = 'hors ligne';
    });

  try {
    const platforms = await getPlatforms();
    platforms.forEach(addPlatform);
    motion.cardsIn([...els.grid.children, ...els.extras.children]);
  } catch (err) {
    showError(err.message || 'Impossible de charger les plateformes.');
    return;
  }

  const initial = new URL(window.location.href).searchParams.get('u');
  if (initial) {
    els.input.value = normalize(initial);
    runSearch(initial);
  } else if (window.matchMedia('(hover: hover)').matches) {
    els.input.focus({ preventScroll: true });
  }
}

init();
