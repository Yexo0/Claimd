// One shared tooltip for every [data-tip] element: hover, keyboard focus or tap.
// Content: data-tip-title (optional, bold) + data-tip.

const GAP = 10;
const MARGIN = 12;

export function initTooltips(tooltip) {
  let current = null;

  function place(trigger) {
    const t = trigger.getBoundingClientRect();
    const tip = tooltip.getBoundingClientRect();
    let left = t.left + t.width / 2 - tip.width / 2;
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - tip.width - MARGIN));
    let top = t.top - tip.height - GAP;
    if (top < MARGIN) top = t.bottom + GAP; // not enough room above: go below
    tooltip.style.left = `${Math.round(left)}px`;
    tooltip.style.top = `${Math.round(top)}px`;
  }

  function show(trigger) {
    const text = trigger.dataset.tip;
    if (!text) return;
    current = trigger;
    tooltip.replaceChildren();
    if (trigger.dataset.tipTitle) {
      const title = document.createElement('strong');
      title.textContent = trigger.dataset.tipTitle;
      tooltip.append(title);
    }
    tooltip.append(text);
    tooltip.id ||= 'tooltip';
    trigger.setAttribute('aria-describedby', tooltip.id);
    place(trigger);
    tooltip.dataset.open = '';
  }

  function hide() {
    if (!current) return;
    current.removeAttribute('aria-describedby');
    current = null;
    delete tooltip.dataset.open;
  }

  const triggerOf = (event) => event.target.closest?.('[data-tip]');

  // Mouse: open on an actual movement over the trigger, not on a pointerover
  // caused by the layout changing under a still cursor (e.g. right after a click).
  // Touch and pen: open on pointerover, which a tap produces.
  document.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return;
    const trigger = triggerOf(e);
    if (trigger && trigger !== current) show(trigger);
  });
  document.addEventListener('pointerover', (e) => {
    if (e.pointerType === 'mouse') return;
    const trigger = triggerOf(e);
    if (trigger && trigger !== current) show(trigger);
  });
  document.addEventListener('pointerout', (e) => {
    const trigger = triggerOf(e);
    if (trigger && trigger === current && !trigger.contains(e.relatedTarget) && document.activeElement !== trigger) hide();
  });
  document.addEventListener('focusin', (e) => {
    const trigger = triggerOf(e);
    if (trigger) show(trigger);
  });
  document.addEventListener('focusout', (e) => {
    if (triggerOf(e) === current) hide();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hide();
  });
  // Follow the trigger instead of vanishing when the page moves under it.
  const follow = () => current && place(current);
  window.addEventListener('scroll', follow, { passive: true });
  window.addEventListener('resize', follow);
}
