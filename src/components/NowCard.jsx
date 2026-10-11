import { useEffect, useState } from 'react';
import {
    Sunrise, Sun, Sunset, MoonStar, ListPlus, Check, Play, RotateCcw, Tv, MonitorPlay, Code2, Trophy,
    ArrowRight, Radio, Moon, CircleCheck,
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, Skeleton, useToast, cx } from './ui';

const IST_OFFSET = 5.5 * 3600 * 1000;
const istNow = () => new Date(Date.now() + IST_OFFSET); // read with getUTC* for IST wall time
const HOUR = 3600 * 1000;

function phaseOf(h) {
    if (h >= 5 && h < 11) return 'morning';
    if (h >= 11 && h < 18) return 'day';
    if (h >= 18 && h < 23) return 'evening';
    return 'night';
}

const PHASES = {
    morning: { icon: Sunrise, eyebrow: 'Morning briefing', title: 'Set up the day' },
    day: { icon: Sun, eyebrow: 'Deep work', title: 'One thing at a time' },
    evening: { icon: Sunset, eyebrow: 'Wind down', title: 'Finish the round' },
    night: { icon: MoonStar, eyebrow: 'Rest', title: 'Recovery is training too' },
};

function useClock() {
    const [now, setNow] = useState(istNow);
    useEffect(() => {
        const t = setInterval(() => setNow(istNow()), 60_000);
        return () => clearInterval(t);
    }, []);
    return now;
}

const prefersReducedMotion = () => {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
};
const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
};

const openShutdown = () => {
    window.dispatchEvent(new CustomEvent('shutdown-open'));
    setTimeout(() => scrollToSection('shutdown'), 30);
};

function fmtSpan(ms) {
    const m = Math.max(0, Math.round(ms / 60000));
    const h = Math.floor(m / 60);
    return h ? `${h}h ${m % 60}m` : `${m}m`;
}

const norm = (s) => String(s || '').trim().toLowerCase();

/** A small inline fact: icon + text, optionally a link/button. */
function Fact({ icon: Icon, children, onClick, href, tone }) {
    const cls = cx(
        'inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg border text-[12.5px] font-medium max-w-full min-w-0 transition-colors',
        tone === 'ok' ? 'border-ok/25 bg-ok/10 text-fg' : 'border-line bg-surface/70 text-muted',
        (onClick || href) && 'hover:text-fg hover:border-line-strong',
    );
    const inner = (
        <>
            <Icon className={cx('h-3.5 w-3.5 shrink-0', tone === 'ok' ? 'text-ok' : 'text-subtle')} />
            <span className="truncate">{children}</span>
        </>
    );
    if (href) return <a href={href} target="_blank" rel="noreferrer" className={cls}>{inner}</a>;
    if (onClick) return <button type="button" onClick={onClick} className={cls}>{inner}</button>;
    return <span className={cls}>{inner}</span>;
}

function Top3List({ items, planned }) {
    return (
        <ol className="space-y-1.5">
            {items.map((t, i) => {
                const on = planned?.has(norm(t));
                return (
                    <li key={i} className="flex items-start gap-2.5 text-sm">
                        <span className={cx('grid place-items-center h-5 w-5 rounded-md text-[11px] font-bold shrink-0 mt-px',
                            on ? 'bg-ok/15 text-ok' : 'bg-accent-soft text-accent')}>
                            {on ? <Check className="h-3 w-3" strokeWidth={3} /> : i + 1}
                        </span>
                        <span className="min-w-0 break-words [overflow-wrap:anywhere] font-medium">{t}</span>
                    </li>
                );
            })}
        </ol>
    );
}

/**
 * Time-aware hero card. `rev` bumps whenever the plan or journal changed elsewhere on the page;
 * `onPlanChange` tells the page we changed the plan.
 */
export default function NowCard({ rev = 0, onPlanChange }) {
    const now = useClock();
    const hour = now.getUTCHours();
    const phase = phaseOf(hour);
    const isMorning = phase === 'morning';
    const isDay = phase === 'day';
    const isEvening = phase === 'evening';

    const journal = useApi('/journal/today', { select: (d) => d, deps: [rev] });
    const todos = useApi('/todos', { deps: [rev] });
    const reviews = useApi(isMorning ? '/reviews' : null);
    const watch = useApi(isMorning || isEvening ? '/watch' : null);
    const learning = useApi(isMorning || isEvening ? '/learning' : null);
    const pending = useApi(isMorning || isDay ? '/logs?type=leetcode' : null, { select: (d) => d.data.filter((l) => !l.is_completed) });
    const contests = useApi(isDay ? '/contests' : null);

    const meta = PHASES[phase];
    const PhaseIcon = meta.icon;
    const timeLabel = `${String(hour).padStart(2, '0')}:${String(now.getUTCMinutes()).padStart(2, '0')}`;

    const series = watch.data?.find((s) => s.is_active) || watch.data?.[0];
    const episodeDone = !!series?.watched_today?.length;
    const course = learning.data?.courses?.find((c) => c.is_active) || learning.data?.courses?.[0];
    const lesson = course?.today?.lesson;
    const lessonDone = (learning.data?.done_today || 0) > 0;
    const firstProblem = pending.data?.[0];
    const open = (todos.data || []).filter((t) => !t.done).sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
    const doneCount = (todos.data || []).filter((t) => t.done).length;
    const closed = !!journal.data?.data;

    let body;
    if (journal.loading && !journal.data) {
        body = <div className="space-y-2.5"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-8 w-40" /></div>;
    } else if (isMorning) {
        body = (
            <Morning
                top3={journal.data?.yesterday?.top3 || []}
                todos={todos.data}
                onAdded={onPlanChange}
                facts={(
                    <>
                        {!!reviews.data?.length && (
                            <Fact icon={RotateCcw} onClick={() => scrollToSection('revisions')}>
                                {reviews.data.length} revision{reviews.data.length === 1 ? '' : 's'} due
                            </Fact>
                        )}
                        {series && !series.finished && (
                            episodeDone
                                ? <Fact icon={Tv} tone="ok">Episode done</Fact>
                                : <Fact icon={Tv} onClick={() => scrollToSection('episode')}>Ep {series.next_episode} tonight</Fact>
                        )}
                        {lesson && (
                            lessonDone
                                ? <Fact icon={MonitorPlay} tone="ok">Lesson done</Fact>
                                : <Fact icon={MonitorPlay} onClick={() => navigate('learn')}>Lesson {lesson.position}: {lesson.title}</Fact>
                        )}
                        {firstProblem && (
                            <Fact icon={Code2} onClick={() => navigate(`problems/${firstProblem.id}`)}>Up first: {firstProblem.title}</Fact>
                        )}
                    </>
                )}
            />
        );
    } else if (isDay) {
        body = (
            <DeepWork
                nowMs={now.getTime() - IST_OFFSET}
                open={open}
                doneCount={doneCount}
                loading={todos.loading && !todos.data}
                firstProblem={firstProblem}
                contests={contests.data}
                onPlanChange={onPlanChange}
                setTodos={todos.setData}
            />
        );
    } else if (isEvening) {
        body = (
            <div className="space-y-3.5">
                <div className="flex flex-wrap gap-2">
                    {series && !series.finished && (
                        episodeDone
                            ? <Fact icon={Tv} tone="ok">Episode {series.watched_today[series.watched_today.length - 1]} watched</Fact>
                            : <Fact icon={Tv} href={series.next_url}>Ep {series.next_episode} of {series.title.split(':')[0]} is waiting</Fact>
                    )}
                    {lesson && !lessonDone && (
                        <Fact icon={MonitorPlay} onClick={() => navigate('learn')}>Today's lesson: {lesson.title}</Fact>
                    )}
                    {todos.data && todos.data.length > 0 && (
                        <Fact icon={CircleCheck} tone={open.length === 0 ? 'ok' : undefined}>
                            {doneCount}/{todos.data.length} plan tasks done
                        </Fact>
                    )}
                </div>
                {closed ? (
                    <ClosedLine />
                ) : (
                    <div className="flex flex-wrap items-center gap-2">
                        <Button variant="primary" icon={Moon} onClick={openShutdown}>Close the day</Button>
                        <span className="text-xs text-subtle">Two minutes. Then you're off the clock.</span>
                    </div>
                )}
            </div>
        );
    } else {
        // After 04:00 the journal day has rolled over, so last night's plan lives in `yesterday`.
        const top3 = journal.data?.data?.top3?.length ? journal.data.data.top3
            : hour >= 4 ? journal.data?.yesterday?.top3 || [] : [];
        body = (
            <div className="space-y-3.5">
                <p className="text-sm text-muted">Screens down soon. The work you put in today only sticks if you sleep on it.</p>
                {top3.length ? (
                    <div>
                        <div className="eyebrow mb-2">Tomorrow's top 3</div>
                        <Top3List items={top3} />
                    </div>
                ) : (
                    <Button size="sm" variant="secondary" icon={ListPlus} onClick={openShutdown}>Set tomorrow's top 3</Button>
                )}
            </div>
        );
    }

    return (
        <Card className="hero-accent relative overflow-hidden border-l-[3px] border-l-accent">
            <div className="card-pad">
                <div className="flex items-center justify-between gap-3">
                    <div className="eyebrow flex items-center gap-1.5 text-accent">
                        <PhaseIcon className="h-3.5 w-3.5" /> {meta.eyebrow}
                    </div>
                    <span className="text-[11px] font-medium text-subtle tabular-nums" title="India Standard Time">{timeLabel} IST</span>
                </div>
                <h2 className="mt-1 mb-3.5 text-lg sm:text-xl font-bold tracking-tight">{meta.title}</h2>
                {body}
            </div>
        </Card>
    );
}

function ClosedLine() {
    return (
        <div className="flex items-center gap-2.5 rounded-xl bg-ok/10 border border-ok/25 px-3 py-2.5 text-sm">
            <Check className="h-4 w-4 text-ok shrink-0" strokeWidth={3} />
            <span>Day closed. <span className="text-muted">Rest well.</span></span>
        </div>
    );
}

function Morning({ top3, todos, onAdded, facts }) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const planned = new Set((todos || []).map((t) => norm(t.text)));
    const missing = top3.filter((t) => !planned.has(norm(t)));

    const addAll = async () => {
        setBusy(true);
        let added = 0;
        try {
            for (const text of missing) {
                await api('/todos', { method: 'POST', body: { text } });
                added += 1;
            }
            toast(`Added ${added} to today's plan`);
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setBusy(false);
            if (added) onAdded?.();
        }
    };

    return (
        <div className="space-y-3.5">
            {top3.length ? (
                <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="eyebrow">Last night's top 3</div>
                        {missing.length > 0 ? (
                            <Button size="sm" variant="secondary" icon={ListPlus} loading={busy} onClick={addAll} disabled={!todos || busy}>
                                Add to plan
                            </Button>
                        ) : (
                            <span className="text-xs font-medium text-ok inline-flex items-center gap-1"><Check className="h-3.5 w-3.5" /> On your plan</span>
                        )}
                    </div>
                    <Top3List items={top3} planned={planned} />
                </div>
            ) : (
                <p className="text-sm text-muted">No game plan from last night. Pick the 3 things that would make today a win and add them below.</p>
            )}
            <div className="flex flex-wrap gap-2 empty:hidden">{facts}</div>
        </div>
    );
}

function DeepWork({ nowMs, open, doneCount, loading, firstProblem, contests, onPlanChange, setTodos }) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const top = open[0];
    const contest = (contests || []).find((c) => {
        const start = new Date(c.start).getTime();
        return c.running || (start > nowMs && start - nowMs <= 6 * HOUR);
    });

    const startFocus = () => {
        window.dispatchEvent(new CustomEvent('focus-timer', { detail: { action: 'start' } }));
        scrollToSection('focus-timer');
    };

    const setDone = async (t, done) => {
        setTodos((list) => (list || []).map((x) => (x.id === t.id ? { ...x, done } : x)));
        try {
            await api(`/todos/${t.id}`, { method: 'PUT', body: { done } });
            onPlanChange?.();
            if (done) toast(`Done: ${t.text}`, 'success', { action: { label: 'Undo', onClick: () => setDone(t, false) } });
        } catch (e) {
            toast(e.message, 'error');
            onPlanChange?.();
        }
    };

    const markTop = async () => {
        setBusy(true);
        await setDone(top, true);
        setBusy(false);
    };

    return (
        <div className="space-y-3.5">
            {loading ? (
                <Skeleton className="h-12 w-full" />
            ) : top ? (
                <div>
                    <div className="eyebrow mb-1">Now</div>
                    <p className="text-base sm:text-[17px] font-semibold leading-snug break-words [overflow-wrap:anywhere]">{top.text}</p>
                    <p className="mt-1 text-xs text-subtle">
                        {open.length - 1 ? `${open.length - 1} more after this` : 'Last one on the plan'}
                        {doneCount > 0 && ` · ${doneCount} done`}
                    </p>
                </div>
            ) : firstProblem ? (
                <div>
                    <div className="eyebrow mb-1">Plan clear · next rep</div>
                    <button type="button" onClick={() => navigate(`problems/${firstProblem.id}`)}
                        className="text-left text-base sm:text-[17px] font-semibold leading-snug hover:text-accent transition-colors">
                        {firstProblem.title}
                    </button>
                </div>
            ) : (
                <p className="text-sm text-muted">Plan is clear and the inbox is empty. Add a task below, or start a focus block on revision.</p>
            )}

            <div className="flex flex-wrap items-center gap-2">
                <Button variant="primary" icon={Play} onClick={startFocus}>Start focus</Button>
                {top && <Button variant="secondary" icon={Check} loading={busy} onClick={markTop}>Done</Button>}
                {!top && firstProblem && (
                    <Button variant="ghost" onClick={() => navigate(`problems/${firstProblem.id}`)}>Open <ArrowRight className="h-3.5 w-3.5" /></Button>
                )}
            </div>

            {contest && (
                <div className="flex flex-wrap gap-2">
                    <Fact icon={contest.running ? Radio : Trophy} href={contest.url}>
                        {contest.name} · {contest.running ? 'live now' : `in ${fmtSpan(new Date(contest.start).getTime() - nowMs)}`}
                    </Fact>
                </div>
            )}
        </div>
    );
}
