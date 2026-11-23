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
  official_api: 'API officielle',
  public_profile: 'Profil public',
  http_probe: 'Sonde du profil',
  session_probe: 'Ta session Instagram',
  manual: 'Vérifié par toi',
  none: 'Aucune méthode légitime',
};

const LINK_LABEL = {
  available: 'Profil ↗',
  taken: 'Profil ↗',
  uncertain: 'Vérifier ↗',
};

const MANUAL_DETAIL = {
  taken: 'Vérifié par toi : un profil existe à ce nom.',
  available: 'Vérifié par toi : aucun profil visible. Un compte désactivé peut encore bloquer ce nom.',
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
  pill: $('server-pill'),
  cardTemplate: $('card-template'),
};

const state = {
  platforms: new Map(), // id -> platform info
  views: new Map(), // id -> { el, seg? }
  run: 0, // increments on every search; stale callbacks compare against it
  controller: null,
  revealAt: 0,
  chain: Promise.resolve(),
  username: '',
  elapsed: null,
  done: false,
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
  if (!platform.verifiable) el.dataset.variant = 'info';
  el.style.setProperty('--i', index);
  el.querySelector('.card__logo').append(brandIcon(platform.id, platform.label));
  el.querySelector('.card__icon').append(statusIcon());
  el.querySelector('.card__name').textContent = platform.label;
  el.querySelector('.card__method').textContent = METHOD_LABEL[platform.method] || platform.method;
  el.querySelector('.reliability__info').append(infoIcon());
  const reliability = el.querySelector('.reliability');
  reliability.dataset.tipTitle = platform.verifiable
    ? `${platform.label} · comment c'est vérifié`
    : `Pourquoi ${platform.label} n'est pas vérifié`;
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
  const index = state.views.size;
  const view = { el: createCard(platform, index) };
  if (platform.verifiable) view.seg = createSegment(platform, els.segments.children.length);
  state.views.set(platform.id, view);
  paintIdle(platform.id);
  return view;
}

function paint(id, status, { detail = '', url = null, reliability, elapsed = null, method, cached = false, manual = false } = {}) {
  const view = state.views.get(id);
  if (!view) return;
  const platform = state.platforms.get(id);
  const { el } = view;
  el.dataset.state = status;
  delete el.dataset.asking;
  if (manual) el.dataset.manual = '';
  else delete el.dataset.manual;

  el.querySelector('.card__label').textContent = STATUS_LABEL[status] || status;
  el.querySelector('.card__method').textContent = METHOD_LABEL[method || platform.method] || method || platform.method;
  const detailEl = el.querySelector('.card__detail');
  detailEl.textContent = detail;
  detailEl.title = detail; // full text on hover if clamped to 3 lines

  const time = el.querySelector('.card__time');
  time.textContent = manual ? 'manuel' : cached ? 'cache' : formatMs(elapsed);
  time.dataset.kind = manual ? 'manual' : cached ? 'cached' : 'timing';
  time.title = cached ? 'Résultat réutilisé : vérifié il y a moins de 10 minutes.' : '';

  const level = reliability || platform.reliability;
  const rel = el.querySelector('.reliability');
  rel.dataset.level = level;
  const relText = status === 'unverifiable' ? 'Pourquoi ?' : RELIABILITY_LABEL[level] || '';
  rel.querySelector('.reliability__label').textContent = relText;
  rel.setAttribute('aria-label', status === 'unverifiable' ? `Pourquoi ${platform.label} n'est pas vérifié` : `${relText}. Comment ${platform.label} est vérifié`);

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

function computeSummary() {
  const summary = { checkable: 0, available: 0, taken: 0, uncertain: 0, invalid: 0 };
  for (const [id, view] of state.views) {
    if (!state.platforms.get(id).verifiable) continue;
    summary.checkable += 1;
    const status = view.el.dataset.state;
    if (status in summary) summary[status] += 1;
  }
  return summary;
}

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

function summaryDone(username, summary, elapsed, from = 0) {
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
  els.summaryTime.textContent = elapsed ? `en ${formatMs(elapsed)}` : '';
  els.copy.setAttribute('aria-label', `Copier « ${username} »`);
  motion.summaryIn(els.summaryText, count, available, from);
}

// ---------------------------------------------------------------- manual check

function startAsking(card) {
  card.dataset.asking = '';
  // The profile opens in a new tab; the question waits here for the user's return.
  requestAnimationFrame(() => card.querySelector('.ask__btn[data-verdict]')?.focus({ preventScroll: true }));
}

function applyManualVerdict(card, verdict) {
  const id = card.dataset.platform;
  const before = computeSummary().available;
  const url = card.querySelector('.card__link').getAttribute('href');
  motion.settle(card);
  paint(id, verdict, {
    detail: MANUAL_DETAIL[verdict],
    url,
    reliability: verdict === 'taken' ? 'high' : 'medium',
    method: 'manual',
    manual: true,
  });
  motion.reveal(card, verdict);
  const view = state.views.get(id);
  if (view.seg) motion.segment(view.seg);
  if (state.done) summaryDone(state.username, computeSummary(), state.elapsed, before);
}

function onGridClick(event) {
  const card = event.target.closest('.card');
  if (!card) return;
  if (event.target.closest('.card__link') && card.dataset.state === 'uncertain') {
    startAsking(card); // the link still opens the profile (no preventDefault)
    return;
  }
  const verdict = event.target.closest('[data-verdict]')?.dataset.verdict;
  if (verdict) {
    applyManualVerdict(card, verdict);
    card.querySelector('.card__link')?.focus({ preventScroll: true });
    return;
  }
  if (event.target.closest('.ask__cancel')) {
    delete card.dataset.asking;
    card.querySelector('.card__link')?.focus({ preventScroll: true });
  }
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
    method: result.method,
    cached: result.cached,
  });
  motion.reveal(view.el, result.status);
  if (view.seg) motion.segment(view.seg);
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
  state.elapsed = null;
  state.done = false;

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
    cards.push(view.el);
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
          enqueue(
            run,
            () => {
              state.elapsed = event.elapsed_ms;
              state.done = true;
              summaryDone(event.username, computeSummary(), event.elapsed_ms);
            },
            motion.pacing().summaryDelay,
          );
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
  els.grid.addEventListener('click', onGridClick);

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
    motion.cardsIn([...els.grid.children]);
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
