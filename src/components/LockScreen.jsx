import { useEffect, useRef, useState } from 'react';
import { Flame, Lock, ArrowRight } from 'lucide-react';
import { api, setToken } from '../lib/api';
import { Spinner, cx } from './ui';

export default function LockScreen({ onUnlock }) {
    const [code, setCode] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const [shake, setShake] = useState(false);
    const input = useRef(null);

    useEffect(() => { input.current?.focus(); }, []);

    const submit = async (e) => {
        e.preventDefault();
        if (!code) return;
        setBusy(true);
        setError('');
        try {
            const res = await api('/auth/login', { method: 'POST', body: { passcode: code } });
            setToken(res.token);
            onUnlock();
        } catch (err) {
            setError(err.message);
            setCode('');
            setShake(true);
            setTimeout(() => setShake(false), 450);
            input.current?.focus();
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="min-h-dvh grid place-items-center px-4 relative overflow-hidden">
            <div aria-hidden className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[28rem] w-[28rem] rounded-full bg-accent opacity-[0.12] blur-3xl" />
            <form onSubmit={submit} className={cx('relative w-full max-w-sm card p-7 sm:p-8 text-center animate-rise', shake && 'animate-[shake_0.4s]')}>
                <div className="mx-auto grid place-items-center h-14 w-14 rounded-2xl bg-accent text-accent-fg shadow-[0_10px_30px_-8px_var(--accent)]">
                    <Flame className="h-7 w-7" strokeWidth={2.5} />
                </div>
                <h1 className="mt-5 text-2xl font-bold tracking-tight">Welcome back</h1>
                <p className="mt-1 text-sm text-muted">Enter your passcode to open Daily.</p>
                <div className="relative mt-6">
                    <Lock className="h-4 w-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-subtle" />
                    <input
                        ref={input}
                        type="password"
                        inputMode="text"
                        autoComplete="current-password"
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        placeholder="Passcode"
                        className="input h-12 pl-10 text-base tracking-widest"
                        aria-label="Passcode"
                    />
                </div>
                {error && <p className="mt-2 text-sm text-danger text-left">{error}</p>}
                <button type="submit" disabled={busy || !code} className="btn btn-primary btn-lg w-full mt-4">
                    {busy ? <Spinner /> : <>Unlock <ArrowRight className="h-4 w-4" /></>}
                </button>
                <p className="mt-4 text-xs text-subtle">Remembered on this device until you lock it.</p>
            </form>
        </div>
    );
}
