import { useEffect, useRef, useState } from 'react';
import { HandFist, Medal, Trophy, Crown, Zap } from 'lucide-react';
import { useApi } from '../lib/hooks';
import { Card, ProgressBar, Skeleton, cx } from './ui';

const RANKS = ['Rookie', 'C-Class', 'B-Class', 'A-Class', 'Japanese Champion', 'OPBF Champion', 'World Champion'];
const LAST_RANK_KEY = 'xp:lastRank';

function RankIcon({ rank, ...props }) {
    const i = RANKS.indexOf(rank);
    if (i >= 6) return <Crown {...props} />;
    if (i >= 4) return <Trophy {...props} />;
    if (i >= 2) return <Medal {...props} />;
    return <HandFist {...props} />;
}

const fmt = (n) => Number(n || 0).toLocaleString();

/**
 * Rank pill + thin XP bar.
 * - `data`: the /api/xp payload. Leave undefined to let the badge fetch it itself.
 * - `variant`: 'pill' (sidebar footer) or 'tile' (a card on Today).
 */
export default function RankBadge({ data, variant = 'pill', className }) {
    const own = useApi(data === undefined ? '/xp' : null);
    const xp = data === undefined ? own.data : data;

    if (variant === 'tile') return <RankTile xp={xp} className={className} />;

    if (!xp) return <Skeleton className={cx('h-11 w-full rounded-xl', className)} />;
    const pct = Math.round((xp.progress || 0) * 100);
    return (
        <div
            className={cx('rounded-xl border border-line bg-surface-2/60 px-2.5 py-2', className)}
            title={xp.next_rank ? `${fmt(xp.xp)} XP · ${fmt(xp.xp_to_next)} to ${xp.next_rank}` : `${fmt(xp.xp)} XP · top rank`}
        >
            <div className="flex items-center gap-2 min-w-0">
                <span className="grid place-items-center h-6 w-6 rounded-lg bg-accent-soft text-accent shrink-0">
                    <RankIcon rank={xp.rank} className="h-3.5 w-3.5" />
                </span>
                <span className="text-[13px] font-semibold truncate flex-1">{xp.rank}</span>
                <span className="text-[11px] text-subtle tabular-nums shrink-0">{fmt(xp.xp)} XP</span>
            </div>
            <ProgressBar value={pct} className="mt-2 h-1" />
        </div>
    );
}

function RankTile({ xp, className }) {
    if (!xp) return <Skeleton className={cx('h-[132px] rounded-2xl', className)} />;
    const pct = Math.round((xp.progress || 0) * 100);
    const top = Object.entries(xp.breakdown || {})
        .filter(([, v]) => v.xp > 0)
        .sort((a, b) => b[1].xp - a[1].xp)
        .slice(0, 3);
    return (
        <Card className={cx('card-pad', className)}>
            <div className="flex items-start gap-3">
                <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0">
                    <RankIcon rank={xp.rank} className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                    <div className="eyebrow">Rank</div>
                    <div className="text-[17px] font-bold tracking-tight truncate">{xp.rank}</div>
                </div>
                {xp.today_xp > 0 && (
                    <span className="badge bg-accent-soft text-accent shrink-0" title="XP earned today">
                        <Zap className="h-3 w-3" /> +{fmt(xp.today_xp)}
                    </span>
                )}
            </div>
            <ProgressBar value={pct} className="mt-4" />
            <div className="mt-2 flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold tabular-nums">{fmt(xp.xp)} XP</span>
                <span className="text-subtle truncate">
                    {xp.next_rank ? <>{fmt(xp.xp_to_next)} to <span className="text-muted font-medium">{xp.next_rank}</span></> : 'Top of the world'}
                </span>
            </div>
            {top.length > 0 && (
                <div className="mt-3 pt-3 border-t border-line flex flex-wrap gap-x-3 gap-y-1">
                    {top.map(([k, v]) => (
                        <span key={k} className="text-[11.5px] text-subtle">
                            {v.label} <span className="text-muted font-semibold tabular-nums">{fmt(v.xp)}</span>
                        </span>
                    ))}
                </div>
            )}
        </Card>
    );
}

const readLastRank = () => { try { return localStorage.getItem(LAST_RANK_KEY); } catch { return null; } };
const writeLastRank = (r) => { try { localStorage.setItem(LAST_RANK_KEY, r); } catch { /* storage unavailable */ } };

/**
 * One-time full-screen celebration when the rank goes up (compared with the last rank seen on this device).
 * Mount once (App does it); the first visit just records the current rank silently.
 */
export function RankUpOverlay({ data }) {
    const [shown, setShown] = useState(null);
    const btnRef = useRef(null);
    const rank = data?.rank;

    useEffect(() => {
        if (!rank) return;
        const last = readLastRank();
        const up = last && RANKS.indexOf(rank) > RANKS.indexOf(last);
        if (up) setShown(rank);
        else if (last !== rank) writeLastRank(rank); // first visit, or XP went down: record quietly
    }, [rank]);

    useEffect(() => {
        if (!shown) return;
        btnRef.current?.focus();
        const onKey = (e) => e.key === 'Escape' && close();
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [shown]);

    const close = () => { writeLastRank(shown); setShown(null); };

    if (!shown) return null;
    return (
        <div className="fixed inset-0 z-[90] grid place-items-center p-6" role="dialog" aria-modal="true" aria-labelledby="rankup-title">
            <div className="absolute inset-0 bg-bg/85 backdrop-blur-md animate-fade" onClick={close} />
            <div className="relative w-full max-w-sm text-center animate-pop">
                <div className="relative mx-auto grid place-items-center h-20 w-20">
                    <div aria-hidden className="absolute inset-0 rounded-full bg-accent opacity-25 blur-2xl animate-glow" />
                    <div className="relative grid place-items-center h-16 w-16 rounded-2xl bg-accent text-accent-fg shadow-[0_10px_40px_-10px_var(--accent)]">
                        <RankIcon rank={shown} className="h-8 w-8" strokeWidth={2.2} />
                    </div>
                </div>
                <div className="eyebrow mt-6 text-accent">New rank</div>
                <h2 id="rankup-title" className="mt-1.5 text-3xl sm:text-4xl font-extrabold tracking-tight">{shown}</h2>
                {data?.next_rank && (
                    <p className="mt-2 text-sm text-subtle">{fmt(data.xp_to_next)} XP to {data.next_rank}</p>
                )}
                <blockquote className="mt-6 text-[15px] leading-relaxed text-muted italic">
                    “Not everyone who works hard is rewarded. But all those who succeed have worked hard.”
                    <footer className="mt-1.5 not-italic text-xs text-subtle">Kamogawa Genji</footer>
                </blockquote>
                <button ref={btnRef} onClick={close} className="btn btn-primary btn-lg mt-7 w-full sm:w-auto sm:min-w-40">
                    Back to training
                </button>
            </div>
        </div>
    );
}
