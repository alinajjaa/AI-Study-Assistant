/** Un événement Server-Sent Events : « event: <nom> » et « data: <JSON> ». */
export interface SseEvent {
  event: string;
  data: unknown;
}

/**
 * Découpe un texte SSE reçu (éventuellement partiel) en événements complets.
 * Renvoie aussi la longueur consommée : le reste (événement incomplet) sera relu avec la suite du flux.
 * Les commentaires (« : keepalive ») et les blocs sans données JSON valides sont ignorés.
 */
export function parseSse(text: string): { events: SseEvent[]; consumed: number } {
  const events: SseEvent[] = [];
  let consumed = 0;
  let index: number;
  while ((index = nextBoundary(text, consumed)) !== -1) {
    const block = text.slice(consumed, index).replace(/\r/g, '');
    consumed = index + (text.startsWith('\r\n\r\n', index) ? 4 : 2);
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        data.push(line.slice(5).trimStart());
      }
    }
    if (data.length === 0) {
      continue;
    }
    try {
      events.push({ event, data: JSON.parse(data.join('\n')) });
    } catch {
      // Bloc illisible : ignoré, le flux continue
    }
  }
  return { events, consumed };
}

function nextBoundary(text: string, from: number): number {
  const lf = text.indexOf('\n\n', from);
  const crlf = text.indexOf('\r\n\r\n', from);
  if (lf === -1) {
    return crlf;
  }
  return crlf === -1 ? lf : Math.min(lf, crlf);
}
