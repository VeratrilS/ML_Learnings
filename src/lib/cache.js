// Tiny localStorage-backed snapshot cache for GET responses (stale-while-revalidate).
//
// Each entry lives under `apicache:v1:<path>` as `{ raw, sel, t }`:
//   raw  - the last raw JSON response from the server for that path
//   sel  - optimistic local edits, keyed by a fingerprint of the hook's `select`
//          ({ [selKey]: selectedData }); cleared whenever a fresh `raw` is written
//   t    - last write time (ms), used for LRU eviction
// An index entry tracks sizes/times so eviction never has to scan localStorage.
// Every storage access is wrapped: private windows, quota errors and disabled storage
// simply degrade to "no cache".

const PREFIX = 'apicache:v1:';
const INDEX_KEY = `${PREFIX}__index`;
const MAX_ENTRIES = 80;
const MAX_TOTAL_BYTES = 2_000_000; // ~2MB of UTF-16 chars across all entries
const MAX_ENTRY_BYTES = 400_000; // one huge response should not evict everything else

const memory = new Map(); // path -> parsed entry (avoids re-parsing on route changes)

export const isCacheable = (path) => !!path && !path.includes('/auth');

function storage() {
    try { return window.localStorage; } catch { return null; }
}

function readIndex() {
    try {
        const raw = storage()?.getItem(INDEX_KEY);
        const idx = raw ? JSON.parse(raw) : {};
        return idx && typeof idx === 'object' && !Array.isArray(idx) ? idx : {};
    } catch { return {}; }
}

function writeIndex(idx) {
    try { storage()?.setItem(INDEX_KEY, JSON.stringify(idx)); } catch { /* storage unavailable */ }
}

function removeKey(path, idx) {
    memory.delete(path);
    delete idx[path];
    try { storage()?.removeItem(PREFIX + path); } catch { /* storage unavailable */ }
}

// Drop least-recently-written entries until we are within the count/size budget.
function evict(idx, { extraBytes = 0, keep } = {}) {
    const entries = Object.entries(idx).sort((a, b) => (a[1]?.t || 0) - (b[1]?.t || 0));
    let total = entries.reduce((n, [, v]) => n + (v?.size || 0), 0) + extraBytes;
    let count = entries.length;
    for (const [path, v] of entries) {
        if (count <= MAX_ENTRIES && total <= MAX_TOTAL_BYTES) break;
        if (path === keep) continue;
        removeKey(path, idx);
        total -= v?.size || 0;
        count -= 1;
    }
}

/** Returns `{ raw, sel, t }` for a path, or null. */
export function readSnapshot(path) {
    if (!isCacheable(path)) return null;
    if (memory.has(path)) return memory.get(path);
    try {
        const raw = storage()?.getItem(PREFIX + path);
        if (!raw) return null;
        const entry = JSON.parse(raw);
        if (!entry || typeof entry !== 'object' || !('raw' in entry)) return null;
        memory.set(path, entry);
        return entry;
    } catch { return null; }
}

function persist(path, entry) {
    if (!isCacheable(path)) return;
    memory.set(path, entry);
    const s = storage();
    if (!s) return;
    let json;
    try { json = JSON.stringify(entry); } catch { return; }
    const idx = readIndex();
    if (json.length > MAX_ENTRY_BYTES) { removeKey(path, idx); writeIndex(idx); memory.set(path, entry); return; }
    idx[path] = { t: entry.t, size: json.length };
    evict(idx, { keep: path });
    try {
        s.setItem(PREFIX + path, json);
    } catch {
        // Quota hit (other app data may be using storage): free half our entries and retry once.
        const others = Object.keys(idx).filter((p) => p !== path)
            .sort((a, b) => (idx[a]?.t || 0) - (idx[b]?.t || 0));
        others.slice(0, Math.ceil(others.length / 2)).forEach((p) => removeKey(p, idx));
        try { s.setItem(PREFIX + path, json); } catch { delete idx[path]; }
    }
    writeIndex(idx);
}

/** Store a fresh server response (drops any optimistic local edits for the path). */
export function writeSnapshot(path, raw) {
    persist(path, { raw, sel: {}, t: Date.now() });
}

/** Store locally-edited (already selected) data so optimistic changes survive a reload. */
export function writeSelected(path, selKey, data) {
    const prev = readSnapshot(path);
    if (!prev) return; // nothing fetched yet; a snapshot without `raw` would be useless
    persist(path, { raw: prev.raw, sel: { ...(prev.sel || {}), [selKey]: data }, t: Date.now() });
}

/** Remove every snapshot whose path starts with `prefix` ('' clears everything). */
export function invalidate(prefix = '') {
    const idx = readIndex();
    for (const p of [...memory.keys()]) if (p.startsWith(prefix)) memory.delete(p);
    for (const p of Object.keys(idx)) if (p.startsWith(prefix)) removeKey(p, idx);
    // Also sweep orphans (e.g. index lost) so the prefix is truly gone.
    try {
        const s = storage();
        if (s) {
            const doomed = [];
            for (let i = 0; i < s.length; i++) {
                const k = s.key(i);
                if (k && k !== INDEX_KEY && k.startsWith(PREFIX + prefix)) doomed.push(k);
            }
            doomed.forEach((k) => s.removeItem(k));
        }
    } catch { /* storage unavailable */ }
    writeIndex(idx);
}

// Stable short fingerprint for a `select` function so different selectors on one path
// never read each other's optimistic data.
export function selectKey(fn) {
    const src = String(fn);
    let h = 5381;
    for (let i = 0; i < src.length; i++) h = ((h * 33) ^ src.charCodeAt(i)) >>> 0;
    return h.toString(36);
}

// If the server says the session is locked, do not keep showing private data offline.
try {
    window.addEventListener('auth-required', () => invalidate(''));
} catch { /* non-browser env */ }
