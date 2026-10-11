import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Spinner } from './ui';
import LockScreen from './LockScreen';

// Renders the app only once the server says this device is allowed in.
export default function AuthGate({ children }) {
    const [state, setState] = useState('checking'); // checking | locked | open

    useEffect(() => {
        api('/auth/status')
            .then((r) => setState(r.required && !r.ok ? 'locked' : 'open'))
            .catch(() => setState('open')); // offline/server error: let pages show their own errors
        const onLocked = () => setState('locked');
        window.addEventListener('auth-required', onLocked);
        return () => window.removeEventListener('auth-required', onLocked);
    }, []);

    if (state === 'checking') return <div className="min-h-dvh grid place-items-center text-subtle"><Spinner className="h-5 w-5" /></div>;
    if (state === 'locked') return <LockScreen onUnlock={() => setState('open')} />;
    return children;
}
