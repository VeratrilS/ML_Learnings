import { useEffect, useRef, useState } from 'react';
import { Swords, Trophy } from 'lucide-react';
import { useApi, timeAgo } from '../lib/hooks';
import { haptic, play } from '../lib/sfx';
import { Card, CardHeader, DifficultyBadge, Skeleton, cx } from './ui';

const reducedMotion = () => {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
};

function usePoll(reload, ms, on) {
    useEffect(() => {
        if (!on) return undefined;
        const tick = () => { if (document.visibilityState === 'visible') reload({ silent: true }); };
        const id = setInterval(tick, ms);
        document.addEventListener('visibilitychange', tick);
        return () => { clearInterval(id); document.removeEventListener('visibilitychange', tick); };
    }, [reload, ms, on]);
}

function daysLeftText(b) {
    if (b.defeated) return b.ko_days ? `K.O. in ${b.ko_days} day${b.ko_days === 1 ? '' : 's'}` : 'K.O.';
    if (b.days_left <= 0) return 'Bout over';
    if (b.days_left === 1) return 'Final round today';
    return `${b.days_left} days left`;
}

export function DamageRow({ hit }) {
    return (
        <li className="flex items-center gap-2.5 min-w-0">
            <span className="w-11 shrink-0 text-right text-sm font-semibold tabular-nums text-hard">-{hit.dmg}</span>
            <span className="text-sm truncate flex-1 min-w-0">{hit.title}</span>
            {hit.kind === 'review'
                ? <span className="badge text-muted bg-surface-2">Review</span>
                : <DifficultyBadge value={hit.difficulty} />}
            <span className="text-[11px] text-subtle whitespace-nowrap tabular-nums hidden min-[400px]:inline">{timeAgo(hit.at)}</span>
        </li>
    );
}

/**
 * This week's boss: Ippo rival on your weakest topic, HP bar (shakes on new damage), last 3 hits.
 * Props: boss (optional /gym/boss data; fetched + polled every 60s when omitted), logLimit (3), className.
 */
export default function BossCard({ boss: external, logLimit = 3, className }) {
    const own = useApi(external === undefined ? '/gym/boss' : null);
    usePoll(own.reload, 60000, external === undefined);
    const b = external === undefined ? own.data : external;

    // On new damage the HP bar remounts at the HP we last saw (sessionStorage), then animates down.
    const [fromHp, setFromHp] = useState(null);
    const [hit, setHit] = useState(null); // { id, dmg }
    const timer = useRef(0);
    useEffect(() => () => clearTimeout(timer.current), []);

    useEffect(() => {
        if (!b) return undefined;
        const key = `gym:boss:${b.week_start}`;
        let prev = null;
        try { prev = sessionStorage.getItem(key); } catch { /* storage unavailable */ }
        try { sessionStorage.setItem(key, String(b.damage_total)); } catch { /* storage unavailable */ }
        const prevDmg = prev == null ? null : Number(prev);
        if (prevDmg == null || !(b.damage_total > prevDmg)) return undefined;
        const dmg = b.damage_total - prevDmg;
        let inner = 0;
        const outer = requestAnimationFrame(() => {
            setFromHp(Math.max(0, b.hp_max - prevDmg));
            setHit({ id: Date.now(), dmg });
            inner = requestAnimationFrame(() => setFromHp(null));
            clearTimeout(timer.current);
            timer.current = setTimeout(() => setHit(null), 1600);
            if (b.defeated && prevDmg < b.hp_max) { play('bell'); haptic([80, 60, 120]); }
            else { play(dmg >= 35 ? 'combo' : 'jab'); haptic(dmg >= 35 ? [30, 40, 30, 40, 30] : 35); }
        });
        return () => { cancelAnimationFrame(outer); cancelAnimationFrame(inner); };
    }, [b]);

    if (!b) {
        return (
            <Card className={cx('card-pad', className)}>
                <Skeleton className="h-4 w-40 mb-4" />
                {own.error && !own.loading
                    ? <p className="text-sm text-subtle">Couldn't load the boss. <button className="text-accent font-medium" onClick={() => own.reload()}>Retry</button></p>
                    : <><Skeleton className="h-3 w-full mb-4" /><Skeleton className="h-16 w-full" /></>}
            </Card>
        );
    }

    const hp = fromHp ?? b.hp;
    const pct = b.hp_max ? Math.max(0, Math.min(100, (hp / b.hp_max) * 100)) : 0;
    const log = (b.damage_log || []).slice(0, logLimit);
    const shake = hit && !reducedMotion();

    return (
        <Card className={cx('card-pad relative overflow-hidden', className)}>
            <CardHeader
                title="Boss fight"
                subtitle={`Week of ${new Date(b.week_start + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`}
                icon={Swords}
                action={<span className={cx('badge tabular-nums', b.defeated ? 'text-ok bg-ok/10' : b.days_left <= 1 ? 'text-hard bg-hard/10' : 'text-muted bg-surface-2')}>{daysLeftText(b)}</span>}
            />

            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className={cx('text-xl font-semibold tracking-tight leading-tight', b.defeated && 'text-subtle line-through decoration-2 decoration-hard/70')}>{b.boss}</p>
                    <p className="text-[13px] text-muted mt-0.5">{b.topic}</p>
                </div>
                {b.defeated && (
                    <div className="shrink-0 flex items-center gap-1.5 rounded-xl bg-ok/10 text-ok px-2.5 py-1.5 animate-pop">
                        <Trophy className="h-4 w-4" aria-hidden />
                        <span className="text-sm font-bold tracking-wider">K.O.</span>
                    </div>
                )}
            </div>
            {b.tagline && <p className="text-xs text-subtle italic mt-2 leading-relaxed">{b.tagline}</p>}

            <div className="mt-4">
                <div className="flex items-baseline justify-between text-xs mb-1.5">
                    <span className="font-semibold uppercase tracking-[.12em] text-subtle">HP</span>
                    <span className="tabular-nums relative">
                        <span className="font-semibold">{b.hp}</span><span className="text-subtle">/{b.hp_max}</span>
                        {hit && (
                            <span key={hit.id} className="absolute right-0 -top-5 text-sm font-bold text-hard animate-pop" aria-live="polite">-{hit.dmg}</span>
                        )}
                    </span>
                </div>
                <div
                    key={hit?.id || 'bar'}
                    className={cx('relative h-3 rounded-full bg-surface-3 overflow-hidden', shake && 'animate-[shake_0.45s_ease-in-out]')}
                    role="meter" aria-valuemin={0} aria-valuemax={b.hp_max} aria-valuenow={b.hp} aria-label={`${b.boss} HP`}
                >
                    {/* Trailing "damage" layer catches up after the hit */}
                    <div className="absolute inset-y-0 left-0 rounded-full bg-hard/30" style={{ width: `${pct}%`, transition: 'width 1s cubic-bezier(.2,.7,.2,1) .45s' }} />
                    <div className={cx('absolute inset-y-0 left-0 rounded-full', b.defeated ? 'bg-subtle' : 'bg-hard')} style={{ width: `${pct}%`, transition: 'width .3s ease-out' }} />
                </div>
                <p className="text-[11px] text-subtle mt-1.5">
                    {b.defeated ? `${b.damage_total} damage dealt. Champion's work.` : `Solve ${b.topic} problems to land punches.`}
                </p>
            </div>

            <div className="mt-4">
                {log.length ? (
                    <ul className="space-y-2">
                        {log.map((h, i) => <DamageRow key={`${h.at}-${i}`} hit={h} />)}
                    </ul>
                ) : (
                    <p className="text-[13px] text-subtle">No punches landed yet this week.</p>
                )}
            </div>
        </Card>
    );
}
