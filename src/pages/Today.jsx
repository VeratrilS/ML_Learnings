import { useState } from 'react';
import { Flame, Target, Trophy, Tv, Send, Swords, RefreshCw, ListTodo, ArrowRight, Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Empty, ProgressRing, Skeleton, useToast } from '../components/ui';
import EpisodeCard from '../components/EpisodeCard';
import FocusTimer from '../components/FocusTimer';
import Heatmap from '../components/Heatmap';
import ProblemRow from '../components/ProblemRow';
import PlanCard from '../components/PlanCard';
import RevisionCard from '../components/RevisionCard';
import ContestsCard from '../components/ContestsCard';
import LeetCodeCard from '../components/LeetCodeCard';
import StudyCard from '../components/StudyCard';

const QUOTES = [
    ['Not everyone who works hard is rewarded. But all those who succeed have worked hard.', 'Kamogawa Genji'],
    ['What does it mean to be strong?', 'Makunouchi Ippo'],
    ['One more rep. One more problem. One more round.', null],
    ['Consistency beats intensity. Show up today.', null],
    ['The jab you throw every day becomes the punch that wins.', null],
];

function greeting() {
    const h = new Date().getHours();
    if (h < 5) return 'Still up';
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
}

function Stat({ icon: Icon, label, value, sub, accent }) {
    return (
        <Card className="p-4">
            <div className="flex items-center gap-2 text-subtle">
                <Icon className={accent ? 'h-4 w-4 text-accent' : 'h-4 w-4'} />
                <span className="text-xs font-medium">{label}</span>
            </div>
            <div className="mt-2 text-2xl sm:text-[28px] font-bold tracking-tight tabular-nums leading-none">{value}</div>
            {sub && <div className="mt-1.5 text-xs text-subtle truncate">{sub}</div>}
        </Card>
    );
}

export default function Today({ stats }) {
    const s = stats.data;
    const pending = useApi('/logs?type=leetcode', { select: (d) => d.data.filter((l) => !l.is_completed) });
    const settings = useApi('/settings', { select: (d) => d });
    const toast = useToast();
    const [sending, setSending] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const quote = QUOTES[Math.floor(Date.now() / 86400000) % QUOTES.length];
    const goal = s?.today.goal || 2;

    const refresh = () => { pending.reload({ silent: true }); stats.reload({ silent: true }); };

    const toggle = async (log, value) => {
        pending.setData((list) => list.map((l) => (l.id === log.id ? { ...l, is_completed: value } : l)));
        try {
            await api(`/logs/${log.id}`, { method: 'PUT', body: { is_completed: value } });
            if (value) toast(`Solved: ${log.title}`);
            stats.reload({ silent: true });
            setTimeout(() => pending.reload({ silent: true }), 900);
        } catch (e) {
            toast(e.message, 'error');
            pending.reload({ silent: true });
        }
    };

    const sendNew = async () => {
        setSending(true);
        try {
            const res = await api('/trigger', { method: 'POST', body: { type: 'leetcode' } });
            toast(`Sent to your inbox: ${res.data.title}`);
            refresh();
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setSending(false);
        }
    };

    const sync = async () => {
        setSyncing(true);
        try {
            const res = await api('/leetcode/sync', { method: 'POST' });
            toast(res.updated.length ? `Marked ${res.updated.length} solved from LeetCode` : 'Already up to date', res.updated.length ? 'success' : 'info');
            refresh();
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setSyncing(false);
        }
    };

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="animate-rise">
                <p className="text-sm text-subtle font-medium">
                    {new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
                </p>
                <h1 className="mt-1 text-[28px] sm:text-4xl font-bold tracking-tight">{greeting()}, Sai.</h1>
                <p className="mt-2 text-sm text-muted max-w-xl">
                    <span className="italic">“{quote[0]}”</span>
                    {quote[1] && <span className="text-subtle"> — {quote[1]}</span>}
                </p>
            </header>

            {/* Stat tiles */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {s ? (
                    <>
                        <Card className="p-4 flex items-center gap-3.5">
                            <ProgressRing value={s.today.solved} max={goal} size={58} stroke={6}>
                                <Target className="h-4 w-4 text-subtle" />
                            </ProgressRing>
                            <div className="min-w-0">
                                <div className="text-xs font-medium text-subtle">Today</div>
                                <div className="text-2xl font-bold tracking-tight tabular-nums leading-tight">
                                    {s.today.solved}<span className="text-subtle text-base font-semibold">/{goal}</span>
                                </div>
                                <div className="text-xs text-subtle truncate">{s.today.solved >= goal ? 'Goal hit 🎯' : 'daily goal'}</div>
                            </div>
                        </Card>
                        <Stat icon={Flame} accent label="Streak" value={`${s.streak}d`} sub={`best ${s.best_streak} days`} />
                        <Stat icon={Trophy} label="Solved" value={s.totals.lc_solved + s.totals.cf_solved}
                            sub={`${s.totals.lc_solved} LC · ${s.totals.cf_solved} CF`} />
                        <Stat icon={Tv} label="Episodes" value={s.totals.episodes} sub={s.watch_streak ? `${s.watch_streak}-day watch streak` : 'one a day'} />
                    </>
                ) : (
                    Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[98px] rounded-2xl" />)
                )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 sm:gap-6">
                <div className="lg:col-span-2 space-y-5 sm:space-y-6">
                    <EpisodeCard onChange={() => stats.reload({ silent: true })} />
                    <PlanCard />

                    <Card className="overflow-hidden">
                        <div className="card-pad pb-0">
                            <CardHeader
                                title="Up next"
                                subtitle={pending.data ? `${pending.data.length} pending problem${pending.data.length === 1 ? '' : 's'}` : 'Loading…'}
                                icon={ListTodo}
                                action={
                                    <>
                                        {settings.data?.leetcode_username && (
                                            <Button size="sm" variant="ghost" icon={RefreshCw} loading={syncing} onClick={sync} title="Sync solved from LeetCode">
                                                <span className="hidden sm:inline">Sync</span>
                                            </Button>
                                        )}
                                        <Button size="sm" variant="ghost" onClick={() => navigate('problems')}>
                                            All <ArrowRight className="h-3.5 w-3.5" />
                                        </Button>
                                    </>
                                }
                                className="mb-2"
                            />
                        </div>
                        {pending.loading && !pending.data ? (
                            <div className="p-4 space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
                        ) : pending.data?.length ? (
                            <ul className="divide-y divide-line border-t border-line">
                                {pending.data.slice(0, 5).map((l) => <ProblemRow key={l.id} log={l} onToggle={toggle} compact />)}
                            </ul>
                        ) : (
                            <Empty icon={Sparkles} title="Inbox zero" action={<Button size="sm" variant="primary" icon={Send} loading={sending} onClick={sendNew}>Get a new problem</Button>}>
                                Every problem is solved. Pull a fresh one whenever you're ready.
                            </Empty>
                        )}
                        {!!pending.data?.length && (
                            <div className="flex flex-wrap gap-2 p-3 sm:px-4 border-t border-line bg-surface-2/40">
                                <Button size="sm" variant="secondary" icon={Send} loading={sending} onClick={sendNew}>New problem</Button>
                                <Button size="sm" variant="secondary" icon={Swords} onClick={() => navigate('cf')}>5 Codeforces problems</Button>
                            </div>
                        )}
                    </Card>
                    <RevisionCard />
                    <StudyCard />
                </div>

                <div className="space-y-5 sm:space-y-6">
                    <FocusTimer />
                    <ContestsCard limit={4} />
                    <LeetCodeCard />
                    <WeekCard week={s?.week} goal={goal} />
                </div>
            </div>

            <Heatmap days={s?.heatmap} />
        </div>
    );
}

function WeekCard({ week, goal }) {
    if (!week) return <Skeleton className="h-44 rounded-2xl" />;
    const max = Math.max(goal, ...week.map((d) => d.count), 1);
    const total = week.reduce((a, d) => a + d.count, 0);
    return (
        <Card className="card-pad">
            <div className="flex items-baseline justify-between mb-4">
                <div className="eyebrow">This week</div>
                <div className="text-sm"><span className="font-bold tabular-nums">{total}</span> <span className="text-subtle">solved</span></div>
            </div>
            <div className="flex items-end gap-2 h-24">
                {week.map((d, i) => {
                    const isToday = i === week.length - 1;
                    return (
                        <div key={d.date} className="flex-1 flex flex-col items-center gap-1.5 h-full">
                            <div className="flex-1 w-full flex items-end">
                                <div
                                    className="w-full rounded-md transition-all duration-700"
                                    title={`${d.count} solved`}
                                    style={{
                                        height: `${Math.max(6, (d.count / max) * 100)}%`,
                                        background: d.count ? (d.count >= goal ? 'var(--accent)' : 'color-mix(in srgb, var(--accent) 55%, transparent)') : 'var(--surface-3)',
                                    }}
                                />
                            </div>
                            <span className={isToday ? 'text-[11px] font-bold text-fg' : 'text-[11px] text-subtle'}>
                                {new Date(d.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'narrow' })}
                            </span>
                        </div>
                    );
                })}
            </div>
        </Card>
    );
}
