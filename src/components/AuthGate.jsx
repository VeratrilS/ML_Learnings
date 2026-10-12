import { Suspense, lazy, useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Spinner } from './ui';
import LockScreen from './LockScreen';

const Portfolio = lazy(() => import('../pages/Portfolio'));

const spinner = <div className="min-h-dvh grid place-items-center text-subtle"><Spinner className="h-5 w-5" /></div>;
const hash = () => window.location.hash;

// Visitors (locked) see the public portfolio. The owner opens the passcode screen through a hidden entrance
// in the portfolio (or #/login) and then gets the app. #/portfolio shows the portfolio to anyone, unlocked or not.
export default function AuthGate({ children }) {
    const [state, setState] = useState('checking'); // checking | locked | open
    const [login, setLogin] = useState(() => hash() === '#/login');
    const [route, setRoute] = useState(hash);

    useEffect(() => {
        api('/auth/status')
            .then((r) => setState(r.required && !r.ok ? 'locked' : 'open'))
            .catch(() => setState('open')); // offline/server error: let pages show their own errors
        const onLocked = () => setState('locked');
        const onHash = () => {
            setRoute(hash());
            if (hash() === '#/login') setLogin(true);
        };
        window.addEventListener('auth-required', onLocked);
        window.addEventListener('hashchange', onHash);
        return () => {
            window.removeEventListener('auth-required', onLocked);
            window.removeEventListener('hashchange', onHash);
        };
    }, []);

    const openLogin = () => setLogin(true);
    const closeLogin = () => {
        setLogin(false);
        if (hash() === '#/login') history.replaceState(null, '', window.location.pathname);
    };
    const unlocked = () => {
        setLogin(false);
        setState('open');
        if (hash() === '#/login' || hash() === '#/portfolio') window.location.hash = '#/today';
    };

    if (state === 'checking') return spinner;
    if (state === 'locked' && login) return <LockScreen onUnlock={unlocked} onBack={closeLogin} />;
    if (state === 'locked' || route === '#/portfolio') {
        return (
            <Suspense fallback={spinner}>
                <Portfolio owner={state === 'open'} onUnlock={state === 'open' ? () => { window.location.hash = '#/today'; } : openLogin} />
            </Suspense>
        );
    }
    return children;
}
