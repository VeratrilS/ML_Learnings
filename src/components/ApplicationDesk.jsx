import { useMemo, useState } from 'react';
import { ClipboardList, ExternalLink, Mail, Bot, Hand, CalendarClock } from 'lucide-react';
import { Card, cx } from './ui';

const TZ = 'Asia/Kolkata';
const DAY = 86400000;

const OUTCOME = {
    oa: { label: 'OA received', cls: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30' },
    interview: { label: 'Interview', cls: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
    offer: { label: 'Offer', cls: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' },
    rejected: { label: 'Rejected', cls: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30' },
    no_response: { label: 'No response', cls: 'bg-surface-2 text-subtle border-line' },
};

// IST calendar day key, e.g. "2026-10-17"
const dayKey = (d) => d.toLocaleDateString('en-CA', { timeZone: TZ });
const fmtDay = (d) => d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ });
const fmtTime = (d) => d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: TZ });

function parse(iso) {
    if (!iso) return null;
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`); // server sends naive UTC
    return Number.isNaN(d.getTime()) ? null : d;
}

// How the application was confirmed, from the note the runner / app wrote when marking it applied.
function howApplied(notes = '') {
    if (/confirmed by email/i.test(notes)) return { label: 'Email', title: "Company's confirmation email", Icon: Mail };
    if (/auto-apply|apply-runner/i.test(notes)) return { label: 'Runner', title: 'Apply runner reached the thank-you page', Icon: Bot };
    return { label: 'You', title: 'Marked applied by you', Icon: Hand };
}

function nextFollowUp(job, now) {
    if (job.outcome) return null;
    for (const iso of [job.follow_up_7d_at, job.follow_up_14d_at]) {
        const d = parse(iso);
        if (d && d.getTime() > now - DAY) return d; // due today or later
    }
    return null;
}

function Stat({ label, value, tone }) {
    return (
        <div className="rounded-xl border border-line bg-surface-2 px-3 py-2 min-w-0">
            <div className={cx('text-xl font-bold tabular-nums leading-tight', tone || 'text-fg')}>{value}</div>
            <div className="text-[11px] text-subtle truncate">{label}</div>
        </div>
    );
}

/** Every confirmed application with its date, newest first: the one place to see what you've applied to. */
export default function ApplicationDesk({ jobs, onOpenTracker }) {
    const [showAll, setShowAll] = useState(false);
    const now = Date.now();

    const rows = useMemo(() => jobs
        .map((j) => ({ ...j, applied: parse(j.applied_at) }))
        .filter((j) => j.applied)
        .sort((a, b) => b.applied - a.applied), [jobs]);

    const todayKey = dayKey(new Date(now));
    const yesterdayKey = dayKey(new Date(now - DAY));
    const stats = useMemo(() => ({
        total: rows.length,
        today: rows.filter((r) => dayKey(r.applied) === todayKey).length,
        week: rows.filter((r) => now - r.applied.getTime() < 7 * DAY).length,
        due: rows.filter((r) => {
            const f = nextFollowUp(r, now);
            return f && f.getTime() <= now;
        }).length,
        replies: rows.filter((r) => ['oa', 'interview', 'offer'].includes(r.outcome)).length,
    }), [rows, todayKey, now]);

    const visible = showAll ? rows : rows.slice(0, 8);
    const groups = [];
    for (const r of visible) {
        const k = dayKey(r.applied);
        if (!groups.length || groups[groups.length - 1].key !== k) {
            const label = k === todayKey ? 'Today' : k === yesterdayKey ? 'Yesterday' : fmtDay(r.applied);
            groups.push({ key: k, label, items: [] });
        }
        groups[groups.length - 1].items.push(r);
    }

    return (
        <Card className="card-pad space-y-4">
            <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2.5">
                    <ClipboardList className="h-5 w-5 text-emerald-400 shrink-0" />
                    <div>
                        <h2 className="font-bold text-base text-fg">Application desk</h2>
                        <p className="text-xs text-subtle">Every confirmed application with the date you applied, newest first.</p>
                    </div>
                </div>
                {onOpenTracker && (
                    <button type="button" onClick={onOpenTracker} className="btn btn-ghost btn-sm text-xs">
                        Callbacks &amp; notes →
                    </button>
                )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                <Stat label="Applied in total" value={stats.total} tone="text-emerald-400" />
                <Stat label="This week" value={stats.week} />
                <Stat label="Today" value={stats.today} />
                <Stat label="Follow-ups due" value={stats.due} tone={stats.due ? 'text-amber-400' : undefined} />
                <Stat label="OA / interview / offer" value={stats.replies} tone={stats.replies ? 'text-cyan-400' : undefined} />
            </div>

            {rows.length === 0 ? (
                <p className="text-sm text-subtle py-4 text-center">
                    No confirmed applications yet. They appear here, with the date, as soon as one is confirmed.
                </p>
            ) : (
                <div className="overflow-x-auto -mx-1">
                    <table className="w-full text-sm border-separate border-spacing-0">
                        <thead>
                            <tr className="text-[11px] uppercase tracking-wider text-subtle text-left">
                                <th className="font-medium px-2 pb-2 w-28">Applied</th>
                                <th className="font-medium px-2 pb-2">Company &amp; role</th>
                                <th className="font-medium px-2 pb-2 hidden sm:table-cell">Confirmed by</th>
                                <th className="font-medium px-2 pb-2">Status</th>
                                <th className="font-medium px-2 pb-2 hidden md:table-cell">Next follow-up</th>
                                <th className="px-2 pb-2 w-8" aria-label="Link" />
                            </tr>
                        </thead>
                        {groups.map((g) => (
                            <tbody key={g.key}>
                                <tr>
                                    <td colSpan={6} className="px-2 pt-3 pb-1 text-xs font-semibold text-fg border-b border-line">
                                        {g.label}
                                        <span className="text-subtle font-normal"> · {g.items.length}</span>
                                    </td>
                                </tr>
                                {g.items.map((r) => {
                                    const how = howApplied(r.notes || '');
                                    const follow = nextFollowUp(r, now);
                                    const out = OUTCOME[r.outcome];
                                    const days = Math.floor((now - r.applied.getTime()) / DAY);
                                    return (
                                        <tr key={r.id} className="hover:bg-surface-2/60">
                                            <td className="px-2 py-2 align-top border-b border-line/60 whitespace-nowrap">
                                                <div className="font-medium text-fg">{fmtDay(r.applied)}</div>
                                                <div className="text-[11px] text-subtle">
                                                    {fmtTime(r.applied)} · {days === 0 ? 'today' : `${days}d ago`}
                                                </div>
                                            </td>
                                            <td className="px-2 py-2 align-top border-b border-line/60 min-w-0">
                                                <div className="font-semibold text-fg">{r.company}</div>
                                                <div className="text-xs text-subtle line-clamp-1">{r.role}</div>
                                            </td>
                                            <td className="px-2 py-2 align-top border-b border-line/60 hidden sm:table-cell">
                                                <span className="inline-flex items-center gap-1 text-xs text-subtle" title={how.title}>
                                                    <how.Icon className="h-3.5 w-3.5" />
                                                    {how.label}
                                                </span>
                                            </td>
                                            <td className="px-2 py-2 align-top border-b border-line/60">
                                                {out ? (
                                                    <span className={cx('badge text-[11px] border', out.cls)}>{out.label}</span>
                                                ) : (
                                                    <span className="badge text-[11px] border bg-surface-2 text-subtle border-line">Awaiting reply</span>
                                                )}
                                            </td>
                                            <td className="px-2 py-2 align-top border-b border-line/60 hidden md:table-cell whitespace-nowrap">
                                                {follow ? (
                                                    <span className={cx('inline-flex items-center gap-1 text-xs',
                                                        follow.getTime() <= now ? 'text-amber-400 font-medium' : 'text-subtle')}>
                                                        <CalendarClock className="h-3.5 w-3.5" />
                                                        {follow.getTime() <= now ? 'Due now' : fmtDay(follow)}
                                                    </span>
                                                ) : (
                                                    <span className="text-xs text-subtle">—</span>
                                                )}
                                            </td>
                                            <td className="px-2 py-2 align-top border-b border-line/60">
                                                {(r.portal_url || r.url) && (
                                                    <a href={r.portal_url || r.url} target="_blank" rel="noopener noreferrer"
                                                        className="text-subtle hover:text-fg" title="Open the job posting">
                                                        <ExternalLink className="h-3.5 w-3.5" />
                                                    </a>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        ))}
                    </table>
                    {rows.length > 8 && (
                        <button type="button" onClick={() => setShowAll((v) => !v)}
                            className="mt-2 text-xs text-subtle hover:text-fg px-2">
                            {showAll ? 'Show fewer' : `Show all ${rows.length}`}
                        </button>
                    )}
                </div>
            )}
        </Card>
    );
}
