import { useState } from 'react';
import { Apple, CalendarRange, ChevronLeft, ChevronRight, CircleCheck, ExternalLink, ListChecks, Mail, MonitorPlay, RotateCw, Timer } from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, CardHeader, DifficultyBadge, Skeleton, cx, useToast } from '../components/ui';

const MAX_WEEKS_AGO = 52;
const DIFFICULTIES = ['Easy', 'Medium', 'Hard', 'Unknown'];

const asDate = (iso) => new Date(`${iso}T00:00:00`);
const fmtShort = (iso) => asDate(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
const fmtLong = (iso) => asDate(iso).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
const weekday = (iso) => asDate(iso).toLocaleDateString(undefined, { weekday: 'short' });
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

// "+N vs last week" / "−N vs last week" / "same as last week"
function Delta({ now, prev, unit = '' }) {
    const diff = now - prev;
    if (!diff) return <span className="text-subtle">same as last week</span>;
    return (
        <span className={diff > 0 ? 'text-ok' : 'text-danger'}>
            {diff > 0 ? '+' : '−'}{Math.abs(diff)}{unit} vs last week
        </span>
    );
}

function StatTile({ icon: Icon, label, value, children }) {
    return (
        <Card className="card-pad min-w-0">
            <div className="eyebrow flex items-start gap-1.5 leading-tight">
                <Icon className="h-3.5 w-3.5 shrink-0" /> <span className="min-w-0">{label}</span>
            </div>
            <div className="mt-2 text-[28px] leading-none font-bold tracking-tight tabular-nums">{value}</div>
            <div className="mt-1.5 text-xs text-muted tabular-nums">{children}</div>
        </Card>
    );
}

function DayChart({ days, goal, isCurrent }) {
    const peak = Math.max(goal, 1, ...days.map((d) => d.solved));
    const pct = (n) => (100 * n) / peak;
    const summary = days.map((d) => `${weekday(d.date)} ${d.solved}`).join(', ');

    return (
        <Card className="card-pad min-w-0">
            <CardHeader
                title="Problems per day"
                subtitle={`Goal ${goal} a day · darker bars hit it`}
                icon={CalendarRange}
            />
            <div className="relative pt-5 pr-11" role="img" aria-label={`Problems per day: ${summary}. Goal ${goal}.`}>
                <div className="flex gap-1.5 sm:gap-2.5">
                    {days.map((d, i) => {
                        const today = isCurrent && i === days.length - 1;
                        return (
                            <div
                                key={d.date}
                                title={`${fmtLong(d.date)}\n${d.solved} solved · ${d.focus} min focus`}
                                className="group flex-1 min-w-0 flex flex-col items-center cursor-default"
                            >
                                <div className="relative h-32 w-full flex justify-center">
                                    {d.solved > 0 && (
                                        <span
                                            className="absolute left-1/2 -translate-x-1/2 text-[11px] font-semibold text-fg tabular-nums leading-none"
                                            style={{ bottom: `calc(${pct(d.solved)}% + 4px)` }}
                                        >
                                            {d.solved}
                                        </span>
                                    )}
                                    <div
                                        className={cx(
                                            'absolute bottom-0 w-full max-w-7 transition-[height,opacity] duration-500 group-hover:opacity-80',
                                            d.goal_met ? 'bg-accent rounded-t-[4px]' : d.solved ? 'bg-accent/40 rounded-t-[4px]' : 'bg-surface-3 rounded-[2px]',
                                        )}
                                        style={{ height: d.solved ? `${pct(d.solved)}%` : 3 }}
                                    />
                                </div>
                                <span className={cx('mt-2 text-[11px] leading-4', today ? 'text-fg font-semibold' : 'text-subtle')}>
                                    {weekday(d.date).slice(0, 2)}
                                </span>
                            </div>
                        );
                    })}
                </div>
                {/* Goal reference line, laid over the plot area only (h-32 below the pt-5 label room) */}
                <div aria-hidden className="pointer-events-none absolute inset-x-0 top-5 h-32">
                    <div
                        className="absolute left-0 right-11 border-t border-dashed border-line-strong"
                        style={{ bottom: `${pct(goal)}%` }}
                    />
                    <span
                        className="absolute right-0 translate-y-1/2 text-[10px] leading-none text-subtle whitespace-nowrap"
                        style={{ bottom: `${pct(goal)}%` }}
                    >
                        goal {goal}
                    </span>
                </div>
            </div>
        </Card>
    );
}

function Row({ label, children }) {
    return (
        <div className="flex items-start justify-between gap-3 py-2.5 text-sm">
            <dt className="text-muted shrink-0">{label}</dt>
            <dd className="min-w-0 flex flex-wrap items-center justify-end gap-1.5 text-right text-fg font-medium tabular-nums">{children}</dd>
        </div>
    );
}

function Details({ data }) {
    const diffs = DIFFICULTIES.filter((d) => data.by_difficulty?.[d]);
    const best = data.best_day?.solved ? data.best_day : null;
    return (
        <Card className="card-pad min-w-0">
            <CardHeader title="This week" subtitle={`${data.leetcode} LeetCode · ${data.codeforces} Codeforces`} icon={ListChecks} className="mb-1" />
            <dl className="divide-y divide-line">
                <Row label="Active days">{data.active_days}/7</Row>
                {data.goal_days > 0 && <Row label="Goal hit">{plural(data.goal_days, 'day')}</Row>}
                <Row label="Streak">
                    {plural(data.streak, 'day')}
                    <span className="text-subtle font-normal">· best {data.best_streak}</span>
                </Row>
                {diffs.length > 0 && (
                    <Row label="Difficulty">
                        {diffs.map((d) => (
                            <span key={d} className="inline-flex items-center gap-1">
                                <DifficultyBadge value={d} />
                                <span className="text-xs">{data.by_difficulty[d]}</span>
                            </span>
                        ))}
                    </Row>
                )}
                {data.topics?.length > 0 && (
                    <Row label="Topics">
                        {data.topics.map((t) => (
                            <span key={t.topic} className="chip cursor-default hover:text-muted hover:border-line max-w-full">
                                <span className="truncate">{t.topic}</span>
                                <span className="text-subtle tabular-nums">{t.count}</span>
                            </span>
                        ))}
                    </Row>
                )}
                {data.revisions > 0 && <Row label="Revisions">{plural(data.revisions, 'problem')}</Row>}
                {data.episodes > 0 && <Row label="Episodes watched">{data.episodes}</Row>}
                {best && (
                    <Row label="Best day">
                        {weekday(best.date)} {fmtShort(best.date)}
                        <span className="text-subtle font-normal">· {best.solved} solved</span>
                    </Row>
                )}
            </dl>
        </Card>
    );
}

function NextUp({ next }) {
    const { sheet, lesson } = next || {};
    if (!sheet && !lesson) return null;
    return (
        <Card className="card-pad">
            <CardHeader title="Pick up next week" subtitle="Where the trackers left off" icon={ChevronRight} />
            <ul className="divide-y divide-line">
                {sheet && (
                    <li className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                        <Apple className="h-4 w-4 text-subtle shrink-0" />
                        <div className="min-w-0 flex-1">
                            <div className="eyebrow">Apple sheet</div>
                            <a
                                href={sheet.url}
                                target="_blank"
                                rel="noreferrer"
                                className="mt-0.5 block text-sm font-medium leading-snug wrap-break-word hover:text-accent transition-colors"
                            >
                                <span className="font-mono text-subtle font-normal">{sheet.leetcode_id}.</span> {sheet.title}
                            </a>
                        </div>
                        <DifficultyBadge value={sheet.difficulty} className="shrink-0" />
                        <a
                            href={sheet.url}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-ghost btn-icon shrink-0"
                            aria-label={`Open ${sheet.title} on LeetCode`}
                            title="Open on LeetCode"
                        >
                            <ExternalLink className="h-4 w-4" />
                        </a>
                    </li>
                )}
                {lesson && (
                    <li className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                        <MonitorPlay className="h-4 w-4 text-subtle shrink-0" />
                        <div className="min-w-0 flex-1">
                            <div className="eyebrow">System design</div>
                            <a href="#/learn" className="mt-0.5 block text-sm font-medium leading-snug wrap-break-word hover:text-accent transition-colors">
                                <span className="font-mono text-subtle font-normal">#{lesson.position}</span> {lesson.title}
                            </a>
                        </div>
                        <a href="#/learn" className="btn btn-ghost btn-icon shrink-0" aria-label="Open Learn" title="Open Learn">
                            <ChevronRight className="h-4 w-4" />
                        </a>
                    </li>
                )}
            </ul>
        </Card>
    );
}

function WeeklySkeleton() {
    return (
        <div className="space-y-4 lg:space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {[0, 1, 2, 3].map((i) => (
                    <Card key={i} className="card-pad">
                        <Skeleton className="h-3 w-24" />
                        <Skeleton className="h-7 w-14 mt-3" />
                        <Skeleton className="h-3 w-28 mt-2" />
                    </Card>
                ))}
            </div>
            <div className="grid gap-4 lg:gap-6 lg:grid-cols-5">
                <Card className="card-pad lg:col-span-3">
                    <Skeleton className="h-4 w-40 mb-6" />
                    <Skeleton className="h-36 w-full" />
                </Card>
                <Card className="card-pad lg:col-span-2 space-y-3">
                    <Skeleton className="h-4 w-28 mb-5" />
                    {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-4 w-full" />)}
                </Card>
            </div>
        </div>
    );
}

/** Weekly report (beta): the 7-day recap that also goes out by email on Sundays. */
export default function Weekly() {
    const [weeksAgo, setWeeksAgo] = useState(0);
    const { data, loading, error, reload } = useApi(`/weekly?weeks_ago=${weeksAgo}`);
    const [sending, setSending] = useState(false);
    const toast = useToast();

    const send = async () => {
        setSending(true);
        try {
            await api('/weekly/send', { method: 'POST' });
            toast('Weekly report sent');
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setSending(false);
        }
    };

    const range = data ? `${fmtShort(data.start)} – ${fmtShort(data.end)}` : null;
    const when = weeksAgo === 0 ? 'last 7 days' : weeksAgo === 1 ? 'a week earlier' : `${weeksAgo} weeks earlier`;

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 animate-rise">
                <div className="min-w-0">
                    <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Weekly report</h1>
                    <p className="text-sm text-muted mt-1 tabular-nums">
                        {range ? <>{range} <span className="text-subtle">· {when}</span></> : <span className="text-subtle">{when}</span>}
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <div className="inline-flex items-center gap-1">
                        <Button
                            size="icon"
                            icon={ChevronLeft}
                            aria-label="Previous week"
                            title="Previous week"
                            disabled={weeksAgo >= MAX_WEEKS_AGO}
                            onClick={() => setWeeksAgo((w) => Math.min(MAX_WEEKS_AGO, w + 1))}
                        />
                        <Button
                            size="icon"
                            icon={ChevronRight}
                            aria-label="Next week"
                            title="Next week"
                            disabled={weeksAgo === 0}
                            onClick={() => setWeeksAgo((w) => Math.max(0, w - 1))}
                        />
                    </div>
                    {weeksAgo > 0 && (
                        <Button variant="ghost" size="sm" onClick={() => setWeeksAgo(0)}>This week</Button>
                    )}
                    {weeksAgo === 0 && (
                        <Button variant="primary" icon={Mail} loading={sending} onClick={send}>Email me this</Button>
                    )}
                </div>
            </header>

            <p className="text-xs text-subtle -mt-2 sm:-mt-3">
                Beta: the Sunday 7:30 PM email starts once you approve Weekly report in the Beta Lab.
            </p>

            {loading && !data ? (
                <WeeklySkeleton />
            ) : error && !data ? (
                <Card className="card-pad flex items-center justify-between gap-3">
                    <span className="text-sm text-danger min-w-0">{error}</span>
                    <Button size="sm" icon={RotateCw} onClick={() => reload()}>Retry</Button>
                </Card>
            ) : data && (
                <div className="space-y-4 lg:space-y-6">
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 animate-rise">
                        <StatTile icon={CircleCheck} label="Problems solved" value={data.solved}>
                            <Delta now={data.solved} prev={data.solved_prev} />
                        </StatTile>
                        <StatTile icon={Apple} label="Apple sheet" value={data.sheet}>
                            {data.sheet_done}/{data.sheet_total} total
                        </StatTile>
                        <StatTile icon={MonitorPlay} label="System design videos" value={data.videos}>
                            {data.videos_done}/{data.videos_total} total
                        </StatTile>
                        <StatTile icon={Timer} label="Focus time" value={`${(data.focus_minutes / 60).toFixed(1)}h`}>
                            <Delta now={data.focus_minutes} prev={data.focus_minutes_prev} unit=" min" />
                        </StatTile>
                    </div>

                    <div className="grid gap-4 lg:gap-6 lg:grid-cols-5 items-start">
                        <div className="lg:col-span-3 min-w-0">
                            <DayChart days={data.days} goal={data.goal} isCurrent={data.weeks_ago === 0} />
                        </div>
                        <div className="lg:col-span-2 min-w-0">
                            <Details data={data} />
                        </div>
                    </div>

                    <NextUp next={data.next} />
                </div>
            )}
        </div>
    );
}
