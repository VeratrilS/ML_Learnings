import { useMemo, useState } from 'react';
import { GraduationCap, BookOpen, ArrowRight, CalendarClock, Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Checkbox, Empty, ProgressBar, ProgressRing, Skeleton, useToast, cx } from './ui';

// Keep in sync with the palette on the Study page
const COLORS = {
    violet: '#7c5cff', teal: '#0d9488', rose: '#e11d48', amber: '#d97706',
    blue: '#2563eb', green: '#16a34a', pink: '#db2777', orange: '#e8590c',
};
const hexOf = (s) => COLORS[s?.color] || (/^#[0-9a-f]{3,8}$/i.test(s?.color || '') ? s.color : 'var(--accent)');

const parseDay = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const fmtDate = (s) => parseDay(s).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });

function daysTone(d) {
    if (d == null || d < 0) return 'text-subtle';
    if (d <= 7) return 'text-danger';
    if (d <= 14) return 'text-accent';
    return 'text-muted';
}
function daysShort(d) {
    if (d == null) return 'no date';
    if (d < 0) return 'done';
    if (d === 0) return 'today';
    if (d === 1) return 'tomorrow';
    return `${d}d`;
}

// Upcoming exams first (nearest first), then undated, then finished.
const examRank = (s) => (s.days_left == null ? 1e6 : s.days_left < 0 ? 2e6 : s.days_left);

function suggestions(theory, limit = 3) {
    const ranked = [...theory].sort((a, b) => examRank(a) - examRank(b));
    const out = [];
    ranked.forEach((s, rank) => {
        s.units.forEach((u) => u.topics.forEach((t) => {
            if (!t.done) out.push({ ...t, subject: s, rank });
        }));
    });
    out.sort((a, b) => a.rank - b.rank
        || (a.confidence ?? 1) - (b.confidence ?? 1)
        || Number(!!a.last_studied_at) - Number(!!b.last_studied_at)
        || (a.last_studied_at || '').localeCompare(b.last_studied_at || '')
        || a.position - b.position);
    return out.slice(0, limit);
}

export default function StudyCard() {
    const { data, loading, error, setData, reload } = useApi('/syllabus', { select: (d) => d });
    const [justDone, setJustDone] = useState({}); // id -> topic, kept visible briefly after ticking
    const toast = useToast();

    const theory = useMemo(() => (data?.data || []).filter((s) => s.kind === 'theory'), [data]);
    const total = theory.reduce((n, s) => n + s.total, 0);
    const done = theory.reduce((n, s) => n + s.done, 0);
    const pct = total ? Math.round((100 * done) / total) : 0;
    const next = data?.next_exam;
    const nextSubject = next && theory.find((s) => s.id === next.id);
    const picks = useMemo(() => suggestions(theory), [theory]);
    const shown = [...Object.values(justDone), ...picks.filter((t) => !justDone[t.id])].slice(0, 3);

    const mark = async (topic, value) => {
        setJustDone((m) => {
            const copy = { ...m };
            if (value) copy[topic.id] = { ...topic, done: true }; else delete copy[topic.id];
            return copy;
        });
        // Optimistically update the subject so the percentages move right away
        setData((d) => ({
            ...d,
            data: d.data.map((s) => {
                if (s.id !== topic.subject_id) return s;
                const units = s.units.map((u) => ({ ...u, topics: u.topics.map((t) => (t.id === topic.id ? { ...t, done: value } : t)) }));
                const n = units.reduce((k, u) => k + u.topics.filter((t) => t.done).length, 0);
                return { ...s, units, done: n, progress: s.total ? Math.round((100 * n) / s.total) : 0 };
            }),
        }));
        try {
            await api(`/syllabus/topics/${topic.id}`, { method: 'PUT', body: { done: value } });
            if (value) {
                toast(`Covered: ${topic.title}`);
                setTimeout(() => setJustDone((m) => { const copy = { ...m }; delete copy[topic.id]; return copy; }), 1400);
            }
        } catch (e) {
            toast(e.message, 'error');
            setJustDone((m) => { const copy = { ...m }; delete copy[topic.id]; return copy; });
            reload({ silent: true });
        }
    };

    if (loading && !data) {
        return (
            <Card className="card-pad">
                <Skeleton className="h-8 w-40 mb-5" />
                <Skeleton className="h-16 w-full mb-4" />
                <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-7" />)}</div>
            </Card>
        );
    }
    if (error && !data) {
        return <Card className="card-pad"><CardHeader title="End-sem prep" icon={GraduationCap} /><p className="text-sm text-danger">{error}</p></Card>;
    }
    if (!theory.length || !total) {
        return (
            <Card className="card-pad">
                <CardHeader title="End-sem prep" icon={GraduationCap} />
                <Empty icon={BookOpen} title={theory.length ? 'Paste your syllabus' : 'Add your subjects'}
                    action={<Button size="sm" variant="primary" icon={ArrowRight} onClick={() => navigate('study')}>Set up study plan</Button>}>
                    Copy each subject&apos;s syllabus into the study plan to get an exam countdown and daily “study next” picks.
                </Empty>
            </Card>
        );
    }

    const hex = nextSubject ? hexOf(nextSubject) : 'var(--accent)';
    const d = next?.days_left;

    return (
        <Card className="relative overflow-hidden">
            <div aria-hidden className="pointer-events-none absolute -top-24 -right-20 h-56 w-56 rounded-full opacity-[0.12] blur-3xl" style={{ background: hex }} />
            <div className="relative card-pad">
                <CardHeader title="End-sem prep" subtitle={`${done} of ${total} topics covered`} icon={GraduationCap}
                    action={(
                        <ProgressRing value={done} max={total} size={40} stroke={4}>
                            <span className="text-[10px] font-bold tabular-nums">{pct}%</span>
                        </ProgressRing>
                    )} />

                {/* Next exam */}
                <div className="flex items-center gap-3.5 rounded-xl border border-line bg-surface-2/60 p-3">
                    {next ? (
                        <>
                            <div className="text-center shrink-0 w-14">
                                <div className="text-3xl font-extrabold tracking-tighter leading-none tabular-nums" style={{ color: hex }}>
                                    {d}
                                </div>
                                <div className="text-[10px] font-semibold uppercase tracking-wider text-subtle mt-1">{d === 1 ? 'day' : 'days'}</div>
                            </div>
                            <div className="min-w-0 border-l border-line pl-3.5">
                                <div className="eyebrow">{d === 0 ? 'Exam today' : d === 1 ? 'Exam tomorrow' : 'Next exam'}</div>
                                <div className="text-sm font-semibold truncate mt-0.5">{next.short || next.subject}</div>
                                <div className="text-xs text-subtle truncate">{fmtDate(next.date)}{next.short ? ` · ${next.subject}` : ''}</div>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="grid place-items-center h-10 w-10 rounded-xl bg-surface border border-line text-subtle shrink-0">
                                <CalendarClock className="h-4 w-4" />
                            </div>
                            <div className="min-w-0">
                                <div className="text-sm font-medium">No exam dates yet</div>
                                <button onClick={() => navigate('study')} className="text-xs text-accent hover:underline">Add dates for a countdown</button>
                            </div>
                        </>
                    )}
                </div>

                {/* Per-subject progress */}
                <ul className="mt-4 space-y-3">
                    {theory.map((s) => (
                        <li key={s.id}>
                            <div className="flex items-center gap-2 text-[13px]">
                                <span className="h-2 w-2 rounded-full shrink-0" style={{ background: hexOf(s) }} />
                                <span className="font-medium truncate min-w-0 flex-1" title={s.name}>{s.short || s.name}</span>
                                <span className={cx('text-xs tabular-nums shrink-0', daysTone(s.days_left))}>{daysShort(s.days_left)}</span>
                                <span className="text-xs font-semibold tabular-nums w-9 text-right shrink-0">{s.total ? `${s.progress}%` : '—'}</span>
                            </div>
                            <ProgressBar value={s.progress} color={s.progress >= 100 ? 'var(--ok)' : hexOf(s)} className="mt-1.5 h-1" />
                        </li>
                    ))}
                </ul>

                {/* Study next */}
                <div className="mt-5">
                    <div className="eyebrow flex items-center gap-1.5 mb-1.5"><Sparkles className="h-3.5 w-3.5 text-accent" /> Study next</div>
                    {shown.length ? (
                        <ul className="-mx-2">
                            {shown.map((t) => (
                                <li key={t.id} className="flex items-start gap-2.5 rounded-lg px-2 py-2 row-hover">
                                    <Checkbox checked={!!t.done} onChange={(v) => mark(t, v)} label={`Mark ${t.title} done`} className="mt-px" />
                                    <div className="min-w-0 flex-1">
                                        <div className={cx('text-[13.5px] leading-snug break-words', t.done && 'line-through text-subtle')}>{t.title}</div>
                                        <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-subtle min-w-0">
                                            <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: hexOf(t.subject) }} />
                                            <span className="truncate">{[t.subject.short || t.subject.name, t.unit?.split(' · ')[0]].filter(Boolean).join(' · ')}</span>
                                            {t.confidence === 1 && <span className="text-danger font-medium shrink-0">· shaky</span>}
                                        </div>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="text-sm text-ok font-medium py-2">Everything covered. Time to revise.</p>
                    )}
                </div>

                <Button className="w-full mt-3" icon={ArrowRight} onClick={() => navigate('study')}>Open study plan</Button>
            </div>
        </Card>
    );
}
