import { useEffect, useMemo, useRef, useState } from 'react';
import {
    Apple, CalendarClock, CircleCheck, ExternalLink, Flag, Gauge, Hourglass, ListOrdered, RotateCw, Target, TrendingUp,
    TriangleAlert, X,
} from 'lucide-react';
import { useApi, useLocalStorage } from '../lib/hooks';
import { Button, Card, CardHeader, DifficultyBadge, Empty, Skeleton, cx } from '../components/ui';

// ---- Day arithmetic on 'YYYY-MM-DD' strings (UTC day numbers, no DST surprises) ----
const DAY = 86400000;
const toNum = (iso) => Math.round(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / DAY);
const toIso = (n) => new Date(n * DAY).toISOString().slice(0, 10);
const fmt = (n, opts = { day: 'numeric', month: 'short' }) =>
    new Date(n * DAY).toLocaleDateString('en-GB', { ...opts, timeZone: 'UTC' });
const fmtFull = (n) => fmt(n, { day: 'numeric', month: 'short', year: 'numeric' });
// ISO UTC timestamp -> IST calendar day (fallback when done_day is missing)
const istDay = (iso) => new Date(new Date(iso).getTime() + 5.5 * 3600000).toISOString().slice(0, 10);
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const one = (x) => (Math.round(x * 10) / 10).toFixed(1);

function addMonths(iso, k) {
    const y = +iso.slice(0, 4), m = +iso.slice(5, 7) - 1, d = +iso.slice(8, 10);
    const last = new Date(Date.UTC(y, m + k + 1, 0)).getUTCDate();
    return new Date(Date.UTC(y, m + k, Math.min(d, last))).toISOString().slice(0, 10);
}

const HORIZON = 365; // projections beyond this read "> 1 year"

/** Everything the page shows, derived from the sheet payload. */
function derive(data, deadline) {
    const today = toNum(data.day);
    const total = data.total || 0;
    const done = data.done || 0;
    const remaining = Math.max(0, total - done);

    // Solves per day; solves with no date at all count as a baseline before the first dated solve.
    const perDay = new Map();
    let baseline = 0;
    for (const p of data.problems || []) {
        if (!p.done) continue;
        const iso = p.done_day || (p.done_at ? istDay(p.done_at) : null);
        if (!iso) { baseline += 1; continue; }
        const n = Math.min(toNum(iso), today);
        perDay.set(n, (perDay.get(n) || 0) + 1);
    }
    const days = [...perDay.keys()].sort((a, b) => a - b);
    const first = days.length ? days[0] : today;

    const inLast = (k) => days.reduce((s, d) => s + (d > today - k ? perDay.get(d) : 0), 0);
    const pace14 = inLast(14) / 14;
    const pace7 = inLast(7) / 7;

    const projDays = remaining === 0 ? 0 : pace14 > 0 ? Math.ceil(remaining / pace14) : null;
    const finish = projDays == null ? null : today + projDays;

    const dl = deadline && /^\d{4}-\d{2}-\d{2}$/.test(deadline) ? toNum(deadline) : null;
    const dlDays = dl == null ? null : dl - today;
    const required = dlDays != null && dlDays > 0 ? remaining / dlDays : null;

    // Cumulative series: one point per day that had solves, plus the start and today.
    const series = [];
    let cum = baseline;
    if (!perDay.has(first)) series.push({ day: first, cum, added: 0 });
    for (const d of days) { cum += perDay.get(d); series.push({ day: d, cum, added: perDay.get(d) }); }
    if (series[series.length - 1].day !== today) series.push({ day: today, cum, added: 0 });

    // Weekly totals (Monday-start weeks), for the screen-reader table.
    const weeks = [];
    const monday = (n) => n - ((new Date(n * DAY).getUTCDay() + 6) % 7);
    let running = baseline;
    for (let w = monday(first); w <= today; w += 7) {
        let n = 0;
        for (let d = w; d < w + 7; d++) n += perDay.get(d) || 0;
        running += n;
        weeks.push({ start: w, solved: n, cum: running });
    }

    return { today, total, done, remaining, perDay, baseline, first, pace14, pace7, solved14: inLast(14), projDays, finish, dl, dlDays, required, series, weeks };
}

// ---------------- Pieces ----------------

function StatTile({ icon: Icon, label, value, small, children }) {
    return (
        <Card className="card-pad min-w-0">
            <div className="eyebrow flex items-start gap-1.5 leading-tight">
                <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden /> <span className="min-w-0">{label}</span>
            </div>
            <div className={cx('mt-2 leading-none font-bold tracking-tight tabular-nums wrap-break-word', small ? 'text-lg' : 'text-[28px]')}>{value}</div>
            <div className="mt-1.5 text-xs text-muted tabular-nums">{children}</div>
        </Card>
    );
}

function Status({ ok, children }) {
    const Icon = ok ? CircleCheck : TriangleAlert;
    return (
        <span className={cx('inline-flex items-center gap-1.5 text-sm font-semibold', ok ? 'text-ok' : 'text-danger')}>
            <Icon className="h-4 w-4 shrink-0" aria-hidden /> {children}
        </span>
    );
}

function Deadline({ data, m, deadline, setDeadline }) {
    const todayIso = data.day;
    const chips = [
        { label: '+2 weeks', value: toIso(m.today + 14) },
        { label: '+1 month', value: addMonths(todayIso, 1) },
        { label: '+2 months', value: addMonths(todayIso, 2) },
    ];
    const { Medium: med = { done: 0, total: 0 }, Hard: hard = { done: 0, total: 0 } } = data.by_difficulty || {};
    const left = [
        { d: 'Medium', n: Math.max(0, med.total - med.done), of: med.total },
        { d: 'Hard', n: Math.max(0, hard.total - hard.done), of: hard.total },
    ].filter((x) => x.of > 0);

    let verdict = null;
    if (m.remaining === 0) {
        verdict = <Status ok>Sheet complete</Status>;
    } else if (m.dl != null && m.dlDays <= 0) {
        verdict = <Status ok={false}>{m.dlDays === 0 ? 'Deadline is today' : 'Deadline has passed'}: pick a later date</Status>;
    } else if (m.required != null) {
        const gap = m.required - m.pace14;
        verdict = gap <= 1e-9
            ? <Status ok>On track</Status>
            : <Status ok={false}>Need +{one(Math.max(0.1, gap))}/day</Status>;
    }

    return (
        <Card className="card-pad min-w-0">
            <CardHeader title="Deadline" subtitle="What pace a target date needs" icon={Target} />
            <div className="flex flex-col sm:flex-row sm:items-end gap-3">
                <div className="min-w-0 sm:w-56">
                    <label htmlFor="pace-deadline" className="label">Finish by</label>
                    <div className="flex items-center gap-1.5">
                        <input
                            id="pace-deadline"
                            type="date"
                            className="input min-w-0"
                            min={toIso(m.today + 1)}
                            value={deadline}
                            onChange={(e) => setDeadline(e.target.value)}
                        />
                        {deadline && (
                            <Button size="icon" variant="ghost" icon={X} aria-label="Clear deadline" title="Clear deadline" onClick={() => setDeadline('')} />
                        )}
                    </div>
                </div>
                <div className="flex flex-wrap gap-2" role="group" aria-label="Quick deadlines">
                    {chips.map((c) => (
                        <button
                            key={c.label}
                            type="button"
                            aria-pressed={deadline === c.value}
                            onClick={() => setDeadline(c.value)}
                            className={cx('chip h-8', deadline === c.value && 'chip-on')}
                        >
                            {c.label}
                        </button>
                    ))}
                </div>
            </div>

            <dl className="mt-4 divide-y divide-line border-t border-line">
                <div className="flex items-start justify-between gap-3 py-2.5 text-sm">
                    <dt className="text-muted shrink-0">Required pace</dt>
                    <dd className="text-right font-medium tabular-nums">
                        {m.required != null
                            ? <>{one(m.required)}/day <span className="text-subtle font-normal">· {plural(m.remaining, 'problem')} in {plural(m.dlDays, 'day')}</span></>
                            : <span className="text-subtle font-normal">{m.remaining === 0 ? 'Nothing left' : 'Set a deadline'}</span>}
                    </dd>
                </div>
                <div className="flex items-start justify-between gap-3 py-2.5 text-sm">
                    <dt className="text-muted shrink-0">Current pace</dt>
                    <dd className="text-right font-medium tabular-nums">
                        {one(m.pace14)}/day <span className="text-subtle font-normal">· last 14 days</span>
                    </dd>
                </div>
                {verdict && (
                    <div className="flex items-center justify-between gap-3 py-2.5 text-sm">
                        <dt className="text-muted shrink-0">Status</dt>
                        <dd className="text-right min-w-0">{verdict}</dd>
                    </div>
                )}
                {left.length > 0 && (
                    <div className="flex items-start justify-between gap-3 py-2.5 text-sm">
                        <dt className="text-muted shrink-0">Remaining</dt>
                        <dd className="min-w-0 flex flex-wrap items-center justify-end gap-x-3 gap-y-1.5 text-right tabular-nums">
                            {left.map((x) => (
                                <span key={x.d} className="inline-flex items-center gap-1.5">
                                    <DifficultyBadge value={x.d} />
                                    <span className="font-medium">{x.n}</span>
                                    <span className="text-xs text-subtle">
                                        of {x.of}{m.required != null && x.n > 0 && m.remaining > 0 ? ` · ${one((m.required * x.n) / m.remaining)}/day` : ''}
                                    </span>
                                </span>
                            ))}
                        </dd>
                    </div>
                )}
            </dl>
        </Card>
    );
}

function useWidth(ref, fallback = 640) {
    const [w, setW] = useState(fallback);
    useEffect(() => {
        const el = ref.current;
        if (!el || typeof ResizeObserver === 'undefined') return undefined;
        const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
        ro.observe(el);
        return () => ro.disconnect();
    }, [ref]);
    return w;
}

function CurveChart({ m }) {
    const wrap = useRef(null);
    const W = useWidth(wrap);
    const H = W < 480 ? 200 : 240;
    const pad = { l: 34, r: 12, t: 12, b: 26 };
    const [hover, setHover] = useState(null); // day number under the cursor

    const total = Math.max(1, m.total);
    const projEnd = m.finish != null ? Math.min(m.finish, m.today + HORIZON) : null;
    const needEnd = m.dl != null && m.dlDays > 0 && m.remaining > 0 ? m.dl : null;
    const x0 = Math.min(m.first, m.today - 6);
    const x1 = Math.max(m.today + 7, projEnd ?? 0, needEnd ?? 0);

    const x = (d) => pad.l + ((d - x0) / (x1 - x0)) * (W - pad.l - pad.r);
    const y = (v) => pad.t + (1 - v / total) * (H - pad.t - pad.b);
    const dayAt = (px) => Math.round(x0 + ((px - pad.l) / (W - pad.l - pad.r)) * (x1 - x0));

    // Step line: flat until a solve day, then up.
    let line = `M${x(x0)},${y(m.baseline)}`;
    let prev = m.baseline;
    for (const p of m.series) {
        if (p.cum !== prev) { line += `H${x(p.day)}V${y(p.cum)}`; prev = p.cum; }
    }
    line += `H${x(m.today)}`;
    const area = `${line}V${y(0)}H${x(x0)}Z`;

    // Projection: straight line at the 14-day pace (clipped to the 1-year horizon).
    const proj = projEnd != null && m.remaining > 0
        ? { x2: x(projEnd), y2: y(Math.min(total, m.done + m.pace14 * (projEnd - m.today))) }
        : null;
    const need = needEnd != null ? { x2: x(needEnd), y2: y(total) } : null;

    // Value lookups for the readout.
    const cumAt = (d) => {
        let v = m.baseline;
        for (const p of m.series) { if (p.day <= d) v = p.cum; else break; }
        return v;
    };
    const readout = (d) => {
        const date = fmtFull(d);
        if (d <= m.today) {
            const added = m.perDay.get(d) || 0;
            return `${date}: ${cumAt(d)} solved${added ? ` (+${added} that day)` : ''}`;
        }
        const parts = [];
        if (proj && d <= projEnd) parts.push(`projected ${Math.min(m.total, Math.floor(m.done + m.pace14 * (d - m.today)))}`);
        if (need && d <= needEnd) parts.push(`needed ${Math.min(m.total, Math.ceil(m.done + m.required * (d - m.today)))}`);
        return `${date}: ${parts.length ? parts.join(' · ') : 'beyond the lines'}`;
    };
    const active = hover ?? m.today;
    const activeY = active <= m.today ? y(cumAt(active))
        : proj && active <= projEnd ? y(Math.min(total, m.done + m.pace14 * (active - m.today))) : null;

    // Axes
    const step = Math.max(10, Math.ceil(total / 3 / 10) * 10);
    const yTicks = [];
    for (let v = 0; v < total; v += step) if (total - v >= step * 0.4 || v === 0) yTicks.push(v);
    yTicks.push(total);
    const nx = W < 480 ? 3 : 5;
    const xTicks = [...new Set(Array.from({ length: nx }, (_, i) => Math.round(x0 + (i * (x1 - x0)) / (nx - 1))))];

    const onMove = (e) => {
        const r = e.currentTarget.getBoundingClientRect();
        const px = ((e.clientX - r.left) / r.width) * W;
        setHover(Math.max(x0, Math.min(x1, dayAt(px))));
    };
    const onKey = (e) => {
        const by = e.shiftKey ? 7 : 1;
        if (e.key === 'ArrowLeft') { e.preventDefault(); setHover((h) => Math.max(x0, (h ?? m.today) - by)); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); setHover((h) => Math.min(x1, (h ?? m.today) + by)); }
        else if (e.key === 'Escape') setHover(null);
    };

    const summary = `Cumulative Apple sheet problems solved, from ${fmtFull(m.first)} to today: ${m.done} of ${m.total}.`
        + (proj ? ` At ${one(m.pace14)} a day you finish ${m.projDays > HORIZON ? 'in more than a year' : `on ${fmtFull(m.finish)}`}.` : '')
        + (need ? ` Hitting the ${fmtFull(m.dl)} deadline needs ${one(m.required)} a day.` : '');

    return (
        <Card className="card-pad min-w-0">
            <CardHeader title="Cumulative solved" subtitle="Done so far, and where each pace lands" icon={TrendingUp} />

            <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted mb-2" aria-label="Legend">
                <li className="inline-flex items-center gap-1.5">
                    <svg width="18" height="6" aria-hidden><line x1="0" y1="3" x2="18" y2="3" stroke="var(--accent)" strokeWidth="2" /></svg>
                    Solved
                </li>
                {proj && (
                    <li className="inline-flex items-center gap-1.5">
                        <svg width="18" height="6" aria-hidden><line x1="0" y1="3" x2="18" y2="3" stroke="var(--accent)" strokeWidth="2" strokeDasharray="4 3" /></svg>
                        Projection ({one(m.pace14)}/day)
                    </li>
                )}
                {need && (
                    <li className="inline-flex items-center gap-1.5">
                        <svg width="18" height="6" aria-hidden><line x1="0" y1="3" x2="18" y2="3" stroke="var(--muted)" strokeWidth="2" strokeDasharray="2 3" /></svg>
                        Needed ({one(m.required)}/day)
                    </li>
                )}
            </ul>

            <p className="text-xs text-fg font-medium tabular-nums min-h-4 mb-1 truncate" aria-hidden>
                {readout(active)}
            </p>

            <div ref={wrap} className="w-full min-w-0">
                <svg
                    width={W}
                    height={H}
                    viewBox={`0 0 ${W} ${H}`}
                    className="block max-w-full touch-pan-y outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-md"
                    role="img"
                    aria-label={summary}
                    tabIndex={0}
                    onPointerMove={onMove}
                    onPointerLeave={() => setHover(null)}
                    onKeyDown={onKey}
                    onBlur={() => setHover(null)}
                >
                    {/* grid + y labels */}
                    {yTicks.map((v) => (
                        <g key={v}>
                            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth="1" />
                            <text x={pad.l - 6} y={y(v)} dy="0.32em" textAnchor="end" fontSize="10" fill="var(--subtle)" className="tabular-nums">{v}</text>
                        </g>
                    ))}
                    {/* x labels */}
                    {xTicks.map((d, i) => (
                        <text
                            key={d}
                            x={x(d)}
                            y={H - 8}
                            textAnchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'}
                            fontSize="10"
                            fill="var(--subtle)"
                        >
                            {fmt(d)}
                        </text>
                    ))}

                    <path d={area} fill="var(--accent-soft)" />
                    {need && (
                        <line x1={x(m.today)} y1={y(m.done)} x2={need.x2} y2={need.y2} stroke="var(--muted)" strokeWidth="2" strokeDasharray="2 4" strokeLinecap="round">
                            <title>{`Needed: ${one(m.required)}/day to finish by ${fmtFull(m.dl)}`}</title>
                        </line>
                    )}
                    {proj && (
                        <line x1={x(m.today)} y1={y(m.done)} x2={proj.x2} y2={proj.y2} stroke="var(--accent)" strokeWidth="2" strokeDasharray="5 4" strokeLinecap="round">
                            <title>{m.projDays > HORIZON ? `Projection at ${one(m.pace14)}/day: more than a year` : `Projection at ${one(m.pace14)}/day: done ${fmtFull(m.finish)}`}</title>
                        </line>
                    )}
                    <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />

                    {/* end-point labels */}
                    {proj && m.projDays <= HORIZON && (
                        <circle cx={proj.x2} cy={proj.y2} r="3.5" fill="var(--surface)" stroke="var(--accent)" strokeWidth="2">
                            <title>{`Projected finish ${fmtFull(m.finish)}`}</title>
                        </circle>
                    )}
                    {need && (
                        <circle cx={need.x2} cy={need.y2} r="3.5" fill="var(--surface)" stroke="var(--muted)" strokeWidth="2">
                            <title>{`Deadline ${fmtFull(m.dl)}`}</title>
                        </circle>
                    )}

                    {/* crosshair */}
                    <line x1={x(active)} x2={x(active)} y1={pad.t} y2={H - pad.b} stroke="var(--line-strong)" strokeWidth="1" />
                    {activeY != null && (
                        <circle cx={x(active)} cy={activeY} r="4.5" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />
                    )}
                </svg>
            </div>
            <p className="mt-2 text-[11px] text-subtle">Hover or focus the chart and use the arrow keys to read any day.</p>

            <table className="sr-only">
                <caption>Problems solved per week</caption>
                <thead><tr><th scope="col">Week of</th><th scope="col">Solved</th><th scope="col">Total so far</th></tr></thead>
                <tbody>
                    {m.weeks.map((w) => (
                        <tr key={w.start}><td>{fmtFull(w.start)}</td><td>{w.solved}</td><td>{w.cum}</td></tr>
                    ))}
                </tbody>
            </table>
        </Card>
    );
}

function NextUp({ problems }) {
    const next = problems.filter((p) => !p.done).slice(0, 3);
    if (!next.length) return null;
    return (
        <Card className="card-pad min-w-0">
            <CardHeader title="Next up" subtitle="The next unsolved problems, in sheet order" icon={ListOrdered} />
            <ul className="divide-y divide-line">
                {next.map((p) => (
                    <li key={p.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                        <div className="min-w-0 flex-1">
                            <a
                                href={p.url}
                                target="_blank"
                                rel="noreferrer"
                                className="block text-sm font-medium leading-snug wrap-break-word hover:text-accent transition-colors"
                            >
                                <span className="font-mono text-subtle font-normal">{p.leetcode_id}.</span> {p.title}
                            </a>
                        </div>
                        <DifficultyBadge value={p.difficulty} className="shrink-0" />
                        <a
                            href={p.url}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-ghost btn-icon shrink-0"
                            aria-label={`Open ${p.title} on LeetCode`}
                            title="Open on LeetCode"
                        >
                            <ExternalLink className="h-4 w-4" />
                        </a>
                    </li>
                ))}
            </ul>
        </Card>
    );
}

function PaceSkeleton() {
    return (
        <div className="space-y-4 lg:space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {[0, 1, 2, 3].map((i) => (
                    <Card key={i} className="card-pad">
                        <Skeleton className="h-3 w-20" />
                        <Skeleton className="h-7 w-16 mt-3" />
                        <Skeleton className="h-3 w-24 mt-2" />
                    </Card>
                ))}
            </div>
            <Card className="card-pad">
                <Skeleton className="h-4 w-40 mb-6" />
                <Skeleton className="h-52 w-full" />
            </Card>
            <Card className="card-pad space-y-3">
                <Skeleton className="h-4 w-28 mb-5" />
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-4 w-full" />)}
            </Card>
        </div>
    );
}

/** Compound Curve (beta): Apple-sheet finish date at the current pace, and what a deadline needs. */
export default function Pace() {
    const { data, loading, error, reload } = useApi('/sheets/apple');
    const [deadline, setDeadline] = useLocalStorage('pace:deadline', '');
    const m = useMemo(() => (data ? derive(data, deadline) : null), [data, deadline]);

    let finishValue = '—';
    let finishNote = 'Start solving to get a projection';
    let daysValue = '—';
    let daysNote = 'Set a deadline or start solving';
    if (m) {
        if (m.remaining === 0) {
            finishValue = 'Done'; finishNote = `All ${m.total} solved`;
        } else if (m.projDays != null) {
            finishValue = m.projDays > HORIZON ? '> 1 year' : fmt(m.finish);
            finishNote = m.projDays > HORIZON ? `At ${one(m.pace14)}/day` : `${fmtFull(m.finish)} at ${one(m.pace14)}/day`;
        }
        if (m.dl != null) {
            daysValue = Math.max(0, m.dlDays);
            daysNote = m.dlDays > 0 ? `Until your ${fmt(m.dl)} deadline` : 'Deadline has passed';
        } else if (m.remaining === 0) {
            daysValue = 0; daysNote = 'Sheet complete';
        } else if (m.projDays != null) {
            daysValue = m.projDays > HORIZON ? '365+' : m.projDays;
            daysNote = 'To finish at current pace';
        }
    }

    return (
        <div className="space-y-5 sm:space-y-6 min-w-0">
            <header className="animate-rise min-w-0">
                <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Compound Curve</h1>
                <p className="text-sm text-muted mt-1">
                    When you&apos;ll finish the Apple sheet at your current pace — and what a deadline needs.
                </p>
            </header>

            {loading && !data ? (
                <PaceSkeleton />
            ) : error && !data ? (
                <Card className="card-pad flex items-center justify-between gap-3">
                    <span className="text-sm text-danger min-w-0">{error}</span>
                    <Button size="sm" icon={RotateCw} onClick={() => reload()}>Retry</Button>
                </Card>
            ) : m && (
                <div className="space-y-4 lg:space-y-6">
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 animate-rise">
                        <StatTile icon={Apple} label="Solved" value={<>{m.done}<span className="text-base text-subtle font-semibold">/{m.total}</span></>}>
                            {plural(m.remaining, 'problem')} left
                        </StatTile>
                        <StatTile icon={Gauge} label="Pace · 14 days" value={<>{one(m.pace14)}<span className="text-base text-subtle font-semibold">/day</span></>}>
                            7-day: {one(m.pace7)}/day
                        </StatTile>
                        <StatTile icon={Flag} label="Projected finish" value={finishValue}>
                            {finishNote}
                        </StatTile>
                        <StatTile icon={Hourglass} label="Days left" value={daysValue}>
                            {daysNote}
                        </StatTile>
                    </div>

                    <div className="grid gap-4 lg:gap-6 lg:grid-cols-5 items-start">
                        <div className="lg:col-span-3 min-w-0">
                            {m.done > 0 ? (
                                <CurveChart m={m} />
                            ) : (
                                <Card className="card-pad min-w-0">
                                    <CardHeader title="Cumulative solved" subtitle="Done so far, and where each pace lands" icon={TrendingUp} className="mb-0" />
                                    <Empty
                                        icon={CalendarClock}
                                        title="Nothing solved yet"
                                        action={<a href="#/learn" className="btn btn-primary btn-sm">Open the Apple sheet</a>}
                                    >
                                        Solve your first problem and the curve, pace and finish date appear here.
                                    </Empty>
                                </Card>
                            )}
                        </div>
                        <div className="lg:col-span-2 min-w-0 space-y-4 lg:space-y-6">
                            <Deadline data={data} m={m} deadline={deadline} setDeadline={setDeadline} />
                            <NextUp problems={data.problems || []} />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
