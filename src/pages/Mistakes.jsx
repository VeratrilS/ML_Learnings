import { useMemo, useRef, useState } from 'react';
import {
    ArrowDownRight, ArrowUpRight, BarChart3, Check, ClipboardCheck, Copy, ExternalLink, Lightbulb,
    NotebookPen, PenLine, Trash2,
} from 'lucide-react';
import { api } from '../lib/api';
import { invalidate, timeAgo, useApi } from '../lib/hooks';
import { Button, Card, CardHeader, Checkbox, Empty, Segmented, Skeleton, cx, useToast } from '../components/ui';
import MistakeQuickAdd, { CategoryBadge } from '../components/MistakeQuickAdd';

const selectAll = (d) => ({ items: d.data || [], stats: d.stats || null, categories: d.categories || [] });

// ---------------- stats strip ----------------
function Delta({ now, prev }) {
    if (!now && !prev) return <span className="text-xs text-subtle">no data</span>;
    const diff = now - prev;
    if (diff === 0) return <span className="text-xs text-subtle">same as last week</span>;
    const Icon = diff < 0 ? ArrowDownRight : ArrowUpRight;
    return (
        <span className={cx('inline-flex items-center gap-0.5 text-xs font-medium', diff < 0 ? 'text-ok' : 'text-danger')}>
            <Icon className="h-3.5 w-3.5" aria-hidden />
            {Math.abs(diff)} vs last week
        </span>
    );
}

function Stat({ label, value, children }) {
    const text = typeof value === 'string';
    return (
        <div className="card p-3.5 sm:p-4 min-w-0">
            <p className="eyebrow">{label}</p>
            <p className={cx('font-bold tracking-tight tabular-nums mt-1 truncate', text ? 'text-base sm:text-lg leading-8 capitalize' : 'text-2xl')}>{value}</p>
            <div className="mt-0.5 min-h-4 truncate">{children}</div>
        </div>
    );
}

function StatsStrip({ stats }) {
    const top = stats.top_categories?.[0];
    const pattern = stats.top_patterns?.[0];
    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="This week" value={stats.this_week}>
                <Delta now={stats.this_week} prev={stats.last_week} />
            </Stat>
            <Stat label="Open" value={stats.open}>
                <span className="text-xs text-subtle">{stats.resolved} resolved · {stats.total} total</span>
            </Stat>
            <Stat label="Top trap" value={top ? top.label : '—'}>
                <span className="text-xs text-subtle">{top ? `${top.count}× in the last 30 days` : 'Nothing logged yet'}</span>
            </Stat>
            <Stat label="Weak pattern" value={pattern ? pattern.pattern : '—'}>
                <span className="text-xs text-subtle">{pattern ? `${pattern.count} mistake${pattern.count === 1 ? '' : 's'}` : 'Tagged automatically'}</span>
            </Stat>
        </div>
    );
}

// ---------------- category bars ----------------
function CategoryBars({ stats }) {
    const rows = (stats.per_category || []).filter((r) => r.this_week || r.last_week);
    const max = Math.max(1, ...rows.flatMap((r) => [r.this_week, r.last_week]));
    return (
        <Card className="card-pad">
            <CardHeader
                title="By category"
                subtitle="This week vs the week before"
                icon={BarChart3}
                action={(
                    <div className="flex items-center gap-3 text-[11px] text-subtle">
                        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-accent" />This</span>
                        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-line-strong" />Last</span>
                    </div>
                )}
            />
            {rows.length === 0 ? (
                <p className="text-[13px] text-subtle py-4 text-center">No mistakes in the last two weeks. Clean run.</p>
            ) : (
                <ul className="space-y-3.5">
                    {rows.map((r) => (
                        <li key={r.category} className="min-w-0">
                            <div className="flex items-center justify-between gap-2 mb-1.5">
                                <span className="text-[13px] font-medium truncate">{r.label}</span>
                                <span className="text-xs tabular-nums text-subtle shrink-0">
                                    <span className="text-fg font-semibold">{r.this_week}</span> / {r.last_week}
                                </span>
                            </div>
                            <div className="space-y-1" aria-label={`${r.label}: ${r.this_week} this week, ${r.last_week} last week`} role="img">
                                <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
                                    <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${(r.this_week / max) * 100}%` }} />
                                </div>
                                <div className="h-1 rounded-full bg-surface-2 overflow-hidden">
                                    <div className="h-full rounded-full bg-line-strong transition-[width] duration-700" style={{ width: `${(r.last_week / max) * 100}%` }} />
                                </div>
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    );
}

// ---------------- pre-submit checklist ----------------
function Checklist({ data, loading }) {
    const toast = useToast();
    const [ticked, setTicked] = useState({});
    const [copied, setCopied] = useState(false);
    const timer = useRef(null);

    async function copy() {
        try {
            await navigator.clipboard.writeText(data.text);
            setCopied(true);
            clearTimeout(timer.current);
            timer.current = setTimeout(() => setCopied(false), 1800);
        } catch {
            toast('Could not copy. Select the text manually.', 'error');
        }
    }

    const based = data?.based_on?.map((b) => b.label).join(' & ');
    return (
        <Card className="card-pad hero-accent">
            <CardHeader
                title="Pre-submit checklist"
                subtitle={based ? `Built from your recurring ${based} mistakes` : 'Starter list, it adapts as you log'}
                icon={ClipboardCheck}
                action={data && (
                    <Button size="sm" variant="secondary" icon={copied ? Check : Copy} onClick={copy} aria-label="Copy checklist">
                        <span className="hidden sm:inline">{copied ? 'Copied' : 'Copy'}</span>
                    </Button>
                )}
            />
            {loading && !data ? (
                <div className="space-y-2.5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-5" />)}</div>
            ) : data ? (
                <ul className="space-y-1">
                    {data.items.map((it, i) => (
                        <li key={it.text}>
                            <label className="flex items-start gap-2.5 rounded-lg px-1.5 py-1.5 -mx-1.5 row-hover cursor-pointer">
                                <Checkbox
                                    checked={!!ticked[i]}
                                    onChange={(v) => setTicked((t) => ({ ...t, [i]: v }))}
                                    label={it.text}
                                    className="mt-px"
                                />
                                <span className={cx('text-[13.5px] leading-snug flex-1 min-w-0 transition-colors', ticked[i] && 'text-subtle line-through')}>
                                    {it.text}
                                </span>
                                <span className="badge text-subtle bg-surface-2 shrink-0 hidden sm:inline-flex">{it.label}</span>
                            </label>
                        </li>
                    ))}
                </ul>
            ) : null}
        </Card>
    );
}

// ---------------- list ----------------
function MistakeRow({ m, onToggle, onDelete }) {
    const [confirming, setConfirming] = useState(false);
    const timer = useRef(null);
    const askDelete = () => {
        if (confirming) { clearTimeout(timer.current); onDelete(m); return; }
        setConfirming(true);
        timer.current = setTimeout(() => setConfirming(false), 3000);
    };
    return (
        <li className={cx('flex items-start gap-3 px-4 sm:px-5 py-4 transition-opacity', m.resolved && 'opacity-60')}>
            <Checkbox checked={m.resolved} onChange={(v) => onToggle(m, v)} label={m.resolved ? 'Mark as open' : 'Mark as resolved'} className="mt-0.5" />
            <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                    <CategoryBadge category={m.category} label={m.category_label} />
                    {m.pattern && <span className="badge text-muted bg-surface-2">{m.pattern}</span>}
                    <span className="text-[11px] text-subtle">{timeAgo(m.created_at)}</span>
                </div>
                {m.problem_title && (
                    m.link ? (
                        <a href={m.link} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-center gap-1 text-sm font-semibold hover:text-accent transition-colors max-w-full">
                            <span className="truncate">{m.problem_title}</span>
                            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-subtle" aria-hidden />
                        </a>
                    ) : <p className="mt-1.5 text-sm font-semibold truncate">{m.problem_title}</p>
                )}
                {!m.problem_title && m.link && (
                    <a href={m.link} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted hover:text-accent max-w-full">
                        <span className="truncate">{m.link.replace(/^https?:\/\/(www\.)?/, '')}</span>
                        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                    </a>
                )}
                {m.lesson && (
                    <p className={cx('mt-1.5 flex items-start gap-1.5 text-[14px] leading-snug font-medium', m.resolved && 'line-through decoration-subtle')}>
                        <Lightbulb className="h-4 w-4 text-accent shrink-0 mt-px" aria-hidden />
                        <span className="min-w-0">{m.lesson}</span>
                    </p>
                )}
                {m.what_happened && m.what_happened !== m.lesson && (
                    <p className="mt-1 text-[13px] text-muted leading-snug line-clamp-2 break-words">{m.what_happened}</p>
                )}
            </div>
            <button
                type="button"
                onClick={askDelete}
                className={cx('btn btn-sm shrink-0 -mr-1.5', confirming ? 'btn-danger bg-danger/10' : 'btn-ghost btn-icon h-8 w-8')}
                aria-label={confirming ? 'Confirm delete' : 'Delete mistake'}
            >
                {confirming ? 'Delete?' : <Trash2 className="h-4 w-4" />}
            </button>
        </li>
    );
}

export default function Mistakes() {
    const toast = useToast();
    const { data, error, loading, reload, setData } = useApi('/mistakes', { select: selectAll });
    const checklist = useApi('/mistakes/checklist');
    const [status, setStatus] = useState('open');
    const [cat, setCat] = useState('');

    const refreshAll = () => {
        invalidate('/mistakes');
        reload({ silent: true });
        checklist.reload({ silent: true });
    };

    const items = data?.items;
    const visible = useMemo(() => (items || []).filter((m) =>
        (!cat || m.category === cat)
        && (status === 'all' || (status === 'open' ? !m.resolved : m.resolved))), [items, cat, status]);
    const usedCats = useMemo(() => {
        const seen = new Set((items || []).map((m) => m.category));
        return (data?.categories || []).filter((c) => seen.has(c.key));
    }, [items, data?.categories]);

    async function toggle(m, resolved) {
        setData((d) => ({ ...d, items: d.items.map((x) => (x.id === m.id ? { ...x, resolved } : x)) }));
        try {
            await api(`/mistakes/${m.id}`, { method: 'PUT', body: { resolved } });
            if (resolved) toast('Resolved. Lesson learned.', 'success');
        } catch (e) {
            toast(e.message, 'error');
        }
        refreshAll();
    }

    async function remove(m) {
        setData((d) => ({ ...d, items: d.items.filter((x) => x.id !== m.id) }));
        try {
            await api(`/mistakes/${m.id}`, { method: 'DELETE' });
            toast('Deleted.', 'info');
        } catch (e) {
            toast(e.message, 'error');
        }
        refreshAll();
    }

    function onSaved(m) {
        setData((d) => (d ? { ...d, items: [m, ...d.items.filter((x) => x.id !== m.id)] } : d));
        if (status === 'resolved') setStatus('open');
        refreshAll();
    }

    return (
        <div className="space-y-6 min-w-0">
            <header className="animate-rise">
                <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Mistake journal</h1>
                <p className="text-sm text-muted mt-1">Every loss is a lesson.</p>
            </header>

            <Card className="card-pad animate-rise">
                <CardHeader title="Log a mistake" subtitle="AI tags the category and writes a one-line lesson" icon={PenLine} />
                <MistakeQuickAdd onSaved={onSaved} />
            </Card>

            {error && !data ? (
                <Card className="card-pad">
                    <Empty icon={NotebookPen} title="Couldn't load your journal" action={<Button size="sm" onClick={() => reload()}>Retry</Button>}>
                        {error}
                    </Empty>
                </Card>
            ) : !data?.stats ? (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[92px] rounded-2xl" />)}
                </div>
            ) : (
                <StatsStrip stats={data.stats} />
            )}

            <div className="grid gap-6 lg:grid-cols-2 items-start">
                {data?.stats ? <CategoryBars stats={data.stats} /> : <Skeleton className="h-56 rounded-2xl" />}
                <Checklist data={checklist.data} loading={checklist.loading} />
            </div>

            <Card className="overflow-hidden">
                <div className="px-4 sm:px-5 pt-4 sm:pt-5 pb-3 space-y-3 border-b border-line">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="min-w-0">
                            <h2 className="text-[15px] font-semibold tracking-tight">Journal</h2>
                            <p className="text-xs text-subtle">{visible.length} {visible.length === 1 ? 'entry' : 'entries'}</p>
                        </div>
                        <Segmented
                            value={status}
                            onChange={setStatus}
                            options={[{ value: 'open', label: 'Open' }, { value: 'resolved', label: 'Resolved' }, { value: 'all', label: 'All' }]}
                        />
                    </div>
                    {usedCats.length > 1 && (
                        <div className="-mx-4 px-4 sm:mx-0 sm:px-0 flex gap-1.5 overflow-x-auto no-scrollbar sm:flex-wrap">
                            <button type="button" onClick={() => setCat('')} className={cx('chip shrink-0', !cat && 'chip-on')}>All</button>
                            {usedCats.map((c) => (
                                <button key={c.key} type="button" onClick={() => setCat(cat === c.key ? '' : c.key)} className={cx('chip shrink-0', cat === c.key && 'chip-on')}>
                                    {c.label}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {loading && !data ? (
                    <div className="p-4 sm:p-5 space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>
                ) : visible.length === 0 ? (
                    <Empty icon={NotebookPen} title={items?.length ? 'Nothing here' : 'No mistakes logged yet'}>
                        {items?.length
                            ? 'Try another filter.'
                            : 'Next time a submission fails, write down why. Patterns show up fast.'}
                    </Empty>
                ) : (
                    <ul className="divide-y divide-line">
                        {visible.map((m) => <MistakeRow key={m.id} m={m} onToggle={toggle} onDelete={remove} />)}
                    </ul>
                )}
            </Card>
        </div>
    );
}
