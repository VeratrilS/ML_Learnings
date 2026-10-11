import { useEffect, useRef, useState } from 'react';
import { BookOpen, Check, CloudOff, CodeXml, Coffee, GraduationCap, ListPlus, ListTodo, RefreshCw, RotateCcw, Sparkles, TriangleAlert, Tv } from 'lucide-react';
import { api } from '../lib/api';
import { invalidate, useApi } from '../lib/hooks';
import { Button, Card, Empty, Skeleton, Spinner, cx, useToast } from './ui';

const KIND = {
    exam: { label: 'Exam', dot: 'bg-hard', text: 'text-hard', icon: GraduationCap },
    dsa: { label: 'DSA', dot: 'bg-accent', text: 'text-accent', icon: CodeXml },
    review: { label: 'Review', dot: 'bg-medium', text: 'text-medium', icon: RotateCcw },
    video: { label: 'Lesson', dot: 'bg-easy', text: 'text-easy', icon: BookOpen },
    plan: { label: 'Plan', dot: 'bg-muted', text: 'text-muted', icon: ListTodo },
    rest: { label: 'Rest', dot: 'bg-surface border-2 border-line-strong', text: 'text-subtle', icon: Coffee },
    episode: { label: 'Reward', dot: 'bg-ok', text: 'text-ok', icon: Tv },
};

const toMin = (s) => {
    const [h, m] = String(s || '').split(':').map(Number);
    return h * 60 + m;
};
const nowMin = () => {
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
};
const localIso = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const fmtDur = (m) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ''}` : `${m}m`);
const buzz = () => { try { navigator.vibrate?.(8); } catch { /* unsupported */ } };

function useMinute() {
    const [m, setM] = useState(nowMin);
    useEffect(() => {
        const id = setInterval(() => setM(nowMin()), 30000);
        return () => clearInterval(id);
    }, []);
    return m;
}

function TimelineSkeleton() {
    return (
        <ol className="mt-5" aria-hidden>
            {[0, 1, 2, 3, 4].map((i) => (
                <li key={i} className="flex gap-2.5 sm:gap-3">
                    <Skeleton className="mt-3 h-3 w-11 shrink-0" />
                    <div className="flex w-3 shrink-0 flex-col items-center">
                        <span className={cx('h-3 w-px', i ? 'bg-line' : '')} />
                        <span className="my-0.75 h-2.5 w-2.5 rounded-full bg-surface-3" />
                        {i < 4 && <span className="w-px flex-1 bg-line" />}
                    </div>
                    <Skeleton className="mb-1.5 h-15 flex-1 rounded-xl" />
                </li>
            ))}
        </ol>
    );
}

export default function BriefCard() {
    const { data, error, loading, reload, setData } = useApi('/brief', { select: (d) => ({ brief: d.data, pending: !!d.pending }) });
    const toast = useToast();
    const minute = useMinute();
    const [generating, setGenerating] = useState(null); // 'auto' | 'force' | null
    const [genError, setGenError] = useState(null);
    const [selected, setSelected] = useState(() => new Set());
    const [accepting, setAccepting] = useState(false);
    const autoTried = useRef(false);
    const alive = useRef(true);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

    const generate = async (force) => {
        if (generating) return;
        setGenerating(force ? 'force' : 'auto');
        setGenError(null);
        try {
            const res = await api(`/brief${force ? '?force=1' : ''}`, { method: 'POST' });
            if (!alive.current) return;
            setData({ brief: res.data, pending: false });
            setSelected(new Set());
            if (force) {
                if (res.data?.ai) toast('Fresh plan ready.');
                else toast('Coach is offline. Built a plan from your numbers.', 'info');
            }
        } catch (e) {
            if (!alive.current) return;
            setGenError(e.message);
            if (force) toast(e.message, 'error');
        } finally {
            if (alive.current) setGenerating(null);
        }
    };

    // No brief yet today: ask for one, once.
    useEffect(() => {
        if (data?.pending && !autoTried.current) {
            autoTried.current = true;
            generate(false);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data?.pending]);

    const brief = data?.brief;
    const isToday = !!brief && brief.day === localIso();
    const blocks = brief?.blocks || [];
    const accepted = new Set(brief?.accepted || []);
    const remaining = blocks.filter((b, i) => b.kind !== 'rest' && !accepted.has(i)).length;

    let current = -1;
    let next = -1;
    if (isToday) {
        current = blocks.findIndex((b) => toMin(b.start) <= minute && minute < toMin(b.start) + b.minutes);
        if (current < 0) next = blocks.findIndex((b) => toMin(b.start) > minute);
    }

    const toggle = (i) => {
        buzz();
        setSelected((prev) => {
            const n = new Set(prev);
            if (n.has(i)) n.delete(i);
            else n.add(i);
            return n;
        });
    };

    const accept = async () => {
        const indices = selected.size ? [...selected].sort((a, b) => a - b) : null;
        setAccepting(true);
        try {
            const res = await api('/brief/accept', { method: 'POST', body: indices ? { indices } : {} });
            if (!alive.current) return;
            setData((d) => (d?.brief ? { ...d, brief: { ...d.brief, accepted: res.accepted || [] } } : d));
            setSelected(new Set());
            const n = res.data?.length || 0;
            if (n) {
                toast(`Added ${n} block${n === 1 ? '' : 's'} to your plan.`);
                invalidate('/todos');
                window.dispatchEvent(new CustomEvent('todos-changed'));
            } else {
                toast('Already in your plan.', 'info');
            }
            if (res.failed) toast(`${res.failed} block${res.failed === 1 ? '' : 's'} couldn't be added.`, 'error');
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            if (alive.current) setAccepting(false);
        }
    };

    // ---- states without a brief ----
    if (!brief && error && !loading) {
        return (
            <Card className="card-pad">
                <Empty icon={Sparkles} title="Couldn't load today's brief" action={<Button size="sm" icon={RefreshCw} onClick={() => reload()}>Retry</Button>}>
                    {error}
                </Empty>
            </Card>
        );
    }

    const planning = generating === 'auto' || (!!data?.pending && !genError);
    if (!brief || (!isToday && loading)) {
        const failed = !brief && !!genError && !generating;
        return (
            <Card className="card-pad hero-accent" aria-busy={!failed}>
                <div className="flex items-center justify-between gap-3">
                    <span className="eyebrow">Today's brief</span>
                </div>
                {failed ? (
                    <Empty icon={Sparkles} title="Coach couldn't plan your day" action={<Button size="sm" variant="primary" icon={RefreshCw} onClick={() => generate(false)}>Try again</Button>}>
                        {genError}
                    </Empty>
                ) : (
                    <>
                        {(planning || data?.pending) && (
                            <p className="mt-3 flex items-center gap-2 text-sm font-medium text-fg animate-fade">
                                <Spinner className="h-4 w-4 text-accent" />
                                Coach is planning your day…
                            </p>
                        )}
                        <Skeleton className="mt-3 h-6 w-4/5" />
                        <Skeleton className="mt-3 h-3.5 w-full" />
                        <Skeleton className="mt-2 h-3.5 w-2/3" />
                        <TimelineSkeleton />
                        {(planning || data?.pending) && <p className="mt-2 text-xs text-subtle">Thinking… up to a minute.</p>}
                    </>
                )}
            </Card>
        );
    }

    const busy = generating === 'force';
    return (
        <Card className="card-pad hero-accent" aria-busy={busy}>
            {/* header */}
            <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                    <span className="eyebrow">Today's brief</span>
                    {brief.ai ? (
                        <span className="badge bg-accent-soft text-accent"><Sparkles className="h-3 w-3" aria-hidden />AI</span>
                    ) : (
                        <span className="badge bg-surface-2 text-muted"><CloudOff className="h-3 w-3" aria-hidden />Offline plan</span>
                    )}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                    {brief.generated_at && <span className="hidden font-mono text-[11px] text-subtle sm:inline">at {brief.generated_at}</span>}
                    <Button variant="ghost" size="sm" icon={RefreshCw} loading={busy} disabled={!!generating} onClick={() => generate(true)} aria-label="Regenerate brief" title="Regenerate">
                        <span className="hidden sm:inline">Regenerate</span>
                    </Button>
                </div>
            </div>
            {busy && (
                <p className="mt-2 flex items-center gap-2 text-xs font-medium text-accent animate-fade" role="status">
                    <Spinner className="h-3.5 w-3.5" /> Thinking… up to a minute
                </p>
            )}

            <div className={cx('transition-opacity', busy && 'pointer-events-none opacity-50')}>
                <h2 className="mt-2.5 text-lg font-semibold leading-snug tracking-tight text-balance sm:text-xl">{brief.headline}</h2>
                {brief.summary && <p className="mt-1.5 text-sm leading-relaxed text-muted">{brief.summary}</p>}

                {/* timeline */}
                <ol className="mt-4">
                    {blocks.map((b, i) => {
                        const k = KIND[b.kind] || KIND.plan;
                        const Icon = k.icon;
                        const start = toMin(b.start);
                        const isNow = i === current;
                        const isNext = i === next;
                        const past = isToday && !isNow && start + b.minutes <= minute;
                        const done = accepted.has(i);
                        const sel = selected.has(i);
                        const last = i === blocks.length - 1;
                        return (
                            <li key={`${b.start}-${i}`} className="flex gap-2.5 sm:gap-3">
                                <time className={cx('w-11 shrink-0 pt-3 text-right font-mono text-[12px] leading-4 tabular-nums', isNow || isNext ? 'font-semibold text-fg' : 'text-subtle')}>
                                    {b.start}
                                </time>
                                <div className="flex w-3 shrink-0 flex-col items-center" aria-hidden>
                                    <span className={cx('h-3 w-px', i ? 'bg-line' : '')} />
                                    <span className={cx('my-0.75 h-2.5 w-2.5 shrink-0 rounded-full', k.dot, isNow && 'animate-glow', past && 'opacity-50')} />
                                    {!last && <span className="w-px flex-1 bg-line" />}
                                </div>
                                <button
                                    type="button"
                                    onClick={() => !done && toggle(i)}
                                    aria-pressed={done ? undefined : sel}
                                    aria-disabled={done || undefined}
                                    className={cx(
                                        'group mb-1.5 flex min-w-0 flex-1 items-start gap-2.5 rounded-xl border px-3 py-2 text-left transition-colors',
                                        'focus-visible:outline-2 focus-visible:outline-accent',
                                        sel ? 'border-accent/60 bg-accent-soft'
                                            : isNow ? 'border-accent/30 bg-accent-soft'
                                                : isNext ? 'border-line bg-surface-2'
                                                    : 'border-transparent hover:bg-surface-2',
                                        past && !sel && 'opacity-60',
                                        done && 'cursor-default',
                                    )}
                                >
                                    <span className="block min-w-0 flex-1">
                                        <span className="block pt-px text-sm font-medium leading-5 text-fg">{b.title}</span>
                                        {b.why && <span className="mt-0.5 block text-xs leading-snug text-subtle">{b.why}</span>}
                                        <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
                                            <span className={cx('inline-flex items-center gap-1 font-semibold', k.text)}>
                                                <Icon className="h-3 w-3" aria-hidden />{k.label}
                                            </span>
                                            <span className="font-mono text-subtle">{fmtDur(b.minutes)}</span>
                                            {isNow && <span className="badge bg-accent text-accent-fg">Now</span>}
                                            {isNext && <span className="badge bg-accent-soft text-accent">Next</span>}
                                            {done && <span className="font-medium text-ok">In plan</span>}
                                        </span>
                                    </span>
                                    <span
                                        aria-hidden
                                        className={cx(
                                            'mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border transition-all',
                                            done ? 'border-ok bg-ok text-surface'
                                                : sel ? 'border-accent bg-accent text-accent-fg'
                                                    : 'border-line-strong text-transparent opacity-60 group-hover:opacity-100',
                                        )}
                                    >
                                        <Check className="h-3.5 w-3.5" strokeWidth={3} />
                                    </span>
                                </button>
                            </li>
                        );
                    })}
                </ol>

                {brief.risk && (
                    <div role="note" className="mt-3 flex gap-2.5 rounded-xl border border-danger/25 bg-danger/10 px-3 py-2.5">
                        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />
                        <p className="text-[13px] leading-snug text-fg">
                            <span className="font-semibold text-danger">At risk: </span>{brief.risk}
                        </p>
                    </div>
                )}

                {brief.nudge && <p className="mt-4 border-l-2 border-accent/60 pl-3 text-sm italic leading-relaxed text-muted">{brief.nudge}</p>}

                {/* actions */}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                    {selected.size > 0 ? (
                        <>
                            <Button variant="primary" icon={ListPlus} loading={accepting} onClick={accept} className="flex-1 sm:flex-none">
                                Add {selected.size} to plan
                            </Button>
                            <Button variant="ghost" onClick={() => setSelected(new Set())} disabled={accepting}>Clear</Button>
                        </>
                    ) : remaining > 0 ? (
                        <Button variant="primary" icon={ListPlus} loading={accepting} onClick={accept} className="flex-1 sm:flex-none">
                            Add {remaining === blocks.filter((b) => b.kind !== 'rest').length ? 'all' : `${remaining} more`} to plan
                        </Button>
                    ) : (
                        <Button variant="secondary" icon={Check} disabled className="flex-1 sm:flex-none">In your plan</Button>
                    )}
                    {remaining > 0 && selected.size === 0 && (
                        <span className="w-full text-center text-[11px] text-subtle sm:w-auto sm:text-left">or tap blocks to pick a few</span>
                    )}
                </div>
            </div>
        </Card>
    );
}
