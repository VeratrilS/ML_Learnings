import { useEffect, useMemo, useState } from 'react';
import { Trophy, CalendarPlus, ExternalLink, Radio, Clock, ChevronDown, RefreshCw } from 'lucide-react';
import { useApi, useLocalStorage } from '../lib/hooks';
import { Card, CardHeader, Empty, Segmented, Skeleton, cx } from './ui';

const PLATFORMS = {
    leetcode: { short: 'LC', label: 'LeetCode', color: '#FFA116' },
    codeforces: { short: 'CF', label: 'Codeforces', color: '#1F8ACB' },
};
const FILTERS = [
    { value: 'all', label: 'All' },
    { value: 'leetcode', label: 'LC' },
    { value: 'codeforces', label: 'CF' },
];
const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

// ---------- formatting ----------
function fmtSpan(ms) {
    const m = Math.max(0, Math.round(ms / MIN));
    const d = Math.floor(m / 1440);
    const h = Math.floor((m % 1440) / 60);
    const mm = m % 60;
    if (d) return h ? `${d}d ${h}h` : `${d}d`;
    if (h) return mm ? `${h}h ${mm}m` : `${h}h`;
    return `${mm}m`;
}

function fmtStart(date, now) {
    const time = date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    const dayDiff = Math.round((startOfDay(date) - startOfDay(new Date(now))) / DAY);
    if (dayDiff === 0) return `Today ${time}`;
    if (dayDiff === 1) return `Tomorrow ${time}`;
    if (dayDiff > 0 && dayDiff < 7) return `${date.toLocaleDateString(undefined, { weekday: 'short' })} ${time}`;
    return `${date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}, ${time}`;
}

function startOfDay(d) {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x.getTime();
}

// ---------- .ics ----------
const icsDate = (d) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
const icsText = (s) => String(s).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');

// RFC 5545: lines longer than 75 octets are folded with CRLF + space.
function fold(line) {
    const enc = new TextEncoder();
    if (enc.encode(line).length <= 75) return line;
    const out = [];
    let cur = '';
    for (const ch of line) {
        if (enc.encode(cur + ch).length > (out.length ? 74 : 75)) {
            out.push(cur);
            cur = '';
        }
        cur += ch;
    }
    out.push(cur);
    return out.join('\r\n ');
}

function downloadIcs(c) {
    const start = new Date(c.start);
    const end = new Date(start.getTime() + (c.duration_seconds || 0) * 1000);
    const p = PLATFORMS[c.platform];
    const lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//ML_Fun//Contests//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VEVENT',
        `UID:${c.platform}-${start.getTime() / 1000}-${encodeURIComponent(c.name).slice(0, 40)}@ml-fun`,
        `DTSTAMP:${icsDate(new Date())}`,
        `DTSTART:${icsDate(start)}`,
        `DTEND:${icsDate(end)}`,
        `SUMMARY:${icsText(`${c.name} (${p?.label || c.platform})`)}`,
        `URL:${c.url}`,
        `DESCRIPTION:${icsText(c.register_url && c.register_url !== c.url ? `Register: ${c.register_url}\nContest: ${c.url}` : c.url)}`,
        `LOCATION:${icsText(c.url)}`,
        'BEGIN:VALARM',
        'ACTION:DISPLAY',
        `DESCRIPTION:${icsText(`${c.name} starts in 15 minutes`)}`,
        'TRIGGER:-PT15M',
        'END:VALARM',
        'END:VEVENT',
        'END:VCALENDAR',
    ];
    const blob = new Blob([lines.map(fold).join('\r\n') + '\r\n'], { type: 'text/calendar;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = href;
    a.download = `${c.name.replace(/[^\w-]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'contest'}.ics`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
}

// ---------- pieces ----------
function PlatformMark({ platform }) {
    const p = PLATFORMS[platform] || { short: '?', color: '#8a8a94' };
    return (
        <div
            className="grid place-items-center h-9 w-9 rounded-[10px] text-[11px] font-bold tracking-tight shrink-0 select-none"
            style={{
                color: `color-mix(in srgb, ${p.color} 78%, var(--fg))`,
                background: `color-mix(in srgb, ${p.color} 14%, transparent)`,
                boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${p.color} 28%, transparent)`,
            }}
            title={p.label}
            aria-hidden
        >
            {p.short}
        </div>
    );
}

function Countdown({ contest, now }) {
    if (contest.running) {
        return (
            <span className="badge text-danger bg-danger/10">
                <Radio className="h-3 w-3 animate-pulse" aria-hidden />
                LIVE · ends in {fmtSpan(contest.endMs - now)}
            </span>
        );
    }
    const ms = contest.startMs - now;
    if (ms < MIN) return <span className="font-semibold text-accent">starting now</span>;
    return (
        <span className={cx('tabular-nums', ms < HOUR ? 'font-semibold text-accent' : 'text-muted font-medium')}>
            in {fmtSpan(ms)}
        </span>
    );
}

function ContestRow({ c, now, index }) {
    const start = new Date(c.startMs);
    const p = PLATFORMS[c.platform];
    return (
        <li
            className="animate-rise flex items-start gap-3 px-3 sm:px-4 py-3 row-hover"
            style={{ animationDelay: `${Math.min(index, 8) * 30}ms` }}
        >
            <PlatformMark platform={c.platform} />
            <div className="min-w-0 flex-1 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                <div className="min-w-0 flex-1 basis-[13rem]">
                    <a
                        href={c.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm font-medium leading-snug line-clamp-2 break-words hover:text-accent transition-colors"
                        title={`${c.name} — open on ${p?.label || c.platform}`}
                    >
                        {c.name}
                    </a>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-subtle">
                        <time dateTime={c.start} title={start.toLocaleString()} className="whitespace-nowrap">
                            {fmtStart(start, now)}
                        </time>
                        <span aria-hidden className="text-line-strong">·</span>
                        <Countdown contest={c} now={now} />
                        {c.duration_seconds > 0 && (
                            <>
                                <span aria-hidden className="text-line-strong">·</span>
                                <span className="inline-flex items-center gap-1 whitespace-nowrap">
                                    <Clock className="h-3 w-3" aria-hidden />
                                    {fmtSpan(c.duration_seconds * 1000)}
                                </span>
                            </>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-0.5 shrink-0 ml-auto -mr-1">
                    {c.running ? (
                        <a href={c.url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm text-danger hover:text-danger">
                            Join <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                        </a>
                    ) : (
                        <>
                            {c.platform === 'codeforces' && c.register_url && (
                                <a href={c.register_url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
                                    Register <ExternalLink className="h-3.5 w-3.5 opacity-70" aria-hidden />
                                </a>
                            )}
                            <button
                                type="button"
                                onClick={() => downloadIcs(c)}
                                className="btn btn-ghost btn-sm btn-icon"
                                aria-label={`Add ${c.name} to calendar`}
                                title="Add to calendar (.ics)"
                            >
                                <CalendarPlus className="h-4 w-4" aria-hidden />
                            </button>
                        </>
                    )}
                </div>
            </div>
        </li>
    );
}

function useNow(intervalMs = 30_000) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), intervalMs);
        return () => clearInterval(id);
    }, [intervalMs]);
    return now;
}

// ---------- card ----------
export default function ContestsCard({ limit = 5 }) {
    const { data, loading, error, reload } = useApi('/contests', {
        select: (d) => ({ items: d.data || [], errors: d.errors || [] }),
    });
    const [storedFilter, setFilter] = useLocalStorage('contests.filter', 'all');
    const filter = FILTERS.some((f) => f.value === storedFilter) ? storedFilter : 'all';
    const [expanded, setExpanded] = useState(false);
    const now = useNow();

    const contests = useMemo(() => (data?.items || [])
        .map((c) => {
            const startMs = new Date(c.start).getTime();
            const endMs = startMs + (c.duration_seconds || 0) * 1000;
            return { ...c, startMs, endMs, running: startMs <= now && now < endMs };
        })
        .filter((c) => Number.isFinite(c.startMs) && c.endMs > now)
        .sort((a, b) => a.startMs - b.startMs), [data, now]);

    const visible = filter === 'all' ? contests : contests.filter((c) => c.platform === filter);
    const shown = expanded ? visible : visible.slice(0, limit);
    const next = contests.find((c) => !c.running);
    const live = contests.filter((c) => c.running).length;
    let subtitle = 'LeetCode · Codeforces';
    if (live) subtitle = `${live} live now`;
    else if (next) subtitle = next.startMs - now < MIN ? 'Next starting now' : `Next in ${fmtSpan(next.startMs - now)}`;

    return (
        <Card className="overflow-hidden">
            <div className="card-pad pb-0">
                <CardHeader
                    title="Upcoming contests"
                    subtitle={data ? subtitle : 'LeetCode · Codeforces'}
                    icon={Trophy}
                    className="flex-wrap"
                    action={<Segmented options={FILTERS} value={filter} onChange={(v) => { setFilter(v); setExpanded(false); }} />}
                />
            </div>

            {loading && !data ? (
                <ul className="border-t border-line divide-y divide-line" aria-busy="true">
                    {Array.from({ length: Math.min(limit, 3) }).map((_, i) => (
                        <li key={i} className="flex items-center gap-3 px-3 sm:px-4 py-3">
                            <Skeleton className="h-9 w-9 rounded-[10px] shrink-0" />
                            <div className="flex-1 space-y-2 min-w-0">
                                <Skeleton className="h-3.5 w-3/4" />
                                <Skeleton className="h-3 w-1/2" />
                            </div>
                        </li>
                    ))}
                </ul>
            ) : error && !data ? (
                <div className="border-t border-line">
                    <Empty
                        icon={Trophy}
                        title="Couldn't load contests"
                        action={<button type="button" className="btn btn-secondary btn-sm" onClick={() => reload()}><RefreshCw className="h-3.5 w-3.5" aria-hidden />Retry</button>}
                    >
                        {error}
                    </Empty>
                </div>
            ) : visible.length ? (
                <ul className="border-t border-line divide-y divide-line">
                    {shown.map((c, i) => <ContestRow key={`${c.platform}-${c.url}`} c={c} now={now} index={i} />)}
                </ul>
            ) : (
                <div className="border-t border-line">
                    <Empty icon={Trophy} title="No contests in the next 30 days">
                        {filter !== 'all' && contests.length ? `Nothing on ${PLATFORMS[filter].label} — try All.` : null}
                    </Empty>
                </div>
            )}

            {(visible.length > limit || data?.errors?.length > 0) && (
                <div className="flex items-center gap-3 px-3 sm:px-4 py-2 border-t border-line bg-surface-2/40 min-w-0">
                    {data?.errors?.length > 0 && (
                        <p className="text-xs text-subtle truncate min-w-0 flex-1" title={data.errors.join('\n')}>
                            {data.errors.join(' · ')}
                        </p>
                    )}
                    {visible.length > limit && (
                        <button
                            type="button"
                            className="btn btn-ghost btn-sm ml-auto shrink-0"
                            onClick={() => setExpanded((v) => !v)}
                            aria-expanded={expanded}
                        >
                            {expanded ? 'Show less' : `Show all (${visible.length})`}
                            <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} aria-hidden />
                        </button>
                    )}
                </div>
            )}
        </Card>
    );
}
