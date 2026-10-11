// Web Share Target + manifest shortcut handling.
// Android shares land on /share?title=&text=&url= (GET, see manifest share_target); many apps put
// the link inside `text` instead of `url`. Shortcuts open /#/today?capture=1 or ?focus=1.

const URL_RE = /https?:\/\/[^\s<>"'`]+/i;

export const extractUrl = (s) => {
    const m = (s || '').match(URL_RE);
    return m ? m[0].replace(/[).,;:!?\]]+$/, '') : '';
};

let consumed = null;

/**
 * Reads and clears share/shortcut params from the current location (once per page load).
 * Returns null, or { title, text, url, capture: true } for a share / ?capture=1, or { focus: true }.
 */
export function consumeShareParams() {
    if (consumed) return consumed.payload;
    consumed = { payload: null };
    if (typeof window === 'undefined') return null;
    const loc = window.location;

    if (loc.pathname.replace(/\/+$/, '') === '/share') {
        const q = new URLSearchParams(loc.search);
        const title = (q.get('title') || '').trim();
        let text = (q.get('text') || '').trim();
        let url = (q.get('url') || '').trim() || extractUrl(text) || extractUrl(title);
        if (url && text.includes(url)) text = text.replace(url, ' ').replace(/\s+/g, ' ').trim();
        window.history.replaceState(null, '', '/#/today');
        if (title || text || url) consumed.payload = { title, text, url, capture: true };
        return consumed.payload;
    }

    // Hash-route query, e.g. #/today?capture=1 — strip it so the router sees a clean route.
    const [route, query] = loc.hash.split('?');
    if (query !== undefined) {
        const q = new URLSearchParams(query);
        if (q.get('capture') === '1') consumed.payload = { title: '', text: q.get('text') || '', url: '', capture: true };
        else if (q.get('focus') === '1') consumed.payload = { focus: true };
        window.history.replaceState(null, '', `${loc.pathname}${loc.search}${route || '#/today'}`);
    }
    return consumed.payload;
}

/** Text to prefill the capture input with: "<text> <url>" (title used when there is no text). */
export function sharePrefill(p) {
    if (!p) return '';
    const body = p.text || (p.url ? '' : p.title);
    return [body, p.url].filter(Boolean).join(' ').trim();
}
