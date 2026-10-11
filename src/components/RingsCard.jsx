import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, CircleDot, GraduationCap, HeartPulse, Tv } from 'lucide-react';
import { useApi } from '../lib/hooks';
import { haptic, play } from '../lib/sfx';
import { Card, CardHeader, Skeleton, cx } from './ui';

const TONES = {
    solve: { text: 'text-accent', dot: 'bg-accent' },
    study: { text: 'text-ok', dot: 'bg-ok' },
    learn: { text: 'text-medium', dot: 'bg-medium' },
};
const toneOf = (key) => TONES[key] || TONES.solve;

// Ring geometry in viewBox units (scaled by CSS width)
const VB = 200;
const STROKE = 20;
const GAP = 4;
const radius = (i) => (VB - STROKE) / 2 - i * (STROKE + GAP);

const prefersReducedMotion = () => {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
};

function usePoll(reload, ms) {
    useEffect(() => {
        const tick = () => { if (document.visibilityState === 'visible') reload({ silent: true }); };
        const id = setInterval(tick, ms);
        document.addEventListener('visibilitychange', tick);
        return () => { clearInterval(id); document.removeEventListener('visibilitychange', tick); };
    }, [reload, ms]);
}

// Rings sweep in from zero on mount (CSS transition; reduced motion collapses it globally).
function useMounted() {
    const [ready, setReady] = useState(false);
    useEffect(() => {
        let inner = 0;
        const outer = requestAnimationFrame(() => { inner = requestAnimationFrame(() => setReady(true)); });
        return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner); };
    }, []);
    return ready;
}

export function Rings({ rings, closed, big, flash = [] }) {
    const ready = useMounted();
    const [reduced] = useState(prefersReducedMotion);
    return (
        <div className={cx('relative shrink-0 aspect-square', big ? 'w-50 sm:w-58' : 'w-34')}>
            <svg viewBox={`0 0 ${VB} ${VB}`} className="w-full h-full -rotate-90" role="img"
                aria-label={rings.map((r) => `${r.label} ${Math.round(r.progress * 100)}%`).join(', ')}>
                {rings.map((r, i) => {
                    const rad = radius(i);
                    const c = 2 * Math.PI * rad;
                    const p = ready ? Math.max(0, Math.min(1, r.progress)) : 0;
                    const lit = flash.includes(r.key);
                    return (
                        <g key={r.key} className={toneOf(r.key).text}>
                            <circle cx={VB / 2} cy={VB / 2} r={rad} fill="none" stroke="currentColor" strokeOpacity={0.16} strokeWidth={STROKE} />
                            <circle
                                cx={VB / 2} cy={VB / 2} r={rad} fill="none" stroke="currentColor" strokeWidth={STROKE}
                                strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - p)}
                                opacity={p > 0 ? 1 : 0}
                                style={{
                                    transition: `stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1) ${reduced ? 0 : i * 140}ms, filter .4s ease`,
                                    filter: lit ? 'drop-shadow(0 0 7px currentColor)' : r.closed ? 'drop-shadow(0 0 3px currentColor)' : 'none',
                                }}
                            />
                        </g>
                    );
                })}
            </svg>
            <div className="absolute inset-0 grid place-items-center pointer-events-none">
                <div className="text-center leading-none">
                    <div className={cx('font-semibold tracking-tight tabular-nums', big ? 'text-3xl' : 'text-xl')}>
                        {closed}<span className="text-subtle">/3</span>
                    </div>
                    {big && <div className="text-[10px] uppercase tracking-[.14em] text-subtle mt-1">closed</div>}
                </div>
            </div>
        </div>
    );
}

const CONFETTI_TONES = ['bg-accent', 'bg-ok', 'bg-medium', 'bg-hard', 'bg-easy'];
const CONFETTI_CSS = `@keyframes gym-confetti {
  0% { transform: translate(-50%, -50%) rotate(0deg); opacity: 1; }
  45% { transform: translate(calc(-50% + var(--dx) * .7), calc(-50% + var(--dy))) rotate(calc(var(--r) * .5)); opacity: 1; }
  100% { transform: translate(calc(-50% + var(--dx)), calc(-50% + var(--dy) + 160px)) rotate(var(--r)); opacity: 0; }
}`;

function Confetti({ burst }) {
    const pieces = useMemo(() => Array.from({ length: 28 }, (_, i) => {
        const a = (i / 28) * Math.PI * 2 + Math.random() * 0.4;
        const v = 70 + Math.random() * 90;
        return {
            dx: Math.cos(a) * v, dy: Math.sin(a) * v * 0.8 - 50, r: (Math.random() - 0.5) * 720,
            d: 1100 + Math.random() * 600, delay: Math.random() * 120,
            tone: CONFETTI_TONES[i % CONFETTI_TONES.length], w: 5 + Math.random() * 4, h: 3 + Math.random() * 6,
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }), [burst]);
    return (
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden z-10">
            <style>{CONFETTI_CSS}</style>
            {pieces.map((p, i) => (
                <span
                    key={`${burst}-${i}`}
                    className={cx('absolute left-1/2 top-[45%] rounded-[1px]', p.tone)}
                    style={{
                        width: p.w, height: p.h, '--dx': `${p.dx}px`, '--dy': `${p.dy}px`, '--r': `${p.r}deg`,
                        animation: `gym-confetti ${p.d}ms cubic-bezier(.2,.6,.35,1) ${p.delay}ms both`,
                    }}
                />
            ))}
        </div>
    );
}

function Legend({ rings, flash }) {
    return (
        <ul className="flex-1 w-full min-w-0 space-y-3">
            {rings.map((r) => {
                const t = toneOf(r.key);
                return (
                    <li key={r.key} className={cx('flex items-center gap-3', flash.includes(r.key) && 'animate-pop')}>
                        <span className={cx('h-2.5 w-2.5 rounded-full shrink-0', t.dot)} aria-hidden />
                        <div className="min-w-0 flex-1">
                            <div className="flex items-baseline justify-between gap-2">
                                <span className="text-sm font-medium">{r.label}</span>
                                <span className="text-sm tabular-nums whitespace-nowrap">
                                    <span className="font-semibold">{r.value}</span>
                                    <span className="text-subtle">/{r.goal} {r.unit}</span>
                                </span>
                            </div>
                            <p className="text-xs text-subtle truncate">{r.detail}</p>
                        </div>
                        <span className={cx('grid place-items-center h-5 w-5 rounded-full shrink-0 transition-all',
                            r.closed ? cx(t.dot, 'text-white scale-100') : 'border border-line-strong scale-90')}>
                            {r.closed && <Check className="h-3 w-3" strokeWidth={3.5} aria-label="closed" />}
                        </span>
                    </li>
                );
            })}
        </ul>
    );
}

/**
 * Today's three rings (Solve / Study / Learn). Polls every 60s; a ring that closes since the last
 * look (sessionStorage) plays a combo, all three closing rings the bell and throws confetti.
 * Props: big (larger rings for the Gym page), className.
 */
export default function RingsCard({ big = false, className }) {
    const { data, error, loading, reload } = useApi('/gym/rings');
    usePoll(reload, 60000);
    const [flash, setFlash] = useState([]);
    const [burst, setBurst] = useState(0);
    const timers = useRef([]);
    useEffect(() => () => timers.current.forEach(clearTimeout), []);

    useEffect(() => {
        if (!data?.rings) return;
        const key = `gym:rings:${data.date}`;
        const now = data.rings.filter((r) => r.closed).map((r) => r.key);
        let prev = null;
        try { prev = JSON.parse(sessionStorage.getItem(key) || 'null'); } catch { /* storage unavailable */ }
        try { sessionStorage.setItem(key, JSON.stringify(now)); } catch { /* storage unavailable */ }
        if (!Array.isArray(prev)) return; // first look this session: just remember
        const fresh = now.filter((k) => !prev.includes(k));
        if (!fresh.length) return;
        const allNow = data.all_closed && prev.length < 3;
        if (allNow) { play('bell'); haptic([70, 90, 70]); } else { play('combo'); haptic(40); }
        // Visual celebration on the next frame (keeps state updates out of the effect body)
        const frame = requestAnimationFrame(() => {
            setFlash(fresh);
            timers.current.push(setTimeout(() => setFlash([]), 2200));
            if (allNow && !prefersReducedMotion()) {
                setBurst((b) => b + 1);
                timers.current.push(setTimeout(() => setBurst(0), 2200));
            }
        });
        return () => cancelAnimationFrame(frame);
    }, [data]);

    if (!data) {
        return (
            <Card className={cx('card-pad', className)}>
                <Skeleton className="h-4 w-32 mb-5" />
                {error && !loading ? (
                    <p className="text-sm text-subtle">Couldn't load rings. <button className="text-accent font-medium" onClick={() => reload()}>Retry</button></p>
                ) : (
                    <div className="flex items-center gap-5">
                        <Skeleton className={cx('rounded-full shrink-0', big ? 'size-50' : 'size-34')} />
                        <div className="flex-1 space-y-3"><Skeleton className="h-8" /><Skeleton className="h-8" /><Skeleton className="h-8" /></div>
                    </div>
                )}
            </Card>
        );
    }

    const left = 3 - data.closed;
    const subtitle = data.all_closed ? 'All three closed. Ding ding!' : `${left} ring${left === 1 ? '' : 's'} to close today`;

    return (
        <Card className={cx('card-pad relative overflow-hidden', data.all_closed && 'hero-accent', className)}>
            {burst > 0 && <Confetti burst={burst} />}
            <CardHeader
                title="Rings"
                subtitle={subtitle}
                icon={CircleDot}
                action={data.earned_episode && (
                    <span className="badge text-ok bg-ok/10" title="Solve ring closed (or exam day): tonight's episode is yours">
                        <Tv className="h-3 w-3" aria-hidden /> Episode earned
                    </span>
                )}
            />
            {(data.recovery || data.exam_day) && (
                <div className="flex flex-wrap gap-1.5 -mt-1 mb-4">
                    {data.recovery && (
                        <span className="badge text-medium bg-medium/10" title="Yesterday broke the streak, so today's goals are halved. Get back in the ring.">
                            <HeartPulse className="h-3 w-3" aria-hidden /> Recovery round · goals halved
                        </span>
                    )}
                    {data.exam_day && (
                        <span className="badge text-accent bg-accent-soft" title="Exam day: Solve 1, Study 120 min">
                            <GraduationCap className="h-3 w-3" aria-hidden /> Exam day
                        </span>
                    )}
                </div>
            )}
            <div className={cx('flex flex-col sm:flex-row items-center', big ? 'gap-6 sm:gap-8' : 'gap-5')}>
                <Rings rings={data.rings} closed={data.closed} big={big} flash={flash} />
                <Legend rings={data.rings} flash={flash} />
            </div>
        </Card>
    );
}
