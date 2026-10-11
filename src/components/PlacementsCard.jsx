import { useEffect, useMemo, useState } from 'react';
import { Briefcase, CalendarClock, Flag, Trophy, ArrowRight, Plus } from 'lucide-react';
import { useApi, navigate } from '../lib/hooks';
import { Card, CardHeader, Skeleton, cx } from './ui';

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const CLOSED = ['rejected', 'withdrawn'];

function span(ms) {
    const a = Math.abs(ms);
    if (a < HOUR) return `${Math.max(1, Math.round(a / MIN))}m`;
    if (a < 36 * HOUR) return `${Math.round(a / HOUR)}h`;
    return `${Math.round(a / DAY)}d`;
}

function daysUntil(ymd) {
    const [y, m, d] = String(ymd).split('-').map(Number);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((new Date(y, m - 1, d) - today) / DAY);
}

function useNow(intervalMs = 60_000) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), intervalMs);
        return () => clearInterval(id);
    }, [intervalMs]);
    return now;
}

// Rounds in the next 14 days + application deadlines in the next 7, soonest first.
function nextUp(apps, now) {
    const items = [];
    for (const a of apps) {
        if (CLOSED.includes(a.stage)) continue;
        if (a.next_event_at) {
            const t = new Date(a.next_event_at).getTime();
            if (t >= now - 2 * HOUR && t <= now + 14 * DAY) {
                items.push({ key: `e${a.id}`, kind: 'event', company: a.company, label: a.next_event_label || 'Next round', t, urgent: t - now < DAY });
            }
        }
        if (a.deadline && a.stage !== 'offer') {
            const n = daysUntil(a.deadline);
            if (n >= 0 && n <= 7) {
                const [y, m, d] = a.deadline.split('-').map(Number);
                items.push({ key: `d${a.id}`, kind: 'deadline', company: a.company, label: 'Deadline', t: new Date(y, m - 1, d, 23, 59).getTime(), n, urgent: n <= 2 });
            }
        }
    }
    return items.sort((x, y) => x.t - y.t);
}

function when(it, now) {
    if (it.kind === 'deadline') return it.n === 0 ? 'today' : it.n === 1 ? 'tomorrow' : `in ${it.n}d`;
    const ms = it.t - now;
    if (Math.abs(ms) < MIN) return 'now';
    return ms > 0 ? `in ${span(ms)}` : `${span(ms)} ago`;
}

export default function PlacementsCard() {
    const { data, loading, error } = useApi('/placements');
    const now = useNow();
    const apps = useMemo(() => data || [], [data]);
    const stats = useMemo(() => {
        const active = apps.filter((a) => ['applied', 'oa', 'interview', 'hr'].includes(a.stage)).length;
        const offers = apps.filter((a) => a.stage === 'offer').length;
        return { active, offers };
    }, [apps]);
    const upcoming = useMemo(() => nextUp(apps, now).slice(0, 3), [apps, now]);

    if (error && !data) return null; // the page itself surfaces errors; keep Today calm

    const open = () => navigate('placements');

    if (loading && !data) {
        return (
            <Card className="card-pad" aria-busy="true">
                <div className="flex items-center gap-2.5 mb-4">
                    <Skeleton className="h-8 w-8" />
                    <Skeleton className="h-4 w-32" />
                </div>
                <Skeleton className="h-10 mb-2" />
                <Skeleton className="h-10" />
            </Card>
        );
    }

    if (!apps.length) {
        return (
            <Card className="p-3.5 sm:p-4">
                <button type="button" onClick={open} className="w-full flex items-center gap-3 text-left group">
                    <div className="grid place-items-center h-9 w-9 rounded-xl bg-accent-soft text-accent shrink-0">
                        <Briefcase className="h-4 w-4" aria-hidden />
                    </div>
                    <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">Track your placements</p>
                        <p className="text-xs text-subtle truncate">Wishlist to offer, with OA and interview countdowns.</p>
                    </div>
                    <span className="btn btn-secondary btn-sm shrink-0 group-hover:border-line-strong">
                        <Plus className="h-3.5 w-3.5" aria-hidden />Start
                    </span>
                </button>
            </Card>
        );
    }

    return (
        <Card className="overflow-hidden">
            <div className="card-pad pb-0">
                <CardHeader
                    title="Placements"
                    subtitle={`${stats.active} active · ${stats.offers} ${stats.offers === 1 ? 'offer' : 'offers'}`}
                    icon={Briefcase}
                    action={
                        <button type="button" onClick={open} className="btn btn-ghost btn-sm">
                            Open pipeline <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                        </button>
                    }
                />
            </div>

            <div className="grid grid-cols-2 border-t border-line divide-x divide-line">
                <div className="px-4 py-3">
                    <div className="text-xl font-bold tabular-nums leading-none">{stats.active}</div>
                    <div className="text-[11px] text-subtle mt-1">In progress</div>
                </div>
                <div className="px-4 py-3 flex items-center gap-2">
                    <div className="min-w-0">
                        <div className={cx('text-xl font-bold tabular-nums leading-none', stats.offers && 'text-ok')}>{stats.offers}</div>
                        <div className="text-[11px] text-subtle mt-1">{stats.offers === 1 ? 'Offer' : 'Offers'}</div>
                    </div>
                    {stats.offers > 0 && <Trophy className="h-4 w-4 text-ok ml-auto" aria-hidden />}
                </div>
            </div>

            {upcoming.length ? (
                <ul className="border-t border-line divide-y divide-line">
                    {upcoming.map((it) => (
                        <li key={it.key}>
                            <button type="button" onClick={open} className="w-full flex items-center gap-3 px-4 py-2.5 text-left row-hover">
                                {it.kind === 'deadline'
                                    ? <Flag className={cx('h-4 w-4 shrink-0', it.urgent ? 'text-danger' : 'text-subtle')} aria-hidden />
                                    : <CalendarClock className={cx('h-4 w-4 shrink-0', it.urgent ? 'text-accent' : 'text-subtle')} aria-hidden />}
                                <p className="min-w-0 flex-1 text-sm truncate">
                                    <span className="font-medium">{it.company}</span>
                                    <span className="text-muted"> · {it.label}</span>
                                </p>
                                <span className={cx(
                                    'text-xs font-semibold tabular-nums shrink-0',
                                    it.urgent ? (it.kind === 'deadline' ? 'text-danger' : 'text-accent') : 'text-muted',
                                )}>
                                    {when(it, now)}
                                </span>
                            </button>
                        </li>
                    ))}
                </ul>
            ) : (
                <p className="border-t border-line px-4 py-3 text-xs text-subtle">No rounds or deadlines this fortnight.</p>
            )}
        </Card>
    );
}
