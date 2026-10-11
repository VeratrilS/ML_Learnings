import { Suspense, useState } from 'react';
import { Flame, Trophy, Tv, Send, Swords, RefreshCw, ListTodo, ArrowRight, Sparkles, Zap } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Empty, ProgressRing, Skeleton, useToast, cx } from '../components/ui';
import NowCard from '../components/NowCard';
import ShutdownCard from '../components/ShutdownCard';
import RankBadge from '../components/RankBadge';
import EpisodeCard from '../components/EpisodeCard';
import LearnCard from '../components/LearnCard';
import { FEATURES, useFeatures } from '../lib/features';
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

// Accepts both a raw string and a JSON-encoded one (useLocalStorage stores JSON).
function profileName() {
    try {
        const raw = localStorage.getItem('profile:name');
        if (!raw) return 'Sai';
        let v = raw;
        try { v = JSON.parse(raw); } catch { /* plain string */ }
        return (typeof v === 'string' && v.trim()) || 'Sai';
    } catch {
        return 'Sai';
    }
}

const fmt = (n) => Number(n || 0).toLocaleString();

/** One compact chip in the stat strip. */
function Chip({ icon: Icon, accent, value, label, title, children }) {
    return (
        <div className="card shrink-0 lg:flex-1 lg:min-w-0 h-14 flex items-center gap-2.5 pl-2.5 pr-3.5" title={title}>
            {children || (
                <div className={cx('grid place-items-center h-9 w-9 rounded-xl shrink-0',
                    accent ? 'bg-accent-soft text-accent' : 'bg-surface-2 text-muted')}>
                    <Icon className="h-4 w-4" />
                </div>
            )}
            <div className="min-w-0 leading-none">
                <div className="text-[17px] font-bold tracking-tight tabular-nums whitespace-nowrap">{value}</div>
                <div className="mt-1 text-[11px] font-medium text-subtle whitespace-nowrap truncate">{label}</div>
            </div>
        </div>
    );
}

function StatStrip({ s, goal, xp }) {
    return (
        <div className="-mx-4 sm:-mx-6 lg:mx-0 overflow-x-auto no-scrollbar lg:overflow-visible">
            <div className="flex gap-2.5 px-4 sm:px-6 lg:px-0 py-1 w-max lg:w-auto">
                {s ? (
                    <>
                        <Chip
                            value={<>{s.today.solved}<span className="text-subtle text-sm font-semibold">/{goal}</span></>}
                            label={s.today.solved >= goal ? 'goal hit' : 'solved today'}
                            title="Problems solved today vs your daily goal"
                        >
                            <ProgressRing value={s.today.solved} max={goal} size={36} stroke={4} />
                        </Chip>
                        <Chip icon={Flame} accent value={`${s.streak}d`} label={`streak · best ${s.best_streak}`} />
                        <Chip icon={Trophy} value={fmt(s.totals.lc_solved + s.totals.cf_solved)}
                            label={`${s.totals.lc_solved} LC · ${s.totals.cf_solved} CF`} title="Problems solved" />
                        <Chip icon={Tv} value={fmt(s.totals.episodes)} label={s.watch_streak ? `episodes · ${s.watch_streak}d run` : 'episodes'} />
                        {xp && (
                            <Chip icon={Zap} accent value={xp.today_xp ? `+${fmt(xp.today_xp)}` : fmt(xp.xp)}
                                label={xp.today_xp ? `XP today · ${xp.rank}` : `XP · ${xp.rank}`} title={`${fmt(xp.xp)} XP total`} />
                        )}
                    </>
                ) : (
                    Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 w-36 lg:flex-1 rounded-2xl shrink-0" />)
                )}
            </div>
        </div>
    );
}

const SECTION = 'scroll-mt-20 lg:scroll-mt-6 min-w-0';

/**
 * Props: `stats` (useApi('/stats')), optional `xp` (useApi('/xp')) from App so the sidebar and page share one fetch.
 */
export default function Today({ stats, xp }) {
    const features = useFeatures();
    const s = stats.data;
    const pending = useApi('/logs?type=leetcode', { select: (d) => d.data.filter((l) => !l.is_completed) });
    const settings = useApi('/settings', { select: (d) => d });
    const toast = useToast();
    const [sending, setSending] = useState(false);
    const [syncing, setSyncing] = useState(false);
    // rev: anything on the plan/journal changed (cards refetch). planKey: changed outside PlanCard (remount it).
    const [rev, setRev] = useState(0);
    const [planKey, setPlanKey] = useState(0);
    const [name] = useState(profileName);
    const [quote] = useState(() => QUOTES[Math.floor(Date.now() / 86400000) % QUOTES.length]);
    const goal = s?.today.goal || 2;

    const reloadXp = () => xp?.reload?.({ silent: true });
    const refresh = () => { pending.reload({ silent: true }); stats.reload({ silent: true }); };
    const planChangedInside = () => { setRev((r) => r + 1); reloadXp(); };
    const planChangedOutside = () => { setRev((r) => r + 1); setPlanKey((k) => k + 1); reloadXp(); };
    const progressChanged = () => { stats.reload({ silent: true }); reloadXp(); };

    const toggle = async (log, value) => {
        pending.setData((list) => list.map((l) => (l.id === log.id ? { ...l, is_completed: value } : l)));
        try {
            await api(`/logs/${log.id}`, { method: 'PUT', body: { is_completed: value } });
            if (value) toast(`Solved: ${log.title}`, 'success', { action: { label: 'Undo', onClick: () => toggle(log, false) } });
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

    const upNext = (
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
    );

    return (
        <div className="space-y-4 sm:space-y-5">
            <header className="animate-rise">
                <p className="text-xs sm:text-sm text-subtle font-medium">
                    {new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
                </p>
                <h1 className="mt-0.5 text-2xl sm:text-3xl font-bold tracking-tight truncate">{greeting()}, {name}.</h1>
                <p className="hidden sm:block mt-1 text-sm text-muted truncate max-w-2xl" title={quote[1] ? `${quote[0]} — ${quote[1]}` : quote[0]}>
                    <span className="italic">“{quote[0]}”</span>
                    {quote[1] && <span className="text-subtle"> — {quote[1]}</span>}
                </p>
            </header>

            <StatStrip s={s} goal={goal} xp={xp?.data} />

            {/* Mobile: one column ordered by `order-*` (the column wrappers are display:contents).
                Desktop: main column (span 2) + side column. */}
            <div className="flex flex-col gap-5 lg:grid lg:grid-cols-3 lg:gap-6 lg:items-start">
                <div className="contents lg:flex lg:flex-col lg:gap-6 lg:col-span-2 lg:min-w-0">
                    {features.isOn('now') && (
                        <div className={cx(SECTION, 'order-1')}>
                            <NowCard rev={rev} onPlanChange={planChangedOutside} />
                        </div>
                    )}
                    <div id="plan" className={cx(SECTION, 'order-2')}>
                        <PlanCard key={planKey} onChange={planChangedInside} />
                    </div>
                    <div className={cx(SECTION, 'order-3')}>{upNext}</div>
                    <div id="episode" className={cx(SECTION, 'duo order-4 grid gap-5 lg:gap-6 xl:grid-cols-2 xl:items-start')}>
                        <EpisodeCard onChange={progressChanged} />
                        <LearnCard onChange={progressChanged} />
                    </div>
                    <div id="revisions" className={cx(SECTION, 'order-6')}><RevisionCard /></div>
                    {/* Cards of approved Beta Lab features */}
                    <Suspense fallback={null}>
                        {FEATURES.filter((f) => features.isOn(f.id)).flatMap((f) => f.cards.map((C, i) => (
                            <div key={`${f.id}-${i}`} className={cx(SECTION, 'order-7')}><C /></div>
                        )))}
                    </Suspense>
                    {features.isOn('shutdown') && (
                        <div id="shutdown" className={cx(SECTION, 'order-9')}>
                            <ShutdownCard rev={rev} onPlanChange={planChangedOutside} onSaved={() => setRev((r) => r + 1)} />
                        </div>
                    )}
                </div>

                <div className="contents lg:flex lg:flex-col lg:gap-6 lg:min-w-0">
                    <div id="focus-timer" className={cx(SECTION, 'order-10 lg:order-0')}><FocusTimer /></div>
                    {features.isOn('ranks') && <div className={cx(SECTION, 'hidden lg:block')}><RankBadge variant="tile" data={xp ? xp.data : undefined} /></div>}
                    <div className={cx(SECTION, 'order-11 lg:order-0')}><ContestsCard limit={4} /></div>
                    <div className={cx(SECTION, 'order-8 lg:order-0')}><StudyCard /></div>
                    <div className={cx(SECTION, 'order-12 lg:order-0')}><LeetCodeCard /></div>
                </div>
            </div>

            <Heatmap days={s?.heatmap} />
        </div>
    );
}
