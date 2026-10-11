import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    ArrowRight, Brain, ChevronDown, Eye, Flame, Layers, Pencil, Plus, RotateCcw, Search, Sparkles, Timer, Trash2, Trophy,
} from 'lucide-react';
import { api } from '../lib/api';
import { invalidate, useApi, useLocalStorage } from '../lib/hooks';
import { Button, Card, Empty, ProgressBar, Segmented, Sheet, Skeleton, cx, useToast } from '../components/ui';

const SUBJECTS = ['OS', 'DBMS', 'CN', 'OOP', 'SQL'];
const SUBJECT_NAMES = {
    OS: 'Operating Systems', DBMS: 'Databases', CN: 'Computer Networks', OOP: 'Object-Oriented Programming', SQL: 'SQL',
};
const GRADES = [
    { grade: 'again', label: 'Again', key: '1', tone: 'text-danger', bar: 'var(--danger)' },
    { grade: 'hard', label: 'Hard', key: '2', tone: 'text-medium', bar: 'var(--medium)' },
    { grade: 'good', label: 'Good', key: '3', tone: 'text-ok', bar: 'var(--ok)' },
    { grade: 'easy', label: 'Easy', key: '4', tone: 'text-accent', bar: 'var(--accent)' },
];
const DIFF = { 1: 'Easy', 2: 'Medium', 3: 'Hard' };
const DIFF_TONE = { 1: 'text-easy bg-easy/10', 2: 'text-medium bg-medium/10', 3: 'text-hard bg-hard/10' };
const STATE_TONE = {
    new: 'text-accent bg-accent-soft', learning: 'text-medium bg-medium/10', review: 'text-muted bg-surface-2', mastered: 'text-ok bg-ok/10',
};
const MAX_REQUEUE = 2; // an 'again' card comes back at most this many times in one session

function fmtInterval(days) {
    if (days == null) return '';
    if (days < 1) return `${Math.max(1, Math.round(days * 24))}h`;
    if (days < 30) return `${Math.round(days)}d`;
    if (days < 365) return `${Math.round(days / 30)}mo`;
    return `${(days / 365).toFixed(days < 730 ? 0 : 1)}y`;
}

function fmtDuration(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
}

const isTyping = (el) => !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

// Answers are plain text: "- " lines are bullets, SQL / indented lines render as code.
const CODE_LINE = /^(\s{2,}|(SELECT|WITH|DELETE|UPDATE|INSERT|FROM|WHERE|GROUP BY|ORDER BY|JOIN|CREATE|ALTER|DROP)\b)/;
function AnswerText({ text, className }) {
    const blocks = [];
    for (const line of (text || '').split('\n')) {
        if (!line.trim()) continue;
        const kind = line.startsWith('- ') ? 'li' : CODE_LINE.test(line) ? 'code' : 'p';
        const last = blocks[blocks.length - 1];
        const value = kind === 'li' ? line.slice(2) : line;
        if (last && last.kind === kind && kind !== 'p') last.lines.push(value);
        else blocks.push({ kind, lines: [value] });
    }
    return (
        <div className={cx('space-y-2 text-[14.5px] leading-relaxed text-fg', className)}>
            {blocks.map((b, i) => {
                if (b.kind === 'li') {
                    return (
                        <ul key={i} className="space-y-1">
                            {b.lines.map((l, j) => (
                                <li key={j} className="flex gap-2">
                                    <span className="mt-[0.6em] h-1.5 w-1.5 rounded-full bg-accent/70 shrink-0" aria-hidden />
                                    <span className="min-w-0">{l}</span>
                                </li>
                            ))}
                        </ul>
                    );
                }
                if (b.kind === 'code') {
                    return (
                        <pre key={i} className="rounded-xl bg-surface-2 border border-line px-3 py-2 overflow-x-auto font-mono text-[12.5px] leading-relaxed whitespace-pre">
                            {b.lines.join('\n')}
                        </pre>
                    );
                }
                return <p key={i} className="text-fg/90">{b.lines[0]}</p>;
            })}
        </div>
    );
}

function SubjectChips({ subjects, value, onChange }) {
    const total = subjects.reduce((n, s) => n + s.total, 0);
    const mastered = subjects.reduce((n, s) => n + s.mastered, 0);
    const all = { subject: '', label: 'All', mastery: total ? Math.round((100 * mastered) / total) : 0 };
    return (
        <div className="-mx-4 px-4 sm:mx-0 sm:px-0 flex gap-2 overflow-x-auto no-scrollbar">
            {[all, ...subjects].map((s) => (
                <button
                    key={s.subject || 'all'}
                    type="button"
                    onClick={() => onChange(s.subject)}
                    className={cx('chip shrink-0 h-8 px-3', value === s.subject && 'chip-on')}
                    title={s.subject ? `${SUBJECT_NAMES[s.subject] || s.subject}: ${s.mastered}/${s.total} mastered` : 'All subjects'}
                >
                    <span className="font-semibold">{s.label || s.subject}</span>
                    <span className={cx('tabular-nums', value === s.subject ? 'text-accent/80' : 'text-subtle')}>{s.mastery}%</span>
                </button>
            ))}
        </div>
    );
}

function Stat({ label, value, icon: Icon, tone }) {
    return (
        <div className="rounded-xl bg-surface-2 border border-line px-3 py-2.5 min-w-0">
            <div className="eyebrow flex items-center gap-1">{Icon && <Icon className={cx('h-3 w-3', tone)} />}{label}</div>
            <div className="text-2xl font-bold tracking-tight tabular-nums mt-0.5">{value}</div>
        </div>
    );
}

// ---------------- Study session ----------------
function Flashcard({ card, flipped, onFlip }) {
    return (
        <div className="perspective-[1600px] animate-rise">
            <div
                role="button"
                tabIndex={0}
                aria-label={flipped ? 'Show question' : 'Show answer'}
                onClick={onFlip}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); onFlip(); } }}
                className={cx(
                    'grid transform-3d transition-transform duration-500 ease-[cubic-bezier(.2,.7,.2,1)] cursor-pointer outline-none rounded-2xl',
                    'focus-visible:ring-4 focus-visible:ring-accent-soft',
                    flipped && 'rotate-y-180',
                )}
            >
                <div className="[grid-area:1/1] backface-hidden card p-5 sm:p-8 min-h-[300px] sm:min-h-[340px] flex flex-col">
                    <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="badge text-muted bg-surface-2">{card.subject}</span>
                        <span className={cx('badge', DIFF_TONE[card.difficulty])}>{DIFF[card.difficulty]}</span>
                        {card.state === 'new' && <span className="badge text-accent bg-accent-soft">New</span>}
                        {card.lapses > 0 && <span className="badge text-danger bg-danger/10">{card.lapses} lapse{card.lapses > 1 ? 's' : ''}</span>}
                    </div>
                    <div className="flex-1 grid place-items-center py-8">
                        <p className="text-xl sm:text-2xl font-semibold tracking-tight text-center leading-snug max-w-xl text-balance">
                            {card.question}
                        </p>
                    </div>
                    <p className="text-xs text-subtle text-center flex items-center justify-center gap-1.5">
                        <Eye className="h-3.5 w-3.5" /> Tap or press <kbd className="font-mono text-[11px] px-1 rounded border border-line bg-surface-2">Space</kbd> to reveal
                    </p>
                </div>
                <div className="[grid-area:1/1] backface-hidden rotate-y-180 card p-5 sm:p-8 min-h-[300px] sm:min-h-[340px] flex flex-col cursor-auto">
                    <p className="text-[13px] font-medium text-muted leading-snug pb-3 mb-4 border-b border-line">{card.question}</p>
                    <AnswerText text={card.answer} className="flex-1" />
                    {card.tags?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-5">
                            {card.tags.map((t) => <span key={t} className="badge text-subtle bg-surface-2 font-medium">#{t}</span>)}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function FinishScreen({ tally, startedAt, counts, onAgain, onExit }) {
    const total = GRADES.reduce((n, g) => n + tally[g.grade], 0);
    const recalled = total - tally.again;
    const accuracy = total ? Math.round((100 * recalled) / total) : 0;
    const left = (counts?.due || 0) + (counts?.new || 0);
    const [elapsed] = useState(() => Date.now() - startedAt);
    return (
        <Card className="card-pad animate-pop text-center">
            <div className="mx-auto grid place-items-center h-14 w-14 rounded-2xl bg-accent-soft text-accent mb-3">
                <Trophy className="h-7 w-7" />
            </div>
            <h2 className="text-xl font-bold tracking-tight">Session complete</h2>
            <p className="text-sm text-muted mt-1">
                {accuracy >= 85 ? 'Sharp recall. These will stay with you.' : accuracy >= 60 ? 'Solid work. The misses will come back soon.' : 'Tough set. Repetition is doing its job.'}
            </p>
            <div className="grid grid-cols-3 gap-2 mt-5 text-left">
                <Stat label="Reviewed" value={total} icon={Layers} />
                <Stat label="Recall" value={`${accuracy}%`} icon={Brain} tone="text-ok" />
                <Stat label="Time" value={fmtDuration(elapsed)} icon={Timer} />
            </div>
            <div className="mt-4 space-y-2 text-left">
                {GRADES.map((g) => (
                    <div key={g.grade} className="flex items-center gap-3 text-[13px]">
                        <span className={cx('w-12 font-medium', g.tone)}>{g.label}</span>
                        <ProgressBar value={total ? (100 * tally[g.grade]) / total : 0} color={g.bar} className="flex-1" />
                        <span className="w-6 text-right tabular-nums text-muted">{tally[g.grade]}</span>
                    </div>
                ))}
            </div>
            {counts?.streak > 0 && (
                <p className="mt-4 text-sm font-medium flex items-center justify-center gap-1.5">
                    <Flame className="h-4 w-4 text-accent" /> {counts.streak}-day streak
                </p>
            )}
            <div className="flex flex-col-reverse sm:flex-row gap-2 mt-5 sm:justify-center">
                <Button onClick={onExit}>Done</Button>
                {left > 0 && <Button variant="primary" icon={ArrowRight} onClick={onAgain}>Keep going ({left} left)</Button>}
            </div>
        </Card>
    );
}

function StudySession({ cards, counts, onExit, onRestart, onReviewed, onFinish }) {
    const toast = useToast();
    const [queue, setQueue] = useState(cards);
    const [pos, setPos] = useState(0);
    const [flipped, setFlipped] = useState(false);
    const [tally, setTally] = useState({ again: 0, hard: 0, good: 0, easy: 0 });
    const [flash, setFlash] = useState(null);
    const [startedAt] = useState(() => Date.now());
    const requeued = useRef({});
    const flashTimer = useRef(null);
    useEffect(() => () => clearTimeout(flashTimer.current), []);

    const card = queue[pos];
    const done = pos >= queue.length;
    useEffect(() => { if (done) onFinish?.(); }, [done, onFinish]);

    const grade = useCallback((g) => {
        if (!card || !flipped) return;
        const id = card.id;
        api(`/cards/${id}/review`, { method: 'POST', body: { grade: g } })
            .then((res) => {
                setQueue((q) => q.map((c) => (c.id === id ? res.data : c)));
                onReviewed?.();
            })
            .catch((e) => toast(e.message, 'error'));
        setTally((t) => ({ ...t, [g]: t[g] + 1 }));
        const back = g === 'again' && (requeued.current[id] || 0) < MAX_REQUEUE;
        if (back) {
            requeued.current[id] = (requeued.current[id] || 0) + 1;
            setQueue((q) => [...q, card]);
        }
        const label = GRADES.find((x) => x.grade === g).label;
        setFlash(back ? `${label}: back later this session` : `${label}: next in ${fmtInterval(card.preview?.[g])}`);
        clearTimeout(flashTimer.current);
        flashTimer.current = setTimeout(() => setFlash(null), 1800);
        setFlipped(false);
        setPos((p) => p + 1);
    }, [card, flipped, onReviewed, toast]);

    useEffect(() => {
        if (done) return undefined;
        const onKey = (e) => {
            if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target) || document.querySelector('[role="dialog"]')) return;
            if (e.key === ' ' || (e.key === 'Enter' && !flipped)) {
                e.preventDefault();
                setFlipped((f) => !f);
            } else if (flipped) {
                const g = GRADES.find((x) => x.key === e.key);
                if (g) { e.preventDefault(); grade(g.grade); }
            }
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [done, flipped, grade]);

    if (done) return <FinishScreen tally={tally} startedAt={startedAt} counts={counts} onAgain={onRestart} onExit={onExit} />;

    const progress = (100 * pos) / queue.length;
    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3">
                <button type="button" onClick={onExit} className="btn btn-ghost btn-sm -ml-2">End</button>
                <ProgressBar value={progress} className="flex-1" />
                <span className="text-xs text-muted tabular-nums shrink-0">{pos + 1} / {queue.length}</span>
            </div>
            <div className="h-5 text-center">
                {flash && <span key={flash + pos} className="text-xs font-medium text-muted animate-fade">{flash}</span>}
            </div>

            <Flashcard key={`${card.id}-${pos}`} card={card} flipped={flipped} onFlip={() => setFlipped((f) => !f)} />

            {!flipped ? (
                <Button variant="primary" size="lg" className="w-full" icon={Eye} onClick={() => setFlipped(true)}>
                    Show answer
                </Button>
            ) : (
                <div className="grid grid-cols-4 gap-2 animate-rise">
                    {GRADES.map((g) => (
                        <button
                            key={g.grade}
                            type="button"
                            onClick={() => grade(g.grade)}
                            className={cx(
                                'btn h-auto flex-col gap-0.5 py-2.5 px-1 border',
                                g.grade === 'good' ? 'bg-accent text-accent-fg border-accent hover:bg-accent-hover' : 'bg-surface border-line hover:bg-surface-2 hover:border-line-strong',
                            )}
                        >
                            <span className={cx('text-sm font-semibold', g.grade !== 'good' && g.tone)}>{g.label}</span>
                            <span className={cx('text-[11px] tabular-nums', g.grade === 'good' ? 'text-accent-fg/80' : 'text-subtle')}>
                                {fmtInterval(card.preview?.[g.grade])}
                            </span>
                        </button>
                    ))}
                </div>
            )}
            <p className="hidden sm:block text-center text-xs text-subtle">
                <kbd className="font-mono">Space</kbd> flip · <kbd className="font-mono">1</kbd>–<kbd className="font-mono">4</kbd> grade
            </p>
        </div>
    );
}

// ---------------- Sheets ----------------
function CardFormSheet({ open, onClose, initial, defaultSubject, onSaved }) {
    const toast = useToast();
    const blank = { subject: defaultSubject || 'OS', question: '', answer: '', tags: '', difficulty: 2 };
    const [form, setForm] = useState(blank);
    const [saving, setSaving] = useState(false);
    const [lastOpen, setLastOpen] = useState(false);
    if (open !== lastOpen) {
        setLastOpen(open);
        if (open) setForm(initial ? { ...initial, tags: (initial.tags || []).join(', ') } : blank);
    }
    const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

    const save = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const body = { subject: form.subject, question: form.question, answer: form.answer, tags: form.tags, difficulty: Number(form.difficulty) };
            const res = initial
                ? await api(`/cards/${initial.id}`, { method: 'PUT', body })
                : await api('/cards', { method: 'POST', body });
            toast(initial ? 'Card updated' : 'Card added');
            onSaved(res.data);
            onClose();
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setSaving(false);
        }
    };

    return (
        <Sheet open={open} onClose={onClose}>
            <form onSubmit={save} className="p-5 sm:p-6 space-y-4">
                <div>
                    <h2 className="text-lg font-semibold tracking-tight">{initial ? 'Edit card' : 'Add a card'}</h2>
                    <p className="text-sm text-muted">One concept per card. Answer like you would in the interview.</p>
                </div>
                <div>
                    <label className="label" htmlFor="card-subject">Subject</label>
                    <select id="card-subject" className="input" value={form.subject} onChange={set('subject')}>
                        {[...new Set([...SUBJECTS, form.subject])].map((s) => <option key={s} value={s}>{SUBJECT_NAMES[s] || s}</option>)}
                    </select>
                </div>
                <div>
                    <label className="label" htmlFor="card-q">Question</label>
                    <textarea id="card-q" className="input h-auto py-2.5 min-h-[72px] resize-y" value={form.question} onChange={set('question')}
                        placeholder="e.g. What is a TLB shootdown?" maxLength={500} required />
                </div>
                <div>
                    <label className="label" htmlFor="card-a">Answer</label>
                    <textarea id="card-a" className="input h-auto py-2.5 min-h-[140px] resize-y" value={form.answer} onChange={set('answer')}
                        placeholder={'Short definition.\n- Start lines with "- " for bullets'} maxLength={4000} required />
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                        <label className="label" htmlFor="card-tags">Tags</label>
                        <input id="card-tags" className="input" value={form.tags} onChange={set('tags')} placeholder="memory, tlb" />
                    </div>
                    <div>
                        <span className="label">Difficulty</span>
                        <Segmented
                            className="w-full [&>button]:flex-1"
                            options={[{ value: 1, label: 'Easy' }, { value: 2, label: 'Medium' }, { value: 3, label: 'Hard' }]}
                            value={Number(form.difficulty)}
                            onChange={(v) => setForm((f) => ({ ...f, difficulty: v }))}
                        />
                    </div>
                </div>
                <div className="flex gap-2 pt-1 safe-bottom">
                    <Button type="button" onClick={onClose} className="flex-1 sm:flex-none">Cancel</Button>
                    <Button type="submit" variant="primary" loading={saving} className="flex-1" icon={initial ? Pencil : Plus}>
                        {initial ? 'Save changes' : 'Add card'}
                    </Button>
                </div>
            </form>
        </Sheet>
    );
}

function GenerateSheet({ open, onClose, defaultSubject, onDone }) {
    const toast = useToast();
    const [subject, setSubject] = useState(defaultSubject || 'OS');
    const [topic, setTopic] = useState('');
    const [count, setCount] = useState(5);
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const [lastOpen, setLastOpen] = useState(false);
    if (open !== lastOpen) {
        setLastOpen(open);
        if (open) { setResult(null); if (defaultSubject) setSubject(defaultSubject); }
    }

    const run = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const res = await api('/cards/generate', { method: 'POST', body: { subject, topic, count } });
            setResult(res);
            const n = res.data.length;
            toast(n ? `Added ${n} card${n === 1 ? '' : 's'}${res.skipped ? ` · ${res.skipped} duplicate${res.skipped === 1 ? '' : 's'} skipped` : ''}` : 'Nothing new. Try a narrower topic.', n ? 'success' : 'info');
            if (n) onDone();
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setBusy(false);
        }
    };

    return (
        <Sheet open={open} onClose={onClose}>
            <form onSubmit={run} className="p-5 sm:p-6 space-y-4">
                <div className="flex items-start gap-3">
                    <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0"><Sparkles className="h-5 w-5" /></div>
                    <div>
                        <h2 className="text-lg font-semibold tracking-tight">Generate with AI</h2>
                        <p className="text-sm text-muted">Fresh interview cards on any topic. Duplicates of your deck are skipped.</p>
                    </div>
                </div>
                <div>
                    <span className="label">Subject</span>
                    <div className="flex flex-wrap gap-2">
                        {SUBJECTS.map((s) => (
                            <button key={s} type="button" onClick={() => setSubject(s)} className={cx('chip h-8 px-3', subject === s && 'chip-on')}>{s}</button>
                        ))}
                    </div>
                </div>
                <div>
                    <label className="label" htmlFor="gen-topic">Topic</label>
                    <input id="gen-topic" className="input" value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={200}
                        placeholder={{ OS: 'e.g. virtual memory, semaphores', DBMS: 'e.g. indexing, isolation levels', CN: 'e.g. TCP congestion control', OOP: 'e.g. SOLID, design patterns', SQL: 'e.g. window functions' }[subject] || 'e.g. a topic'} />
                </div>
                <div>
                    <span className="label">How many</span>
                    <Segmented options={[{ value: 3, label: '3' }, { value: 5, label: '5' }, { value: 10, label: '10' }]} value={count} onChange={setCount} />
                </div>
                <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy} icon={Sparkles}>
                    {busy ? 'Writing cards…' : `Generate ${count} cards`}
                </Button>
                {result?.data?.length > 0 && (
                    <div className="space-y-2 animate-rise">
                        <p className="eyebrow">Added to your deck</p>
                        <ul className="rounded-xl border border-line divide-y divide-line overflow-hidden">
                            {result.data.map((c) => (
                                <li key={c.id} className="px-3 py-2.5 text-sm">{c.question}</li>
                            ))}
                        </ul>
                        <p className="text-xs text-subtle">New cards join your daily queue automatically.</p>
                    </div>
                )}
                <div className="safe-bottom" />
            </form>
        </Sheet>
    );
}

// ---------------- Browse ----------------
function BrowseRow({ card, now, onEdit, onChanged }) {
    const toast = useToast();
    const [open, setOpen] = useState(false);
    const [confirm, setConfirm] = useState(false);
    const [busy, setBusy] = useState(false);

    const act = async (fn, msg) => {
        setBusy(true);
        try { await fn(); toast(msg); onChanged(); } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); setConfirm(false); }
    };
    const due = card.due_at ? new Date(card.due_at) : null;
    const dueIn = due ? (due - now) / 86400000 : null;

    return (
        <li>
            <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
                className="w-full text-left flex items-start gap-3 px-3 sm:px-4 py-3 row-hover">
                <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-snug">{card.question}</p>
                    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        <span className="badge text-muted bg-surface-2">{card.subject}</span>
                        <span className={cx('badge capitalize', STATE_TONE[card.state])}>{card.state}</span>
                        {card.source === 'ai' && <span className="badge text-accent bg-accent-soft"><Sparkles className="h-3 w-3" />AI</span>}
                        {card.source === 'user' && <span className="badge text-muted bg-surface-2">Mine</span>}
                        {dueIn != null && (
                            <span className="text-[11px] text-subtle tabular-nums">{dueIn <= 0 ? 'due now' : `due in ${fmtInterval(dueIn)}`}</span>
                        )}
                    </div>
                </div>
                <ChevronDown className={cx('h-4 w-4 text-subtle mt-0.5 shrink-0 transition-transform', open && 'rotate-180')} />
            </button>
            {open && (
                <div className="px-3 sm:px-4 pb-4 animate-fade">
                    <AnswerText text={card.answer} className="rounded-xl bg-surface-2/60 border border-line p-3 sm:p-4" />
                    <div className="flex flex-wrap items-center gap-1.5 mt-3">
                        {card.stability != null && (
                            <span className="text-xs text-subtle mr-auto">
                                Memory {fmtInterval(card.stability)} · {card.reps} review{card.reps === 1 ? '' : 's'}{card.lapses ? ` · ${card.lapses} lapses` : ''}
                            </span>
                        )}
                        <Button size="sm" variant="ghost" icon={Pencil} onClick={() => onEdit(card)}>Edit</Button>
                        {card.reps > 0 && (
                            <Button size="sm" variant="ghost" icon={RotateCcw} disabled={busy}
                                onClick={() => act(() => api(`/cards/${card.id}`, { method: 'PUT', body: { reset: true } }), 'Progress reset')}>
                                Reset
                            </Button>
                        )}
                        <Button size="sm" variant="danger" icon={Trash2} disabled={busy}
                            onClick={() => (confirm ? act(() => api(`/cards/${card.id}`, { method: 'DELETE' }), 'Card deleted') : setConfirm(true))}>
                            {confirm ? 'Confirm delete' : 'Delete'}
                        </Button>
                    </div>
                </div>
            )}
        </li>
    );
}

const PAGE = 40;

function Browse({ subject, onEdit, refreshKey, onChanged }) {
    const { data, loading, error, reload } = useApi('/cards', { select: (d) => d.data, deps: [refreshKey] });
    const [query, setQuery] = useState('');
    const [state, setState] = useState('all');
    const [limit, setLimit] = useState(PAGE);
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => { const t = setInterval(() => setNow(Date.now()), 60000); return () => clearInterval(t); }, []);

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        return (data || []).filter((c) => {
            if (subject && c.subject !== subject) return false;
            if (state === 'due' && !(c.reps > 0 && new Date(c.due_at).getTime() <= now)) return false;
            if (state !== 'all' && state !== 'due' && c.state !== state) return false;
            if (!q) return true;
            return `${c.question} ${c.answer} ${(c.tags || []).join(' ')}`.toLowerCase().includes(q);
        });
    }, [data, subject, state, query, now]);

    return (
        <div className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-2">
                <div className="relative flex-1">
                    <Search className="h-4 w-4 text-subtle absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                    <input className="input pl-9" type="search" placeholder="Search questions, answers, tags" value={query}
                        onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }} aria-label="Search cards" />
                </div>
                <Segmented
                    className="self-start overflow-x-auto max-w-full no-scrollbar"
                    options={[{ value: 'all', label: 'All' }, { value: 'due', label: 'Due' }, { value: 'new', label: 'New' }, { value: 'mastered', label: 'Mastered' }]}
                    value={state}
                    onChange={(v) => { setState(v); setLimit(PAGE); }}
                />
            </div>
            <Card className="overflow-hidden">
                {loading && !data ? (
                    <div className="p-4 space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
                ) : error ? (
                    <Empty icon={Layers} title="Couldn't load cards" action={<Button size="sm" onClick={() => reload()}>Retry</Button>}>{error}</Empty>
                ) : filtered.length === 0 ? (
                    <Empty icon={Search} title="No cards match">Try another search or subject.</Empty>
                ) : (
                    <>
                        <div className="px-3 sm:px-4 py-2 border-b border-line text-xs text-subtle tabular-nums">{filtered.length} card{filtered.length === 1 ? '' : 's'}</div>
                        <ul className="divide-y divide-line">
                            {filtered.slice(0, limit).map((c) => (
                                <BrowseRow key={c.id} card={c} now={now} onEdit={onEdit} onChanged={onChanged} />
                            ))}
                        </ul>
                        {filtered.length > limit && (
                            <div className="p-3 border-t border-line">
                                <Button size="sm" variant="ghost" className="w-full" onClick={() => setLimit((l) => l + PAGE)}>
                                    Show {Math.min(PAGE, filtered.length - limit)} more
                                </Button>
                            </div>
                        )}
                    </>
                )}
            </Card>
        </div>
    );
}

// ---------------- Page ----------------
export default function Cards() {
    const [tab, setTab] = useLocalStorage('cards:tab', 'study');
    const [subject, setSubject] = useLocalStorage('cards:subject', '');
    const path = `/cards/today?limit=20${subject ? `&subject=${encodeURIComponent(subject)}` : ''}`;
    const { data, loading, error, reload } = useApi(path, { select: (d) => d });
    const [session, setSession] = useState(null); // { cards, id }
    const [form, setForm] = useState({ open: false, card: null });
    const [genOpen, setGenOpen] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    const counts = data?.counts;
    const subjects = data?.subjects || [];
    const queue = data?.data || [];

    const refreshAll = useCallback(() => {
        invalidate('/cards');
        reload({ silent: true });
        setRefreshKey((k) => k + 1);
    }, [reload]);

    const start = (cards) => { if (cards.length) setSession({ cards, id: Date.now() }); };
    const restart = async () => {
        invalidate('/cards');
        try {
            const res = await api(path);
            if (res.data.length) setSession({ cards: res.data, id: Date.now() });
            else setSession(null);
        } catch { setSession(null); }
        reload({ silent: true });
    };
    const exitSession = () => { setSession(null); refreshAll(); };
    const onReviewed = useCallback(() => invalidate('/cards'), []);
    const onFinish = useCallback(() => reload({ silent: true }), [reload]);

    const left = (counts?.due || 0) + (counts?.new || 0);
    const activeSubject = subjects.find((s) => s.subject === subject);

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 animate-rise">
                <div className="min-w-0">
                    <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Cards</h1>
                    <p className="text-sm text-muted mt-1">CS fundamentals on spaced repetition. A few minutes a day, never forgotten.</p>
                </div>
                {!session && (
                    <div className="flex gap-2 shrink-0">
                        <Button icon={Sparkles} onClick={() => setGenOpen(true)} className="flex-1 sm:flex-none">Generate</Button>
                        <Button icon={Plus} onClick={() => setForm({ open: true, card: null })} className="flex-1 sm:flex-none">Add card</Button>
                    </div>
                )}
            </header>

            {session ? (
                <div className="max-w-2xl mx-auto">
                    <StudySession key={session.id} cards={session.cards} counts={counts} onExit={exitSession} onRestart={restart}
                        onReviewed={onReviewed} onFinish={onFinish} />
                </div>
            ) : (
                <>
                    <div className="flex flex-col gap-3">
                        <Segmented options={[{ value: 'study', label: 'Study' }, { value: 'browse', label: 'Browse' }]} value={tab} onChange={setTab} className="self-start" />
                        {subjects.length > 0 && <SubjectChips subjects={subjects} value={subject} onChange={setSubject} />}
                    </div>

                    {tab === 'browse' ? (
                        <Browse subject={subject} refreshKey={refreshKey} onEdit={(card) => setForm({ open: true, card })} onChanged={refreshAll} />
                    ) : loading && !data ? (
                        <Card className="card-pad space-y-4">
                            <Skeleton className="h-6 w-40" />
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}</div>
                            <Skeleton className="h-11" />
                        </Card>
                    ) : error && !data ? (
                        <Card><Empty icon={Layers} title="Couldn't load your cards" action={<Button size="sm" onClick={() => reload()}>Retry</Button>}>{error}</Empty></Card>
                    ) : (
                        <div className="grid lg:grid-cols-[1fr_320px] gap-4 sm:gap-5 items-start">
                            <Card className="card-pad hero-accent animate-rise">
                                <p className="eyebrow">{activeSubject ? SUBJECT_NAMES[activeSubject.subject] || activeSubject.subject : 'Today'}</p>
                                <h2 className="text-xl sm:text-2xl font-bold tracking-tight mt-1">
                                    {left ? `${left} card${left === 1 ? '' : 's'} ready` : 'All caught up'}
                                </h2>
                                <p className="text-sm text-muted mt-1">
                                    {left
                                        ? `${counts.due} due for review · ${counts.new} new today${queue.length < left ? ` · ${queue.length} per session` : ''}`
                                        : 'Nothing due right now. Come back later, or add fresh cards.'}
                                </p>
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4">
                                    <Stat label="Due" value={counts?.due ?? 0} icon={RotateCcw} tone="text-danger" />
                                    <Stat label="New" value={counts?.new ?? 0} icon={Plus} tone="text-accent" />
                                    <Stat label="Done today" value={counts?.done_today ?? 0} icon={Brain} tone="text-ok" />
                                    <Stat label="Streak" value={`${counts?.streak ?? 0}d`} icon={Flame} tone="text-accent" />
                                </div>
                                {queue.length > 0 ? (
                                    <Button variant="primary" size="lg" className="w-full mt-4" icon={ArrowRight} onClick={() => start(queue)}>
                                        Start review
                                    </Button>
                                ) : (
                                    <div className="flex gap-2 mt-4">
                                        <Button className="flex-1" icon={Search} onClick={() => setTab('browse')}>Browse deck</Button>
                                        <Button className="flex-1" icon={Sparkles} onClick={() => setGenOpen(true)}>Generate</Button>
                                    </div>
                                )}
                                <p className="hidden sm:block text-xs text-subtle mt-3 text-center">
                                    <kbd className="font-mono">Space</kbd> flip · <kbd className="font-mono">1</kbd>–<kbd className="font-mono">4</kbd> Again / Hard / Good / Easy
                                </p>
                            </Card>

                            <Card className="card-pad animate-rise">
                                <p className="eyebrow mb-3">Mastery by subject</p>
                                <ul className="space-y-3">
                                    {subjects.map((s) => (
                                        <li key={s.subject}>
                                            <button type="button" onClick={() => setSubject(subject === s.subject ? '' : s.subject)}
                                                className={cx('w-full text-left rounded-lg -mx-1.5 px-1.5 py-1 transition-colors hover:bg-surface-2', subject === s.subject && 'bg-surface-2')}>
                                                <div className="flex items-baseline justify-between gap-2 text-[13px]">
                                                    <span className="font-medium truncate">{SUBJECT_NAMES[s.subject] || s.subject}</span>
                                                    <span className="text-subtle tabular-nums shrink-0">
                                                        {s.due > 0 && <span className="text-danger mr-1.5">{s.due} due</span>}
                                                        {s.mastered}/{s.total}
                                                    </span>
                                                </div>
                                                <ProgressBar value={s.mastery} className="mt-1.5" color={s.mastery >= 80 ? 'var(--ok)' : 'var(--accent)'} />
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                                <p className="text-xs text-subtle mt-4">Mastered = memory holds for 3+ weeks.</p>
                            </Card>
                        </div>
                    )}
                </>
            )}

            <CardFormSheet open={form.open} initial={form.card} defaultSubject={subject} onClose={() => setForm({ open: false, card: null })} onSaved={refreshAll} />
            <GenerateSheet open={genOpen} defaultSubject={subject} onClose={() => setGenOpen(false)} onDone={refreshAll} />
        </div>
    );
}
