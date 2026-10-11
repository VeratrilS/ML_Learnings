import { useEffect, useState } from 'react';
import {
    BookOpen, CalendarClock, CalendarDays, Code2, Flame, GraduationCap, History, Medal, RotateCcw,
    ScrollText, Shuffle, Sunrise, Swords, Target, Timer, Trophy, Volume2, VolumeX,
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { getMode, haptic, play, setMode } from '../lib/sfx';
import BossCard, { DamageRow } from '../components/BossCard';
import RingsCard from '../components/RingsCard';
import { Button, Card, CardHeader, Empty, ProgressBar, Segmented, Skeleton, cx, useToast } from '../components/ui';

const parseDay = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const fmtDay = (s, opts = { day: 'numeric', month: 'short' }) => (s ? parseDay(s).toLocaleDateString(undefined, opts) : '');

function usePoll(reload, ms) {
    useEffect(() => {
        const tick = () => { if (document.visibilityState === 'visible') reload({ silent: true }); };
        const id = setInterval(tick, ms);
        document.addEventListener('visibilitychange', tick);
        return () => { clearInterval(id); document.removeEventListener('visibilitychange', tick); };
    }, [reload, ms]);
}

function SectionTitle({ icon: Icon, title, subtitle }) {
    return (
        <div className="flex items-end gap-2.5 px-0.5">
            <Icon className="h-4 w-4 text-accent mb-1 shrink-0" aria-hidden />
            <div className="min-w-0">
                <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
                {subtitle && <p className="text-xs text-subtle">{subtitle}</p>}
            </div>
        </div>
    );
}

// ---------------- sound ----------------
const SOUND_OPTIONS = [
    { value: 'off', label: 'Off' },
    { value: 'big', label: 'Bells' },
    { value: 'all', label: 'All' },
];

function SoundToggle() {
    const [mode, setM] = useState(getMode);
    useEffect(() => {
        const on = (e) => setM(e.detail);
        window.addEventListener('sfx-mode', on);
        return () => window.removeEventListener('sfx-mode', on);
    }, []);
    const change = (m) => {
        setM(setMode(m));
        if (m === 'all') { play('jab', { force: true }); haptic(30); }
        if (m === 'big') play('bell', { force: true });
    };
    const Icon = mode === 'off' ? VolumeX : Volume2;
    return (
        <div className="flex items-center gap-2" title="Off: silent · Bells: ring closures and the bell · All: every punch too">
            <Icon className="h-4 w-4 text-subtle shrink-0" aria-hidden />
            <span className="sr-only">Sound effects</span>
            <Segmented options={SOUND_OPTIONS} value={mode} onChange={change} />
        </div>
    );
}

// ---------------- quest ----------------
const QUEST_ICON = {
    medium_weak: Target, clear_revisions: RotateCcw, morning_focus: Sunrise,
    sd_lessons: BookOpen, syllabus_3: GraduationCap, oldest_pending: History,
};

function QuestCard({ quest, setQuest, error, loading, reload }) {
    const toast = useToast();
    const [skipping, setSkipping] = useState(false);

    // Completing the quest (seen live, not on first load) lands a combo.
    useEffect(() => {
        if (!quest) return;
        const key = `gym:quest:${quest.date}:${quest.key}`;
        let prev = null;
        try { prev = sessionStorage.getItem(key); } catch { /* storage unavailable */ }
        try { sessionStorage.setItem(key, quest.done ? '1' : '0'); } catch { /* storage unavailable */ }
        if (prev === '0' && quest.done) { play('combo'); haptic(40); }
    }, [quest]);

    const skip = async () => {
        setSkipping(true);
        try {
            const res = await api('/gym/quest/skip', { method: 'POST' });
            setQuest(res.data);
            play('jab');
            toast('New quest drawn. That was your skip for today.', 'info');
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setSkipping(false);
        }
    };

    if (!quest) {
        return (
            <Card className="card-pad h-full">
                <Skeleton className="h-4 w-32 mb-4" />
                {error && !loading
                    ? <p className="text-sm text-subtle">Couldn't load the quest. <button className="text-accent font-medium" onClick={() => reload()}>Retry</button></p>
                    : <><Skeleton className="h-6 w-3/4 mb-2" /><Skeleton className="h-3 w-1/2 mb-5" /><Skeleton className="h-2 w-full" /></>}
            </Card>
        );
    }

    const Icon = QUEST_ICON[quest.key] || Target;
    const pct = quest.goal ? (quest.progress / quest.goal) * 100 : 0;
    return (
        <Card className={cx('card-pad h-full flex flex-col', quest.done && 'hero-accent')}>
            <CardHeader
                title="Today's quest"
                subtitle={quest.done ? 'Cleared. Nice footwork.' : 'Auto-completes from your data'}
                icon={Swords}
                action={<span className={cx('badge tabular-nums', quest.done ? 'text-ok bg-ok/10' : 'text-accent bg-accent-soft')}>+{quest.xp} XP</span>}
            />
            <div className="flex items-start gap-3">
                <div className={cx('grid place-items-center h-10 w-10 rounded-xl shrink-0', quest.done ? 'bg-ok/10 text-ok' : 'bg-accent-soft text-accent')}>
                    <Icon className="h-5 w-5" aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                    <p className={cx('text-[15px] font-semibold leading-snug', quest.done && 'text-muted')}>{quest.text}</p>
                    {quest.detail && <p className="text-xs text-subtle mt-0.5 truncate">{quest.detail}</p>}
                </div>
            </div>
            <div className="mt-4">
                <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-subtle">Progress</span>
                    <span className="tabular-nums font-medium">{quest.progress}/{quest.goal}</span>
                </div>
                <ProgressBar value={pct} color={quest.done ? 'var(--ok)' : 'var(--accent)'} />
            </div>
            <div className="mt-auto pt-4 flex items-center justify-between gap-3 flex-wrap">
                <p className="flex items-center gap-1.5 text-xs text-subtle min-w-0">
                    <CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span className="truncate">Tomorrow: <span className="text-muted">{quest.tomorrow_preview?.text || 'a surprise'}</span></span>
                </p>
                {!quest.done && (
                    <Button
                        size="sm" variant="ghost" icon={Shuffle} loading={skipping} onClick={skip}
                        disabled={!quest.skips_left}
                        title={quest.skips_left ? 'Draw a different quest (once a day)' : 'Already skipped today'}
                    >
                        {quest.skips_left ? 'Skip' : 'No skips left'}
                    </Button>
                )}
            </div>
        </Card>
    );
}

// ---------------- fight log ----------------
const TABLE_TONE = { Easy: 'text-easy bg-easy/10', Medium: 'text-medium bg-medium/10', Hard: 'text-hard bg-hard/10', review: 'text-muted bg-surface-2' };

function FightLog({ boss }) {
    if (!boss) {
        return <Card className="card-pad h-full"><Skeleton className="h-4 w-32 mb-4" /><Skeleton className="h-40 w-full" /></Card>;
    }
    const log = boss.damage_log || [];
    const history = boss.history || [];
    return (
        <Card className="card-pad h-full">
            <CardHeader
                title="Fight log"
                subtitle={`${boss.damage_total} damage in ${log.length} hit${log.length === 1 ? '' : 's'} this week`}
                icon={ScrollText}
            />
            <div className="flex flex-wrap gap-1.5 mb-4" aria-label="Damage per punch">
                {Object.entries(boss.damage_table || {}).map(([k, v]) => (
                    <span key={k} className={cx('badge tabular-nums', TABLE_TONE[k] || 'text-muted bg-surface-2')}>
                        {k === 'review' ? 'Review' : k} {v}
                    </span>
                ))}
            </div>
            {log.length ? (
                <ul className="space-y-2 max-h-56 overflow-y-auto pr-1 -mr-1">
                    {log.map((h, i) => <DamageRow key={`${h.at}-${i}`} hit={h} />)}
                </ul>
            ) : (
                <p className="text-[13px] text-subtle">No damage yet. Any {boss.topic} solve or review counts.</p>
            )}

            <h3 className="text-[11px] font-semibold uppercase tracking-[.12em] text-subtle mt-6 mb-2.5">Past bouts</h3>
            {history.length ? (
                <ul className="divide-y divide-line">
                    {history.map((h) => (
                        <li key={h.week_start} className="py-2.5 first:pt-0 last:pb-0 flex items-center gap-3">
                            <div className="min-w-0 flex-1">
                                <div className="flex items-baseline gap-2 min-w-0">
                                    <span className="text-sm font-medium truncate">{h.boss}</span>
                                    <span className="text-xs text-subtle truncate">{h.topic}</span>
                                </div>
                                <div className="flex items-center gap-2 mt-1">
                                    <ProgressBar
                                        className="flex-1 max-w-40"
                                        value={h.hp_max ? (Math.min(h.damage, h.hp_max) / h.hp_max) * 100 : 0}
                                        color={h.defeated ? 'var(--ok)' : 'var(--hard)'}
                                    />
                                    <span className="text-[11px] text-subtle tabular-nums whitespace-nowrap">wk of {fmtDay(h.week_start)}</span>
                                </div>
                            </div>
                            <span className={cx('badge shrink-0', h.defeated ? 'text-ok bg-ok/10' : 'text-subtle bg-surface-2')}>
                                {h.defeated ? `K.O.${h.ko_days ? ` · ${h.ko_days}d` : ''}` : 'Retreated'}
                            </span>
                        </li>
                    ))}
                </ul>
            ) : (
                <p className="text-[13px] text-subtle">Your first bout is this week.</p>
            )}
        </Card>
    );
}

// ---------------- records ----------------
const RECORD_ICON = { most_solves: Code2, best_focus: Timer, rings_streak: Flame, most_mediums: Medal, fastest_ko: Trophy };

function Records({ records, error }) {
    if (!records) {
        return error
            ? <Card className="card-pad"><p className="text-sm text-subtle">Couldn't load records.</p></Card>
            : <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>;
    }
    return (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
            {records.map((r, i) => {
                const Icon = RECORD_ICON[r.key] || Medal;
                const has = r.value != null && r.value !== 0;
                const when = r.date ? (r.key === 'most_mediums' ? `wk of ${fmtDay(r.date)}` : fmtDay(r.date, { day: 'numeric', month: 'short', year: '2-digit' })) : '';
                return (
                    <div
                        key={r.key}
                        className="card p-3.5 sm:p-4 flex flex-col min-w-0 animate-rise last:col-span-2 sm:last:col-span-1"
                        style={{ animationDelay: `${i * 50}ms` }}
                    >
                        <div className="flex items-center justify-between gap-2">
                            <Icon className={cx('h-4 w-4', has ? 'text-accent' : 'text-subtle')} aria-hidden />
                            {when && <span className="text-[10.5px] text-subtle tabular-nums truncate">{when}</span>}
                        </div>
                        <p className="mt-3 leading-none">
                            <span className={cx('text-2xl font-bold tracking-tight tabular-nums', !has && 'text-subtle')}>{has ? r.value : '—'}</span>
                            {has && <span className="text-xs text-subtle ml-1">{r.unit}</span>}
                        </p>
                        <p className="text-xs text-muted mt-1.5 leading-snug">{r.label}</p>
                        {r.detail && <p className="text-[11px] text-subtle truncate mt-0.5">{r.detail}</p>}
                    </div>
                );
            })}
        </div>
    );
}

// ---------------- rings heatmap ----------------
const LEVEL = ['bg-surface-3', 'bg-accent/30', 'bg-accent/60', 'bg-accent'];

function useWeeks() {
    const pick = () => (window.matchMedia('(min-width: 1024px)').matches ? 52 : window.matchMedia('(min-width: 640px)').matches ? 30 : 18);
    const [weeks, setWeeks] = useState(pick);
    useEffect(() => {
        const onResize = () => setWeeks(pick());
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);
    return weeks;
}

function cellTitle(d) {
    const parts = [`${d.closed}/3 rings`];
    if (d.rest) parts.push('exam rest day');
    if (d.recovery) parts.push('recovery round');
    if (d.perfect_week) parts.push('perfect week');
    return `${parts.join(' · ')} · ${parseDay(d.date).toDateString()}`;
}

function RingsHeatmap({ hist, error }) {
    if (!hist) {
        return (
            <Card className="card-pad">
                <Skeleton className="h-4 w-40 mb-4" />
                {error ? <p className="text-sm text-subtle">Couldn't load ring history.</p> : <Skeleton className="h-28 w-full" />}
            </Card>
        );
    }
    const days = hist.days || [];
    if (!days.length) return <Card className="card-pad"><Empty icon={CalendarDays} title="No history yet" /></Card>;

    const pad = (parseDay(days[0].date).getDay() + 6) % 7; // Monday-first columns
    const cells = [...Array(pad).fill(null), ...days];
    const weeks = [];
    for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
    const today = days[days.length - 1].date;
    const months = weeks.map((w, i) => {
        const d = w.find(Boolean);
        const prev = weeks[i - 1]?.find(Boolean);
        if (!d) return '';
        return !prev || parseDay(prev.date).getMonth() !== parseDay(d.date).getMonth() ? fmtDay(d.date, { month: 'short' }) : '';
    });

    return (
        <Card className="card-pad">
            <CardHeader
                title="Ring history"
                subtitle={`${hist.all_closed_days} perfect day${hist.all_closed_days === 1 ? '' : 's'} · ${hist.perfect_weeks} perfect week${hist.perfect_weeks === 1 ? '' : 's'} in ${weeks.length} weeks`}
                icon={CalendarDays}
                action={hist.streak > 0 && (
                    <span className="badge text-medium bg-medium/10 tabular-nums" title="Days in a row with all three rings closed (exam days don't break it)">
                        <Flame className="h-3 w-3" aria-hidden /> {hist.streak}d streak
                    </span>
                )}
            />
            <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}>
                {months.map((m, i) => <div key={`m${i}`} className="text-[10px] text-subtle h-4 overflow-visible whitespace-nowrap">{m}</div>)}
                {weeks.map((w, wi) => {
                    const perfect = w.some((d) => d?.perfect_week);
                    return (
                        <div
                            key={wi}
                            className={cx('grid grid-rows-7 gap-[3px] rounded-[4px]', perfect && 'outline-1 outline-solid outline-ok outline-offset-1')}
                            title={perfect ? 'Perfect week' : undefined}
                        >
                            {Array.from({ length: 7 }).map((_, di) => {
                                const d = w[di];
                                if (!d) return <div key={di} className="aspect-square" />;
                                return (
                                    <div
                                        key={di}
                                        title={cellTitle(d)}
                                        className={cx(
                                            'aspect-square rounded-[3px]',
                                            LEVEL[Math.max(0, Math.min(3, d.closed))],
                                            d.rest && 'outline-1 outline-dotted outline-muted -outline-offset-1',
                                            d.date === today && 'ring-1 ring-fg/50 ring-offset-1 ring-offset-surface',
                                        )}
                                    />
                                );
                            })}
                        </div>
                    );
                })}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-1.5 mt-3 text-[10.5px] text-subtle">
                <span className="inline-flex items-center gap-1.5 mr-auto">
                    <span className="h-2.5 w-2.5 rounded-[3px] outline-1 outline-solid outline-ok" aria-hidden />
                    perfect week
                    <span className="h-2.5 w-2.5 rounded-[3px] bg-surface-3 outline-1 outline-dotted outline-muted -outline-offset-1 ml-2" aria-hidden />
                    exam day
                </span>
                0
                {LEVEL.map((c) => <span key={c} className={cx('h-2.5 w-2.5 rounded-[3px]', c)} aria-hidden />)}
                3 rings
            </div>
        </Card>
    );
}

// ---------------- page ----------------
export default function Gym() {
    const quest = useApi('/gym/quest');
    const boss = useApi('/gym/boss');
    const records = useApi('/gym/records', { select: (d) => d.data.records });
    const weeks = useWeeks();
    const hist = useApi(`/gym/rings/history?days=${weeks * 7}`);
    usePoll(quest.reload, 60000);
    usePoll(boss.reload, 60000);
    usePoll(hist.reload, 300000);

    return (
        <div className="space-y-6 sm:space-y-8 min-w-0">
            <header className="animate-rise flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
                <div className="min-w-0">
                    <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Gym</h1>
                    <p className="text-sm text-muted mt-1">Close your rings. Beat this week's rival. Ding ding.</p>
                </div>
                <SoundToggle />
            </header>

            <div className="grid gap-4 lg:gap-6 lg:grid-cols-5 items-stretch">
                <RingsCard big className="lg:col-span-3" />
                <div className="lg:col-span-2 min-w-0">
                    <QuestCard quest={quest.data} setQuest={quest.setData} error={quest.error} loading={quest.loading} reload={quest.reload} />
                </div>
            </div>

            <section className="space-y-3">
                <SectionTitle icon={Swords} title="Boss fight" subtitle="Your weakest topic, one rival per week. Easy 20 · Medium 35 · Hard 60 · Review 10" />
                <div className="grid gap-4 lg:gap-6 lg:grid-cols-5 items-start">
                    <BossCard boss={boss.data ?? null} className="lg:col-span-2" />
                    <div className="lg:col-span-3 min-w-0">
                        {boss.error && !boss.data
                            ? <Card className="card-pad"><p className="text-sm text-subtle">{boss.error}</p></Card>
                            : <FightLog boss={boss.data} />}
                    </div>
                </div>
            </section>

            <section className="space-y-3">
                <SectionTitle icon={Trophy} title="Personal records" subtitle="Your best rounds, all time" />
                <Records records={records.data} error={records.error} />
            </section>

            <section className="space-y-3">
                <SectionTitle icon={Flame} title="Consistency" subtitle="Rings closed per day. 5+ perfect days in a week makes a perfect week." />
                <RingsHeatmap hist={hist.data} error={hist.error} />
            </section>
        </div>
    );
}
