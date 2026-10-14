import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { FEATURES } from './featuresList';

export { FEATURES } from './featuresList';

const FeaturesCtx = createContext({ status: () => 'beta', setStatus: () => {}, isOn: () => false, loaded: false });
export const useFeatures = () => useContext(FeaturesCtx);

export function FeaturesProvider({ children }) {
    const [flags, setFlags] = useState({});
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        api('/features').then((r) => setFlags(r.data || {})).catch(() => {}).finally(() => setLoaded(true));
    }, []);

    const setStatus = useCallback(async (id, status) => {
        setFlags((f) => ({ ...f, [id]: status }));
        try { await api(`/features/${id}`, { method: 'PUT', body: { status } }); } catch { /* optimistic; next load re-syncs */ }
    }, []);

    const value = useMemo(() => ({
        loaded,
        status: (id) => flags[id] || 'beta',
        isOn: (id) => flags[id] === 'approved',
        setStatus,
    }), [flags, loaded, setStatus]);

    return <FeaturesCtx.Provider value={value}>{children}</FeaturesCtx.Provider>;
}
