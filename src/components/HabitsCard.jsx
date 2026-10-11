import { useCallback, useEffect, useRef } from 'react';
import { Check, Dumbbell, Flame, GlassWater, Minus, Moon, Plus, RefreshCw } from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, Empty, ProgressRing, Skeleton, cx, useToast } from './ui';

const WEIGHTS = { sleep: 40, water: 30, exercise: 20, screen_off: 10 };
const STREAKS = [['sleep', 'sleep'], ['water', 'water'], ['exercise', 'move'], ['screen_off', 'screens off']];
const DEBOUNCE_MS = 600;
const MAX_GLASS_ICONS = 16;

const ratio = (v, t) => (!v || !t ? 0 : Math.min(v / t, 1));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const buzz = () => { try { navigator.vibrate?.(8); } catch { /* unsupported */ } };
const fmtH = (h) => (Number.isInteger(h) ? `${h}` : h.toFixed(1).replace(/\.0$/, ''));

// Same formula as api/domain/habits.py, so the ring moves instantly on a tap.
function derive(day, t, w = WEIGHTS) {
    const score = Math.round(
        w.sleep * ratio(day.sleep_hours, t.sleep)
        + w.water * ratio(day.water_glasses, t.water)
        + w.exercise * ratio(day.exercise_min, t.exercise)
        + w.screen_off * (day.screen_off_on_time ? 1 : 0),
    );
    return {
        ...day,
        score: clamp(score, 0, 100),
        met: {
            sleep: day.sleep_hours != null && day.sleep_hours >= t.sleep,
            water: (day.water_glasses || 0) >= t.water,
            exercise: (day.exercise_min || 0) >= t.exercise,
            screen_off: !!day.screen_off_on_time,
        },
    };
}

const withToday = (d, today) => ({
    ...d,
    data: today,
    history: (d.history || []).map((h) => (h.day === today.day ? today : h)),
});

// Tap = onTap; long-press (touch) or right-click (mouse) = onLong.
function PressButton({ onTap, onLong, className, children, ...props }) {
    const timer = useRef(null);
    const fired = useRef(false);
    const clear = () => { clearTimeout(timer.current); timer.current = null; };
    useEffect(() => () => clearTimeout(timer.current), []);
    return (
        <button
            type="button"
            {...props}
            className={cx('touch-manipulation select-none', className)}
            style={{ WebkitTouchCallout: 'none' }}
            onPointerDown={(e) => {
                fired.current = false;
                if (e.button !== 0) return;
                clear();
                timer.current = setTimeout(() => { fired.current = true; onLong(); }, 450);
            }}
            onPointerUp={clear}
            onPointerLeave={clear}
            onPointerCancel={clear}
            onContextMenu={(e) => {
                e.preventDefault();
                clear();
                if (!fired.current) { fired.current = true; onLong(); }
            }}
            onClick={() => {
                if (fired.current) { fired.current = false; return; }
                onTap();
            }}
        >
            {children}
        </button>
    );
}

function Sparkline({ values }) {
    const n = values.length;
    if (n < 2) return <div className="h-8" />;
    const pts = values.map((v, i) => [(i / (n - 1)) * 100, 30 - (clamp(v || 0, 0, 100) / 100) * 28]);
    const line = pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
    const [lx, ly] = pts[n - 1];
    return (
        <div className="relative h-8 w-full text-accent" role="img" aria-label={`Body score, last ${n} days: ${values.join(', ')}`}>
            <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden>
                <polygon points={`0,32 ${line} 100,32`} fill="currentColor" opacity="0.1" />
                <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            </svg>
            <span className="absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent ring-2 ring-surface" style={{ left: `${lx}%`, top: `${(ly / 32) * 100}%` }} />
        </div>
    );
}

const MetDot = ({ on }) => (on ? <Check className="h-3.5 w-3.5 text-ok" strokeWidth={3} aria-label="Target met" /> : null);

export default function HabitsCard() {
    const { data, error, loading, reload, setData } = useApi('/habits/today', { select: (d) => d });
    const toast = useToast();
    const queued = useRef({});
    const timer = useRef(null);
    const chain = useRef(Promise.resolve());

    const flush = useCallback(() => {
        clearTimeout(timer.current);
        timer.current = null;
        const body = queued.current;
        if (!Object.keys(body).length) return;
        queued.current = {};
        // Serialize PUTs so responses can't land out of order.
        chain.current = chain.current.then(async () => {
            try {
                const res = await api('/habits/today', { method: 'PUT', body });
                setData((d) => {
                    if (!d) return d;
                    const targets = res.targets || d.targets;
                    // Taps made while this request was in flight still win.
                    const today = derive({ ...res.data, ...queued.current }, targets, d.weights);
                    return { ...withToday(d, today), targets, streaks: res.streaks || d.streaks };
                });
            } catch (e) {
                toast(e.message || "Couldn't save. Try again.", 'error');
                reload({ silent: true });
            }
        });
    }, [setData, toast, reload]);

    // Save pending taps when the tab is hidden or the card unmounts.
    useEffect(() => {
        const onHide = () => document.visibilityState === 'hidden' && flush();
        document.addEventListener('visibilitychange', onHide);
        return () => {
            document.removeEventListener('visibilitychange', onHide);
            flush();
        };
    }, [flush]);

    if (!data && loading) {
        return (
            <Card className="card-pad" aria-busy>
                <div className="flex items-center gap-4">
                    <Skeleton className="h-15 w-15 rounded-full" />
                    <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-1/3" />
                        <Skeleton className="h-8 w-full" />
                    </div>
                </div>
                <Skeleton className="mt-5 h-11 w-full" />
                <Skeleton className="mt-3 h-11 w-full" />
                <Skeleton className="mt-3 h-11 w-full" />
            </Card>
        );
    }
    if (!data) {
        return (
            <Card className="card-pad">
                <Empty icon={GlassWater} title="Couldn't load your body log" action={<Button size="sm" icon={RefreshCw} onClick={() => reload()}>Retry</Button>}>
                    {error}
                </Empty>
            </Card>
        );
    }

    const t = data.targets || { sleep: 7.5, water: 8, exercise: 30 };
    const today = derive(data.data, t, data.weights);
    const history = data.history || [];
    const streaks = data.streaks || {};
    const water = today.water_glasses || 0;
    const sleep = today.sleep_hours;
    const exercise = today.exercise_min || 0;

    const change = (fields) => {
        buzz();
        setData((d) => (d ? withToday(d, derive({ ...d.data, ...fields }, d.targets || t, d.weights)) : d));
        Object.assign(queued.current, fields);
        clearTimeout(timer.current);
        timer.current = setTimeout(flush, DEBOUNCE_MS);
    };

    const setWater = (n) => {
        const v = clamp(n, 0, 40);
        if (v !== water) change({ water_glasses: v });
    };
    const stepSleep = (delta) => {
        const base = sleep ?? t.sleep;
        const v = clamp(Math.round((sleep == null ? base : base + delta) * 2) / 2, 0, 24);
        if (v !== sleep) change({ sleep_hours: v });
    };
    const addExercise = (n) => {
        const v = clamp(exercise + n, 0, 1440);
        if (v !== exercise) change({ exercise_min: v });
    };

    const slots = Math.min(Math.max(t.water, water), MAX_GLASS_ICONS);
    const overflow = water - slots;
    const flames = STREAKS.filter(([k]) => (streaks[k] || 0) > 0);
    const askSleep = sleep == null && (data.hour ?? 12) < 14;

    return (
        <Card className="card-pad">
            {/* score + trend + streaks */}
            <div className="flex items-center gap-4">
                <ProgressRing value={today.score} max={100} size={60} stroke={6}>
                    <span className="text-lg font-bold tabular-nums leading-none">{today.score}</span>
                </ProgressRing>
                <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-baseline justify-between gap-2">
                        <h2 className="text-[15px] font-semibold tracking-tight">Body</h2>
                        <span className="eyebrow">7 days</span>
                    </div>
                    <Sparkline values={history.map((h) => h.score)} />
                </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                {flames.length ? flames.map(([k, label]) => (
                    <span key={k} className="inline-flex items-center gap-1">
                        <Flame className="h-3.5 w-3.5 text-accent" aria-hidden />
                        <span className="font-semibold tabular-nums text-fg">{streaks[k]}</span>{label}
                    </span>
                )) : (
                    <span className="inline-flex items-center gap-1 text-subtle"><Flame className="h-3.5 w-3.5" aria-hidden />Hit a target today to start a streak</span>
                )}
            </div>

            <div className="mt-3 divide-y divide-line">
                {/* water */}
                <div className="py-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 text-[13px] font-medium">
                            <GlassWater className="h-4 w-4 text-accent" aria-hidden />Water<MetDot on={today.met.water} />
                        </span>
                        <span className="text-xs tabular-nums text-subtle">
                            <span className="font-semibold text-fg">{water}</span>/{t.water} glasses
                        </span>
                    </div>
                    <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${Math.min(slots, 8)}, minmax(0, 1fr))` }}>
                        {Array.from({ length: slots }, (_, i) => {
                            const full = i < water;
                            return (
                                <PressButton
                                    key={i}
                                    onTap={() => setWater(water + 1)}
                                    onLong={() => setWater(water - 1)}
                                    aria-label={`Water: ${water} of ${t.water}. Tap to add a glass, hold to remove one`}
                                    title="Tap to add · hold or right-click to remove"
                                    className={cx(
                                        'grid h-11 place-items-center rounded-xl transition-[background,color,transform] duration-150 active:scale-90',
                                        'focus-visible:outline-2 focus-visible:outline-accent',
                                        full ? 'bg-accent-soft text-accent' : 'text-line-strong hover:bg-surface-2 hover:text-subtle',
                                    )}
                                >
                                    <GlassWater className={cx('h-5 w-5', full && 'fill-accent/25')} aria-hidden />
                                </PressButton>
                            );
                        })}
                    </div>
                    {overflow > 0 && <p className="mt-1.5 text-right text-[11px] font-medium text-accent">+{overflow} more</p>}
                </div>

                {/* sleep */}
                <div className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                        <span className="flex items-center gap-1.5 text-[13px] font-medium">
                            <Moon className="h-4 w-4 text-muted" aria-hidden />Sleep<MetDot on={today.met.sleep} />
                        </span>
                        <span className={cx('block text-xs', askSleep ? 'font-medium text-accent' : 'text-subtle')}>
                            {askSleep ? 'How long did you sleep?' : `Last night · goal ${fmtH(t.sleep)}h`}
                        </span>
                    </div>
                    <div className="flex shrink-0 items-center rounded-xl border border-line bg-surface-2 p-0.5">
                        <button type="button" className="btn btn-ghost btn-icon h-10 w-10" onClick={() => stepSleep(-0.5)} disabled={sleep === 0} aria-label="Half an hour less sleep">
                            <Minus className="h-4 w-4" />
                        </button>
                        <span className={cx('w-14 text-center font-mono text-[15px] font-semibold tabular-nums', sleep == null && 'text-subtle')} aria-live="polite">
                            {sleep == null ? '–' : `${fmtH(sleep)}h`}
                        </span>
                        <button type="button" className="btn btn-ghost btn-icon h-10 w-10" onClick={() => stepSleep(0.5)} disabled={sleep === 24} aria-label="Half an hour more sleep">
                            <Plus className="h-4 w-4" />
                        </button>
                    </div>
                </div>

                {/* exercise */}
                <div className="flex items-center justify-between gap-3 pt-3">
                    <div className="min-w-0">
                        <span className="flex items-center gap-1.5 text-[13px] font-medium">
                            <Dumbbell className="h-4 w-4 text-muted" aria-hidden />Move<MetDot on={today.met.exercise} />
                        </span>
                        <span className="block text-xs tabular-nums text-subtle">
                            <span className="font-semibold text-fg">{exercise}</span>/{t.exercise} min
                        </span>
                    </div>
                    <div className="flex shrink-0 gap-1.5">
                        {[10, 20, 30].map((n) => (
                            <PressButton
                                key={n}
                                onTap={() => addExercise(n)}
                                onLong={() => addExercise(-n)}
                                aria-label={`Add ${n} minutes of exercise (hold to remove)`}
                                title="Tap to add · hold or right-click to remove"
                                className="chip h-10 px-3 font-mono text-[13px] active:scale-95"
                            >
                                +{n}
                            </PressButton>
                        ))}
                    </div>
                </div>
            </div>
        </Card>
    );
}
