// Every GSAP animation lives here. Each function is a pure "flourish": the CSS
// already holds the final state, so if GSAP is missing or the user prefers
// reduced motion, these become no-ops and the UI is still correct.

const media = window.matchMedia('(prefers-reduced-motion: reduce)');
let reduced = media.matches;
media.addEventListener?.('change', (event) => {
  reduced = event.matches;
  document.documentElement.classList.toggle('reduce-motion', reduced);
});

const gsap = () => window.gsap;
export const enabled = () => Boolean(gsap()) && !reduced;

// Pacing of the reveal queue (app.js): cards land one by one, never in a burst.
export const pacing = () => (enabled() ? { minLoading: 520, gap: 150, summaryDelay: 120 } : { minLoading: 0, gap: 0, summaryDelay: 0 });

const GLYPHS = {
  available: ['.sicon__check'],
  taken: ['.sicon__cross-a', '.sicon__cross-b'],
  uncertain: ['.sicon__question'],
  invalid: ['.sicon__ban'],
  unverifiable: ['.sicon__dash'],
};

export function intro() {
  const root = document.documentElement;
  if (!enabled()) {
    root.classList.add('intro-done');
    return;
  }
  const g = gsap();
  const items = document.querySelectorAll('[data-intro]');
  g.set(items, { opacity: 0, y: 16 });
  root.classList.add('intro-done');
  const tl = g.timeline({ defaults: { ease: 'power3.out' } });
  tl.to(items, { opacity: 1, y: 0, duration: 0.85, stagger: 0.075, clearProps: 'opacity,transform' });
  const underline = document.querySelector('.hero__underline path');
  if (underline) {
    tl.fromTo(
      underline,
      { strokeDashoffset: 1 },
      { strokeDashoffset: 0, duration: 0.9, ease: 'power2.inOut', clearProps: 'strokeDashoffset' },
      0.5,
    );
  }
}

let entrance = null;

export function cardsIn(elements) {
  if (!enabled() || !elements.length) return;
  entrance = gsap().fromTo(
    elements,
    { opacity: 0, y: 22 },
    { opacity: 1, y: 0, duration: 0.75, ease: 'power3.out', stagger: 0.07, delay: 0.3, clearProps: 'opacity,transform' },
  );
}

// Jump the cards' entrance to its end (a search can start before it finishes,
// e.g. with ?u= in the URL). Completing it also applies its clearProps.
export function finishEntrance() {
  if (!entrance) return;
  entrance.progress(1).kill();
  entrance = null;
}

// Inner SVG shapes (circle, path…), as opposed to HTML elements and the root <svg>.
const isSvgShape = (el) => el instanceof SVGElement && !(el instanceof SVGSVGElement);

// Stop anything still animating inside an element (a new search can start mid-reveal).
export function settle(element) {
  const g = gsap();
  if (!g) return;
  const targets = [element, ...element.querySelectorAll('*')];
  g.killTweensOf(targets);
  // Only what GSAP animates; inline custom properties (--i, --mx…) must survive.
  // Never touch transforms of inner SVG shapes: GSAP would pin an inline
  // transform-origin on them and break the CSS rotation of the status ring.
  g.set(targets.filter((el) => !isSvgShape(el)), { clearProps: 'transform,opacity' });
  g.set(targets.filter(isSvgShape), { clearProps: 'opacity,strokeDashoffset' });
}

export function toLoading(elements) {
  if (!enabled()) return;
  const blocks = elements.flatMap((el) => [...el.querySelectorAll('.card__status, .card__body')]);
  gsap().fromTo(blocks, { opacity: 0.25 }, { opacity: 1, duration: 0.4, ease: 'power2.out', stagger: 0.025, clearProps: 'opacity' });
}

export function reveal(card, state) {
  if (!enabled()) return;
  const g = gsap();
  const q = (selector) => card.querySelector(selector);
  const glyphs = (GLYPHS[state] || []).map(q).filter(Boolean);
  const tl = g.timeline({ defaults: { ease: 'power3.out' } });

  tl.fromTo(card, { y: 8, scale: 0.982 }, { y: 0, scale: 1, duration: 0.75, clearProps: 'transform' }, 0)
    .fromTo(q('.card__flash'), { opacity: 1 }, { opacity: 0, duration: 1.3, ease: 'power2.out', clearProps: 'opacity' }, 0)
    .fromTo(
      q('.sicon'),
      { scale: 0.55, opacity: 0 },
      { scale: 1, opacity: 1, duration: 0.6, ease: 'back.out(2.2)', clearProps: 'transform,opacity' },
      0,
    )
    .fromTo(
      q('.sicon__ring'),
      { strokeDashoffset: 1 },
      { strokeDashoffset: 0, duration: 0.65, ease: 'power2.out', clearProps: 'strokeDashoffset' },
      0.05,
    )
    .fromTo(q('.card__label'), { y: 10, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, clearProps: 'transform,opacity' }, 0.1)
    .fromTo(
      [q('.card__detail'), q('.card__time'), q('.card__foot')],
      { y: 6, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.55, stagger: 0.05, clearProps: 'transform,opacity' },
      0.18,
    );

  if (glyphs.length) {
    tl.fromTo(
      glyphs,
      { strokeDashoffset: 1 },
      { strokeDashoffset: 0, duration: 0.34, stagger: 0.13, ease: 'power2.inOut', clearProps: 'strokeDashoffset' },
      0.24,
    );
  }
  if (state === 'uncertain') {
    // Animate the radius rather than a transform (see settle()).
    tl.fromTo(q('.sicon__question-dot'), { attr: { r: 0 } }, { attr: { r: 1.6 }, duration: 0.45, ease: 'back.out(3.5)' }, 0.55);
  }
}

export function segment(seg) {
  if (!enabled()) return;
  gsap().fromTo(
    seg.querySelector('.seg__fill'),
    { scaleX: 0 },
    { scaleX: 1, duration: 0.7, ease: 'power3.out', clearProps: 'transform' },
  );
}

export function summaryIn(element, countEl, to, from = 0) {
  if (!enabled()) return;
  const g = gsap();
  if (from === 0) {
    g.fromTo(element, { y: 6, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: 'power3.out', clearProps: 'transform,opacity' });
  }
  if (countEl && from !== to) {
    const counter = { value: from };
    countEl.textContent = String(from);
    g.to(counter, {
      value: to,
      duration: 0.8,
      ease: 'power2.out',
      onUpdate: () => { countEl.textContent = String(Math.round(counter.value)); },
    });
  }
}

export function shake(element) {
  if (!enabled()) return;
  gsap().fromTo(
    element,
    { x: 0 },
    { keyframes: { x: [0, -9, 8, -6, 4, -2, 0] }, duration: 0.5, ease: 'power2.out', clearProps: 'transform' },
  );
}

export function copied(button) {
  if (!enabled()) return;
  const g = gsap();
  g.fromTo(button, { scale: 0.92 }, { scale: 1, duration: 0.5, ease: 'back.out(3)', clearProps: 'transform' });
  g.fromTo(
    button.querySelector('.copy__icon--done path'),
    { strokeDashoffset: 1 },
    { strokeDashoffset: 0, duration: 0.35, ease: 'power2.out', clearProps: 'strokeDashoffset' },
  );
}
