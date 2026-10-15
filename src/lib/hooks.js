import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { invalidate as invalidateCache, isCacheable, readSnapshot, selectKey, writeSelected, writeSnapshot } from './cache';

// Hash routing (#/problems/12) so the app works as a static SPA and as a browser homepage.
export function useHashRoute() {
    const read = () => (window.location.hash.replace(/^#\/?/, '') || 'learn').split('/');
    const [parts, setParts] = useState(read);
    useEffect(() => {
        const onChange = () => setParts(read());
        window.addEventListener('hashchange', onChange);
        return () => window.removeEventListener('hashchange', onChange);
    }, []);
    return parts;
}

export const navigate = (path) => { window.location.hash = `/${path}`; };

export function useLocalStorage(key, initial) {
    const [value, setValue] = useState(() => {
        try {
            const raw = localStorage.getItem(key);
            return raw != null ? JSON.parse(raw) : initial;
        } catch { return initial; }
    });
    useEffect(() => {
        try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
    }, [key, value]);
    return [value, setValue];
}

// ---- Request dedupe -------------------------------------------------------------
// Concurrent identical GETs (several cards asking for /settings, /stats, ...) share one
// in-flight promise. A "fresh" request (explicit reload, or a deps change that usually
// follows a mutation) only joins a request that started within JOIN_FRESH_MS, i.e. in
// the same render/effect pass, so it can never be handed a response that predates a write.
const inflight = new Map(); // path -> { promise, started }
const latestStart = new Map(); // path -> start time of the newest request (snapshot ordering)
const JOIN_FRESH_MS = 25;

const clone = (v) => {
    try { return typeof structuredClone === 'function' ? structuredClone(v) : JSON.parse(JSON.stringify(v)); }
    catch { return v; }
};

function sharedGet(path, { fresh = false } = {}) {
    const now = Date.now();
    const cur = inflight.get(path);
    // Joiners get their own copy so an in-place mutation in one card can't leak into another.
    if (cur && (!fresh || now - cur.started <= JOIN_FRESH_MS)) return cur.promise.then(clone);
    latestStart.set(path, now);
    const promise = api(path)
        .then((res) => {
            // Only the newest request for a path may write its snapshot (no out-of-order overwrite).
            if (latestStart.get(path) === now) writeSnapshot(path, res);
            return res;
        })
        .finally(() => { if (inflight.get(path)?.promise === promise) inflight.delete(path); });
    inflight.set(path, { promise, started: now });
    return promise;
}

/** Drop cached snapshots (and in-flight dedupe entries) for paths starting with `prefix`. */
export function invalidate(prefix = '') {
    for (const p of [...inflight.keys()]) if (p.startsWith(prefix)) inflight.delete(p);
    invalidateCache(prefix);
}

// Initial state for a path: hydrate from the snapshot cache if we have one.
function initialState(path, select) {
    if (!path) return { path, data: null, error: null, loading: false, hydrated: false };
    const snap = readSnapshot(path);
    if (snap) {
        try {
            const key = selectKey(select);
            const data = snap.sel && key in snap.sel ? snap.sel[key] : select(snap.raw);
            return { path, data, error: null, loading: false, hydrated: true };
        } catch { /* snapshot shape no longer matches select(); fall through to a cold load */ }
    }
    return { path, data: null, error: null, loading: true, hydrated: false };
}

// GET a resource; returns { data, error, loading, reload, setData }.
// Stale-while-revalidate: a cached snapshot renders instantly (loading=false), then the
// hook refreshes in the background. Fresh responses and setData() edits are snapshotted.
export function useApi(path, { select = (d) => d.data, deps = [] } = {}) {
    const selectRef = useRef(select);
    selectRef.current = select;
    const [state, setState] = useState(() => initialState(path, select));
    // Path changed: re-derive state for the new path during render (no flash of old data).
    let cur = state;
    if (state.path !== path) {
        cur = initialState(path, select);
        setState(cur);
    }

    const reqId = useRef(0);
    const alive = useRef(true);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

    const run = useCallback(async ({ silent, fresh } = {}) => {
        if (!path) return;
        const id = ++reqId.current;
        if (!silent) setState((s) => (s.path === path ? { ...s, loading: true } : s));
        try {
            const res = await sharedGet(path, { fresh });
            if (!alive.current || id !== reqId.current) return;
            const data = selectRef.current(res);
            setState((s) => (s.path === path ? { ...s, data, error: null, loading: false } : s));
        } catch (e) {
            if (!alive.current || id !== reqId.current) return;
            setState((s) => (s.path === path ? { ...s, error: e.message, loading: false } : s));
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [path, ...deps]);

    // Public reload: always a fresh request (it typically follows a mutation).
    const reload = useCallback((opts = {}) => run({ ...opts, fresh: true }), [run]);

    // First run for a path joins any in-flight request and is silent when hydrated;
    // later runs (deps changed) fetch fresh, like the original hook.
    const lastPath = useRef(undefined);
    useEffect(() => {
        if (!path) return;
        const first = lastPath.current !== path;
        lastPath.current = path;
        if (first) run({ silent: state.hydrated && state.path === path, fresh: false });
        else run({ fresh: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [run]);

    // Persist optimistic edits so they survive a page reload.
    const dirty = useRef(false);
    const setData = useCallback((fn) => {
        dirty.current = true;
        setState((s) => ({ ...s, data: typeof fn === 'function' ? fn(s.data) : fn }));
    }, []);
    useEffect(() => {
        if (!dirty.current) return;
        dirty.current = false;
        if (isCacheable(state.path)) writeSelected(state.path, selectKey(selectRef.current), state.data);
    }, [state.data, state.path]);

    return { data: cur.data, error: cur.error, loading: cur.loading, reload, setData };
}

export function timeAgo(iso) {
    if (!iso) return '';
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
