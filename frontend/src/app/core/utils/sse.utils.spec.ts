import { parseSse } from './sse.utils';

describe('parseSse', () => {
  it('lit les événements complets et garde le reste pour la suite du flux', () => {
    const text = 'event: token\ndata: {"text":"Le "}\n\n: keepalive\n\nevent: token\ndata: {"text":"po';
    const { events, consumed } = parseSse(text);
    expect(events).toEqual([{ event: 'token', data: { text: 'Le ' } }]);
    expect(text.slice(consumed)).toBe('event: token\ndata: {"text":"po');
  });

  it('accepte les fins de ligne CRLF et ignore les blocs illisibles', () => {
    const text = 'event: start\r\ndata: {"job_id":"a"}\r\n\r\nevent: token\ndata: pas du json\n\n';
    const { events, consumed } = parseSse(text);
    expect(events).toEqual([{ event: 'start', data: { job_id: 'a' } }]);
    expect(consumed).toBe(text.length);
  });
});
