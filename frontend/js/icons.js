// Brand glyphs from Simple Icons (CC0-1.0, https://simpleicons.org), 24×24 viewBox.
// Used for identification only; each mark belongs to its owner.
const PATHS = {
  twitch:
    'M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.429l-3 3v-3H6.857V1.714h13.714Z',
};

const SVG_NS = 'http://www.w3.org/2000/svg';

// Returns an <svg> for known platforms, or a letter badge as a fallback.
export function iconFor(id, label) {
  const d = PATHS[id];
  if (d) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'currentColor');
    svg.setAttribute('focusable', 'false');
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', d);
    svg.append(path);
    return svg;
  }
  const letter = document.createElement('span');
  letter.className = 'card__logo-letter';
  letter.textContent = (label || id || '?').trim().charAt(0).toUpperCase();
  return letter;
}
