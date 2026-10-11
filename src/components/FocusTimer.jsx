import { useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, SkipForward, Timer } from 'lucide-react';
import { api } from '../lib/api';
import { useLocalStorage } from '../lib/hooks';
import { Card, CardHeader, ProgressRing, Segmented, cx } from './ui';

const MODES = { focus: 'Focus', short: 'Break', long: 'Long break' };
const todayKey = () => new Date().toDateString();

function beep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [0, 0.25, 0.5].forEach((t) => {
            const o = ctx.createOscillator();
            const g = ctx.createGain();
            o.frequency.value = 880;
            g.gain.setValueAtTime(0.0001, ctx.currentTime + t);
            g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + t + 0.02);
            g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.2);
            o.connect(g).connect(ctx.destination);
            o.start(ctx.currentTime + t);
            o.stop(ctx.currentTime + t + 0.22);
        });
    } catch { /* audio unavailable */ }
}

const MIN_PARTIAL_MIN = 5; // abandoned focus sessions this long still count

const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

export default function FocusTimer() {
    const [focusLen, setFocusLen] = useLocalStorage('focus:len', 25);
    const [state, setState] = useLocalStorage('focus:state', { mode: 'focus', endsAt: null, left: 25 * 60 });
    const [sessions, setSessions] = useLocalStorage('focus:sessions', { day: todayKey(), count: 0 });
    const [, tick] = useState(0);
    const [serverMinutes, setServerMinutes] = useState(null); // today's focused minutes from the API (null = unknown)
    const baseTitle = useRef(document.title);
    const loggedRef = useRef(null); // endsAt of the last session we logged (guards double effects)

    const durations = { focus: focusLen * 60, short: 5 * 60, long: 15 * 60 };
    const total = durations[state.mode];
    const running = !!state.endsAt;
    const left = running ? Math.max(0, Math.round((state.endsAt - Date.now()) / 1000)) : state.left;
    const todayCount = sessions.day === todayKey() ? sessions.count : 0;
    const focusedMinutes = serverMinutes ?? todayCount * focusLen;

    useEffect(() => {
        let alive = true;
        api('/focus?days=1').then((r) => alive && setServerMinutes(r.today_minutes ?? 0)).catch(() => { /* fall back to local count */ });
        return () => { alive = false; };
    }, []);

    // Persist a focus session server-side; optimistic so the subtitle updates instantly.
    const logSession = (minutes, completed, startedAtMs) => {
        if (minutes < 1) return;
        setServerMinutes((m) => (m == null ? m : m + minutes));
        api('/focus', { method: 'POST', body: { minutes, completed, started_at: new Date(startedAtMs).toISOString() } })
            .then((r) => setServerMinutes(r.today_minutes ?? null))
            .catch(() => setServerMinutes(null)); // server unreachable: show the local count instead
    };
    // Resetting/skipping a focus block after >= 5 minutes still logs what was done
    const logPartial = () => {
        if (state.mode !== 'focus') return;
        const elapsed = total - left;
        if (elapsed >= MIN_PARTIAL_MIN * 60) logSession(Math.floor(elapsed / 60), false, Date.now() - elapsed * 1000);
    };

    useEffect(() => {
        if (!running) return;
        const t = setInterval(() => tick((n) => n + 1), 500);
        return () => clearInterval(t);
    }, [running]);

    useEffect(() => {
        const title = baseTitle.current;
        if (running) document.title = `${fmt(left)} · ${MODES[state.mode]}`;
        return () => { document.title = title; };
    }, [running, left, state.mode]);

    useEffect(() => {
        if (!running || left > 0) return;
        beep();
        const wasFocus = state.mode === 'focus';
        if (wasFocus) {
            setSessions({ day: todayKey(), count: todayCount + 1 });
            if (loggedRef.current !== state.endsAt) {
                loggedRef.current = state.endsAt;
                logSession(Math.round(total / 60), true, state.endsAt - total * 1000);
            }
        }
        const next = wasFocus ? ((todayCount + 1) % 4 === 0 ? 'long' : 'short') : 'focus';
        try {
            if ('Notification' in window && Notification.permission === 'granted') {
                new Notification(wasFocus ? 'Focus session done. Take a break.' : 'Break over. Back to it!', { icon: '/icon-192.png' });
            }
        } catch { /* notifications unavailable */ }
        setState({ mode: next, endsAt: null, left: durations[next] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [running, left]);

    // Command palette can start a session: window.dispatchEvent(new CustomEvent('focus-timer', {detail:{action:'start'}}))
    const startRef = useRef(null);
    useEffect(() => {
        const onEvent = (e) => e.detail?.action === 'start' && startRef.current?.();
        window.addEventListener('focus-timer', onEvent);
        return () => window.removeEventListener('focus-timer', onEvent);
    }, []);

    const start = () => {
        try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch { /* ignore */ }
        setState({ ...state, endsAt: Date.now() + left * 1000 });
    };
    startRef.current = () => { if (!running) start(); };
    const pause = () => setState({ ...state, endsAt: null, left });
    const reset = () => { logPartial(); setState({ mode: state.mode, endsAt: null, left: total }); };
    const switchMode = (mode) => setState({ mode, endsAt: null, left: durations[mode] });
    const skip = () => { logPartial(); switchMode(state.mode === 'focus' ? 'short' : 'focus'); };
    const changeLen = (len) => {
        setFocusLen(len);
        if (state.mode === 'focus' && !running) setState({ mode: 'focus', endsAt: null, left: len * 60 });
    };

    return (
        <Card className="card-pad">
            <CardHeader
                title="Focus"
                subtitle={`${todayCount} session${todayCount === 1 ? '' : 's'} · ${focusedMinutes} min focused today`}
                icon={Timer}
                action={<Segmented value={focusLen} onChange={changeLen} options={[{ value: 25, label: '25' }, { value: 50, label: '50' }]} />}
            />
            <div className="flex items-center gap-5">
                <ProgressRing value={total - left} max={total} size={112} stroke={7}>
                    <div className="text-center">
                        <div className="font-mono text-[22px] font-semibold tracking-tight tabular-nums">{fmt(left)}</div>
                        <div className="text-[10.5px] uppercase tracking-wider text-subtle font-semibold">{MODES[state.mode]}</div>
                    </div>
                </ProgressRing>
                <div className="flex-1 flex flex-col gap-2 min-w-0">
                    <button onClick={running ? pause : start} className={cx('btn w-full', running ? 'btn-secondary' : 'btn-primary')}>
                        {running ? <><Pause className="h-4 w-4" /> Pause</> : <><Play className="h-4 w-4 fill-current" /> {left < total ? 'Resume' : 'Start'}</>}
                    </button>
                    <div className="flex gap-2">
                        <button onClick={reset} className="btn btn-ghost btn-sm flex-1" aria-label="Reset"><RotateCcw className="h-3.5 w-3.5" /> Reset</button>
                        <button onClick={skip} className="btn btn-ghost btn-sm flex-1" aria-label="Skip"><SkipForward className="h-3.5 w-3.5" /> Skip</button>
                    </div>
                    <div className="flex gap-1 justify-center pt-1">
                        {[0, 1, 2, 3].map((i) => (
                            <span key={i} className={cx('h-1.5 w-6 rounded-full', i < todayCount % 4 || (todayCount > 0 && todayCount % 4 === 0) ? 'bg-accent' : 'bg-surface-3')} />
                        ))}
                    </div>
                </div>
            </div>
        </Card>
    );
}
