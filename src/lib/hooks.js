import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';

// Hash routing (#/problems/12) so the app works as a static SPA and as a browser homepage.
export function useHashRoute() {
    const read = () => (window.location.hash.replace(/^#\/?/, '') || 'today').split('/');
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

// GET a resource; returns { data, error, loading, reload, setData }.
export function useApi(path, { select = (d) => d.data, deps = [] } = {}) {
    const [state, setState] = useState({ data: null, error: null, loading: !!path });
    const selectRef = useRef(select);
    selectRef.current = select;
    const reload = useCallback(async ({ silent } = {}) => {
        if (!path) return;
        if (!silent) setState((s) => ({ ...s, loading: true }));
        try {
            const res = await api(path);
            setState({ data: selectRef.current(res), error: null, loading: false });
        } catch (e) {
            setState((s) => ({ ...s, error: e.message, loading: false }));
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [path, ...deps]);
    useEffect(() => { reload(); }, [reload]);
    const setData = useCallback((fn) => setState((s) => ({ ...s, data: typeof fn === 'function' ? fn(s.data) : fn })), []);
    return { ...state, reload, setData };
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
