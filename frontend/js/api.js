// Thin client for the Claimd backend (same origin).

export class ApiError extends Error {}

async function readError(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') return body.detail;
  } catch {
    /* not JSON */
  }
  return `Erreur du serveur Claimd (HTTP ${res.status}).`;
}

async function request(url, options = {}) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError('Serveur Claimd injoignable. Est-il toujours lancé ?');
  }
  if (!res.ok) throw new ApiError(await readError(res));
  return res;
}

export async function getJSON(url, options) {
  const res = await request(url, { ...options, headers: { Accept: 'application/json' } });
  return res.json();
}

export const getPlatforms = () => getJSON('/platforms');
export const getHealth = () => getJSON('/health');

const checkPath = (username) => `/check/${encodeURIComponent(username)}`;

/**
 * Stream a check: calls onEvent({type: 'start' | 'result' | 'done', ...}) as
 * each platform answers. Falls back to the aggregated endpoint when the
 * browser can't read a response stream.
 */
export async function streamCheck(username, { signal, onEvent }) {
  const res = await request(`${checkPath(username)}/stream`, {
    signal,
    headers: { Accept: 'application/x-ndjson' },
  });

  if (!res.body || typeof TextDecoderStream === 'undefined') {
    const data = await getJSON(checkPath(username), { signal });
    onEvent({ type: 'start', username: data.username, platforms: data.results.map((r) => r.platform) });
    data.results.forEach((result) => onEvent({ type: 'result', result }));
    onEvent({ type: 'done', username: data.username, elapsed_ms: data.elapsed_ms, summary: data.summary });
    return;
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  const flush = (final = false) => {
    let newline;
    while ((newline = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onEvent(JSON.parse(line));
    }
    if (final && buffer.trim()) onEvent(JSON.parse(buffer));
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    flush();
  }
  flush(true);
}
