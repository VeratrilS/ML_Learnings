import { useMemo, useState } from 'react';
import { Apple, Check, ExternalLink, Flame, ListChecks, PartyPopper, RotateCw, Search } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, useLocalStorage } from '../lib/hooks';
import { Button, Card, Checkbox, DifficultyBadge, Empty, ProgressBar, Segmented, Skeleton, cx, useToast } from './ui';
import { TodayPill } from './LearnCard';

// Optimistically flip one problem and recompute the totals (server stays the source of truth).
function patchProblem(data, id, done) {
    let delta = 0;
    const problems = data.problems.map((p) => {
        if (p.id !== id || p.done === done) return p;
        if (done) delta += 1;
        else if (p.done_day === data.day) delta -= 1;
        return { ...p, done, done_day: done ? data.day : null, done_at: done ? new Date().toISOString() : null };
    });
    const solved = problems.filter((p) => p.done);
    const by_difficulty = Object.fromEntries(Object.entries(data.by_difficulty).map(([d, v]) => [
        d, { ...v, done: solved.filter((p) => p.difficulty === d).length },
    ]));
    return {
        ...data, problems, by_difficulty,
        done: solved.length,
        progress: data.total ? Math.round((100 * solved.length) / data.total) : 0,
        next: problems.find((p) => !p.done) || null,
        done_today: Math.max(0, (data.done_today || 0) + delta),
    };
}

const fmtDay = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '');
const ASKED = { '30d': 'Asked < 30 days', '3mo': 'Asked < 3 months', '6mo': 'Asked < 6 months', '6mo+': 'Asked > 6 months ago', older: 'Asked a while ago' };

function Topics({ topics, max = 3 }) {
    if (!topics?.length) return null;
    const extra = topics.length - max;
    return (
        <span className="truncate">
            {topics.slice(0, max).join(' · ')}{extra > 0 && <span className="text-subtle"> +{extra}</span>}
        </span>
    );
}

function NextCard({ data, busy, onDone }) {
    const [opened, setOpened] = useState(false);
    const next = data.next;
    const count = data.done_today || 0;
    const min = data.daily_min || 1;
    const met = count >= min;
    const { Medium: med, Hard: hard } = data.by_difficulty;

    return (
        <Card className="relative overflow-hidden animate-rise">
            <div
                aria-hidden
                className={cx('pointer-events-none absolute -top-24 -right-20 h-64 w-64 rounded-full opacity-[0.13] blur-3xl transition-colors duration-700', met ? 'bg-ok' : 'bg-accent')}
            />
            <div className="relative card-pad">
                <div className="flex items-center justify-between gap-3">
                    <div className="eyebrow flex items-center gap-1.5 min-w-0">
                        <Apple className="h-3.5 w-3.5 shrink-0" /> <span className="truncate">Up next</span>
                    </div>
                    <TodayPill count={count} min={min} />
                </div>

                {next ? (
                    <>
                        <div className="mt-3">
                            <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-subtle">
                                <span>Problem <span className="font-mono text-fg font-semibold">{next.position}</span> / {data.total}</span>
                                <DifficultyBadge value={next.difficulty} />
                                {next.last_asked && <span>{ASKED[next.last_asked]}</span>}
                            </div>
                            <a
                                href={next.url}
                                target="_blank"
                                rel="noreferrer"
                                onClick={() => setOpened(true)}
                                className="mt-1 block text-lg sm:text-xl font-semibold tracking-tight leading-snug hover:text-accent transition-colors wrap-break-word"
                            >
                                <span className="font-mono text-subtle font-normal">{next.leetcode_id}.</span> {next.title}
                            </a>
                            <div className="mt-1 flex text-xs text-muted min-w-0"><Topics topics={next.topics} max={4} /></div>
                        </div>

                        <div className="mt-4 flex flex-wrap gap-2">
                            <a
                                href={next.url}
                                target="_blank"
                                rel="noreferrer"
                                onClick={() => setOpened(true)}
                                className="btn btn-primary btn-lg flex-1 sm:flex-none"
                            >
                                <ExternalLink className="h-4 w-4" /> {met ? 'Solve another' : 'Solve on LeetCode'}
                            </a>
                            <Button
                                size="lg"
                                variant={opened ? 'primary' : 'secondary'}
                                icon={Check}
                                loading={busy}
                                onClick={() => { onDone(next, true); setOpened(false); }}
                                className={cx('flex-1 sm:flex-none', opened && 'animate-rise')}
                            >
                                Mark solved
                            </Button>
                        </div>
                    </>
                ) : (
                    <div className="mt-4 flex items-center gap-3 rounded-xl bg-ok/10 border border-ok/25 px-3 py-3">
                        <PartyPopper className="h-5 w-5 text-ok shrink-0" />
                        <span className="text-sm">All {data.total} problems solved. Sheet complete!</span>
                    </div>
                )}

                <div className="mt-5">
                    <div className="flex items-center justify-between gap-3 text-xs">
                        <span className="text-muted">
                            <span className="font-semibold text-fg font-mono">{data.done}</span> / {data.total} solved
                            <span className="text-subtle"> · {data.progress}%</span>
                        </span>
                        <span className="flex items-center gap-3 text-subtle min-w-0">
                            <span className="hidden min-[400px]:inline whitespace-nowrap">
                                <span className="text-medium font-semibold">{med.done}/{med.total}</span> M
                                {' · '}
                                <span className="text-hard font-semibold">{hard.done}/{hard.total}</span> H
                            </span>
                            <span
                                className={cx('inline-flex items-center gap-1 font-semibold whitespace-nowrap', data.streak ? 'text-accent' : 'text-subtle')}
                                title="Days in a row with at least one problem solved"
                            >
                                <Flame className="h-3.5 w-3.5" /> {data.streak}d
                            </span>
                        </span>
                    </div>
                    <ProgressBar value={data.progress} className="mt-2" color={data.progress >= 100 ? 'var(--ok)' : 'var(--accent)'} />
                </div>
            </div>
        </Card>
    );
}

function ProblemRow({ problem, isNext, onToggle }) {
    return (
        <li className={cx('flex items-center gap-3 px-3 sm:px-4 py-2.5 row-hover', isNext && 'bg-accent-soft hover:bg-accent-soft')}>
            <Checkbox
                checked={problem.done}
                onChange={(v) => onToggle(problem, v)}
                label={problem.done ? `Unmark ${problem.title}` : `Mark ${problem.title} solved`}
            />
            <span className={cx('w-7 text-right font-mono text-xs tabular-nums shrink-0', isNext ? 'text-accent font-semibold' : 'text-subtle')}>
                {problem.position}
            </span>
            <div className="min-w-0 flex-1">
                <a
                    href={problem.url}
                    target="_blank"
                    rel="noreferrer"
                    className={cx(
                        'block text-sm leading-snug line-clamp-2 wrap-break-word hover:text-accent transition-colors',
                        problem.done ? 'text-muted' : 'text-fg font-medium',
                    )}
                >
                    <span className="font-mono text-subtle font-normal">{problem.leetcode_id}.</span> {problem.title}
                </a>
                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-subtle min-w-0">
                    {isNext && <span className="badge bg-accent text-accent-fg shrink-0">Up next</span>}
                    {problem.done && problem.done_day
                        ? <span className="text-ok truncate">solved {fmtDay(problem.done_day)}</span>
                        : <Topics topics={problem.topics} />}
                </div>
            </div>
            <span className="hidden sm:inline font-mono text-xs text-subtle tabular-nums shrink-0" title="LeetCode acceptance rate">
                {problem.acceptance != null && `${Math.round(problem.acceptance)}%`}
            </span>
            <DifficultyBadge value={problem.difficulty} className="shrink-0" />
            <a
                href={problem.url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost btn-icon shrink-0"
                aria-label={`Open ${problem.title} on LeetCode`}
                title="Open on LeetCode"
            >
                <ExternalLink className="h-4 w-4" />
            </a>
        </li>
    );
}

/** Checklist for a company's LeetCode sheet (e.g. Apple Medium + Hard), shown as a tab on Learn. */
export default function SheetTracker({ sheet }) {
    const { data, loading, error, setData, reload } = useApi(`/sheets/${sheet}`);
    const [filter, setFilter] = useLocalStorage(`sheet:${sheet}:filter`, 'todo');
    const [diff, setDiff] = useLocalStorage(`sheet:${sheet}:diff`, 'all');
    const [q, setQ] = useState('');
    const [busy, setBusy] = useState(false);
    const toast = useToast();

    const problems = useMemo(() => data?.problems || [], [data]);
    const shown = useMemo(() => {
        const needle = q.trim().toLowerCase();
        return problems.filter((p) =>
            (filter === 'todo' ? !p.done : filter === 'done' ? p.done : true)
            && (diff === 'all' || p.difficulty === diff)
            && (!needle || p.title.toLowerCase().includes(needle) || String(p.leetcode_id) === needle
                || p.topics.some((t) => t.toLowerCase().includes(needle))));
    }, [problems, filter, diff, q]);

    const toggle = async (problem, done, { quiet } = {}) => {
        setBusy(true);
        setData((d) => patchProblem(d, problem.id, done));
        try {
            await api(`/sheets/problems/${problem.id}`, { method: 'PUT', body: { done } });
            if (done && !quiet) {
                toast(`${problem.title} solved. Nice work.`, 'success', { action: { label: 'Undo', onClick: () => toggle(problem, false, { quiet: true }) } });
            }
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setBusy(false);
            reload({ silent: true }); // refresh streak / server truth
        }
    };

    if (loading && !data) {
        return (
            <div className="space-y-5">
                <Card className="card-pad">
                    <Skeleton className="h-3 w-28" />
                    <Skeleton className="h-6 w-2/3 mt-4" />
                    <Skeleton className="h-10 w-full mt-5" />
                </Card>
                <Card className="divide-y divide-line">
                    {[0, 1, 2, 3, 4].map((i) => (
                        <div key={i} className="flex items-center gap-3 px-4 py-3">
                            <Skeleton className="h-5 w-5 rounded-md" />
                            <Skeleton className="h-4 w-6" />
                            <div className="flex-1 space-y-1.5"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-32" /></div>
                        </div>
                    ))}
                </Card>
            </div>
        );
    }
    if (error && !data) {
        return (
            <Card className="card-pad flex items-center justify-between gap-3">
                <span className="text-sm text-danger min-w-0">{error}</span>
                <Button size="sm" icon={RotateCw} onClick={() => reload()}>Retry</Button>
            </Card>
        );
    }
    if (!data) return null;

    const todo = data.total - data.done;
    const statusOptions = [
        { value: 'todo', label: `To solve ${todo}` },
        { value: 'done', label: `Solved ${data.done}` },
        { value: 'all', label: `All ${data.total}` },
    ];
    const diffOptions = [
        { value: 'all', label: 'Any' },
        { value: 'Medium', label: `Medium ${data.by_difficulty.Medium.total}` },
        { value: 'Hard', label: `Hard ${data.by_difficulty.Hard.total}` },
    ];

    return (
        <div className="space-y-5 sm:space-y-6">
            <NextCard data={data} busy={busy} onDone={toggle} />

            <section className="space-y-3">
                <h2 className="text-[15px] font-semibold tracking-tight flex items-center gap-2">
                    <ListChecks className="h-4 w-4 text-subtle" /> All problems
                </h2>
                <Card className="overflow-hidden">
                    <div className="p-3 sm:p-4 flex flex-col lg:flex-row gap-3 border-b border-line">
                        <div className="flex flex-wrap gap-2 max-w-full overflow-x-auto no-scrollbar">
                            <Segmented options={statusOptions} value={filter} onChange={setFilter} />
                            <Segmented options={diffOptions} value={diff} onChange={setDiff} />
                        </div>
                        <div className="relative flex-1">
                            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
                            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, number or topic" className="input h-9 pl-9" />
                        </div>
                    </div>
                    {shown.length ? (
                        <ul className="divide-y divide-line">
                            {shown.map((p) => (
                                <ProblemRow key={p.id} problem={p} isNext={p.id === data.next?.id} onToggle={toggle} />
                            ))}
                        </ul>
                    ) : (
                        <Empty icon={ListChecks} title={q || diff !== 'all' ? 'No matches' : filter === 'done' ? 'Nothing solved yet' : 'All caught up'}>
                            {q || diff !== 'all'
                                ? 'Try a different search or filter.'
                                : filter === 'done' ? 'Problems you mark solved show up here.' : `You've solved all ${data.total} problems.`}
                        </Empty>
                    )}
                </Card>
            </section>
        </div>
    );
}
