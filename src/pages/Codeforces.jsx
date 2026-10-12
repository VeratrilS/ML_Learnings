import { useMemo, useState } from 'react';
import {
    Swords, Shuffle, RefreshCw, ExternalLink, Mail, Tag, Trophy, Sparkles, Trash2,
    Settings as SettingsIcon, ChevronDown, X, History, Inbox, CircleAlert, ListChecks,
} from 'lucide-react';
import {
    Button, Card, CardHeader, Checkbox, Toggle, Segmented, Empty, Skeleton,
    RatingBadge, ProgressBar, cfColor, useToast, cx,
} from '../components/ui';
import { api } from '../lib/api';
import { useApi, useLocalStorage, timeAgo, navigate } from '../lib/hooks';

const MIN_R = 800;
const MAX_R = 3500;
const RATINGS = Array.from({ length: (MAX_R - MIN_R) / 100 + 1 }, (_, i) => MIN_R + i * 100);
const POPULAR_TAGS = [
    'greedy', 'math', 'implementation', 'dp', 'constructive algorithms', 'brute force',
    'data structures', 'binary search', 'sortings', 'graphs', 'number theory', 'strings',
    'two pointers', 'dfs and similar', 'trees', 'bitmasks',
];
const DEFAULT_FILTERS = { min: null, max: null, count: 5, tags: [], tagMode: 'any', email: false };
const HISTORY_PAGE = 40;

// Codeforces rank titles. Colours always come from cfColor so they match badges elsewhere.
const CF_TIERS = [
    { min: 0, name: 'Newbie' },
    { min: 1200, name: 'Pupil' },
    { min: 1400, name: 'Specialist' },
    { min: 1600, name: 'Expert' },
    { min: 1900, name: 'Candidate Master' },
    { min: 2100, name: 'Master' },
    { min: 2300, name: 'International Master' },
    { min: 2400, name: 'Grandmaster' },
    { min: 2600, name: 'International Grandmaster' },
    { min: 3000, name: 'Legendary Grandmaster' },
];
// Colour bands of cfColor, used for the range preview strip (problem ratings 800–3500, +100 so the top bucket has width).
const BANDS = [800, 1200, 1400, 1600, 1900, 2100, 2400, MAX_R + 100];
const BAND_SPAN = MAX_R + 100 - MIN_R;
const pctOf = (r) => ((Math.max(MIN_R, Math.min(MAX_R + 100, r)) - MIN_R) / BAND_SPAN) * 100;

function tierOf(rating) {
    const r = Number(rating) || 0;
    let i = 0;
    while (i + 1 < CF_TIERS.length && r >= CF_TIERS[i + 1].min) i += 1;
    return { tier: CF_TIERS[i], next: CF_TIERS[i + 1] || null };
}

const clamp = (r) => Math.max(MIN_R, Math.min(MAX_R, r));
const titleCase = (s) => (s || '').replace(/\b\w/g, (c) => c.toUpperCase());
const splitTags = (topic) => (topic ? topic.split(',').map((t) => t.trim()).filter(Boolean) : []);

function dayLabel(iso) {
    const d = new Date(iso);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return 'Today';
    if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
    return d.toLocaleDateString(undefined, {
        weekday: 'short', month: 'short', day: 'numeric',
        year: d.getFullYear() === today.getFullYear() ? undefined : 'numeric',
    });
}

function presetsFor(meta) {
    const lo = meta?.suggested_min ?? 800;
    const hi = meta?.suggested_max ?? 1200;
    return [
        { key: 'warm', label: 'Warm-up', min: clamp(lo - 200), max: clamp(lo) },
        { key: 'target', label: 'Target', min: clamp(lo), max: clamp(hi) },
        { key: 'stretch', label: 'Stretch', min: clamp(lo + 200), max: clamp(lo + 400) },
    ];
}

export default function Codeforces() {
    const toast = useToast();
    const meta = useApi('/cf/meta', { select: (d) => d });
    const history = useApi('/logs?type=codeforces');
    const [filters, setFilters] = useLocalStorage('cf.filters', DEFAULT_FILTERS);
    const [latestIds, setLatestIds] = useLocalStorage('cf.latestIds', []);
    const [view, setView] = useLocalStorage('cf.historyView', 'pending');
    const [generating, setGenerating] = useState(false);
    const [syncing, setSyncing] = useState(false);

    const f = { ...DEFAULT_FILTERS, ...filters };
    const user = meta.data?.user;
    const hasHandle = !!user?.handle;
    const logs = useMemo(() => history.data || [], [history.data]);

    const latest = useMemo(() => {
        const byId = new Map(logs.map((l) => [l.id, l]));
        return latestIds.map((id) => byId.get(id)).filter(Boolean);
    }, [logs, latestIds]);

    const patch = (p) => setFilters((prev) => ({ ...DEFAULT_FILTERS, ...prev, ...p }));

    const toggleSolved = async (log, value) => {
        const apply = (v) => history.setData((d) => (d || []).map((l) => (l.id === log.id ? { ...l, is_completed: v } : l)));
        apply(value);
        try {
            const res = await api(`/logs/${log.id}`, { method: 'PUT', body: { is_completed: value } });
            if (res?.data) history.setData((d) => (d || []).map((l) => (l.id === log.id ? res.data : l)));
        } catch (e) {
            apply(!value);
            toast(e.message, 'error');
        }
    };

    const remove = async (log) => {
        history.setData((d) => (d || []).filter((l) => l.id !== log.id));
        try {
            await api(`/logs/${log.id}`, { method: 'DELETE' });
        } catch (e) {
            toast(e.message, 'error');
            history.reload({ silent: true });
        }
    };

    const generate = async (body) => {
        setGenerating(true);
        try {
            const res = await api('/cf/suggest', { method: 'POST', body });
            const fresh = res.data || [];
            history.setData((d) => [...fresh, ...(d || []).filter((l) => !fresh.some((n) => n.id === l.id))]);
            setLatestIds(fresh.map((l) => l.id));
            toast(`${fresh.length} fresh problem${fresh.length === 1 ? '' : 's'} ready${res.emailed ? ' · emailed' : body.email ? ' · email failed' : ''}`);
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setGenerating(false);
        }
    };

    const sync = async () => {
        setSyncing(true);
        try {
            const res = await api('/cf/sync', { method: 'POST' });
            const n = res.updated?.length || 0;
            toast(n ? `Marked ${n} problem${n === 1 ? '' : 's'} solved from Codeforces` : 'Already up to date', n ? 'success' : 'info');
            if (n) history.reload({ silent: true });
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setSyncing(false);
        }
    };

    return (
        <div className="space-y-4 sm:space-y-5 animate-rise">
            <header className="flex flex-wrap items-end justify-between gap-3">
                <div className="min-w-0">
                    <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
                        <Swords className="h-6 w-6 text-accent shrink-0" aria-hidden />
                        Codeforces
                    </h1>
                    <p className="text-sm text-subtle mt-0.5">Fresh, unseen problems tuned to your rating.</p>
                </div>
                {hasHandle && (
                    <Button
                        icon={RefreshCw}
                        size="sm"
                        onClick={sync}
                        loading={syncing}
                        title="Mark problems you've solved on Codeforces as done"
                    >
                        {syncing ? 'Syncing…' : 'Sync solved'}
                    </Button>
                )}
            </header>

            <ProfileStrip
                loading={meta.loading && !meta.data}
                user={user}
                error={meta.error}
                range={meta.data ? [meta.data.suggested_min, meta.data.suggested_max] : null}
            />

            <Generator
                meta={meta.data}
                metaLoading={meta.loading && !meta.data}
                filters={f}
                patch={patch}
                generating={generating}
                onGenerate={generate}
            />

            {(latestIds.length > 0 && (latest.length > 0 || history.loading)) && (
                <LatestSet
                    items={latest}
                    loading={history.loading && !history.data}
                    onToggle={toggleSolved}
                    onDismiss={() => setLatestIds([])}
                />
            )}

            <HistoryCard
                logs={logs}
                loading={history.loading && !history.data}
                error={history.error}
                view={view}
                setView={setView}
                onToggle={toggleSolved}
                onDelete={remove}
                onRetry={() => history.reload()}
            />
        </div>
    );
}

function ProfileStrip({ loading, user, error }) {
    if (loading) {
        return (
            <Card className="card-pad flex items-center gap-3">
                <Skeleton className="h-10 w-10 rounded-xl" />
                <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-3 w-48" />
                </div>
            </Card>
        );
    }
    if (error) {
        return (
            <Card className="card-pad flex items-center gap-2.5 text-sm text-muted">
                <CircleAlert className="h-4 w-4 text-danger shrink-0" />
                <span className="min-w-0">Couldn&apos;t load Codeforces data: {error}</span>
            </Card>
        );
    }
    if (!user) {
        return (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-line-strong bg-surface-2/60 px-4 py-3">
                <p className="text-[13px] text-muted min-w-0 flex-1 basis-60">
                    Add your handle in Settings to auto-tune difficulty and skip problems you&apos;ve tried.
                </p>
                <Button size="sm" icon={SettingsIcon} onClick={() => navigate('settings')}>Open Settings</Button>
            </div>
        );
    }
    if (user.error) {
        return (
            <Card className="card-pad flex flex-wrap items-center gap-2.5 text-sm">
                <CircleAlert className="h-4 w-4 text-danger shrink-0" />
                <span className="min-w-0 flex-1 text-muted">
                    Couldn&apos;t load <span className="font-semibold text-fg">{user.handle}</span>: {user.error}
                </span>
                <Button size="sm" variant="ghost" icon={SettingsIcon} onClick={() => navigate('settings')}>Settings</Button>
            </Card>
        );
    }
    const color = user.rating ? cfColor(user.rating) : undefined;
    return (
        <Card className="card-pad flex flex-wrap items-center gap-x-5 gap-y-3">
            <div className="flex items-center gap-3 min-w-0 flex-1 basis-48">
                <div
                    className="grid place-items-center h-10 w-10 rounded-xl shrink-0 font-bold text-base"
                    style={color ? { color, background: `${color}1f` } : undefined}
                >
                    {user.handle.slice(0, 1).toUpperCase()}
                </div>
                <div className="min-w-0">
                    <a
                        href={`https://codeforces.com/profile/${encodeURIComponent(user.handle)}`}
                        target="_blank"
                        rel="noreferrer"
                        className="block font-semibold truncate hover:underline underline-offset-2"
                        style={color ? { color } : undefined}
                    >
                        {user.handle}
                    </a>
                    <p className="text-xs text-subtle truncate">{user.rank ? titleCase(user.rank) : 'Unrated'}</p>
                </div>
            </div>
            <div className="flex items-center gap-5">
                <Stat label="Rating" value={user.rating} />
                <Stat label="Max" value={user.max_rating} icon={Trophy} />
            </div>
        </Card>
    );
}

function Stat({ label, value, icon: Icon }) {
    return (
        <div className="text-right">
            <p className="eyebrow flex items-center justify-end gap-1">
                {Icon && <Icon className="h-3 w-3" aria-hidden />}
                {label}
            </p>
            <p className="font-mono text-lg font-semibold leading-tight" style={value ? { color: cfColor(value) } : undefined}>
                {value ?? '—'}
            </p>
        </div>
    );
}

function Generator({ meta, metaLoading, filters, patch, generating, onGenerate }) {
    const [moreOpen, setMoreOpen] = useState(false);
    const min = filters.min ?? meta?.suggested_min ?? 800;
    const max = filters.max ?? meta?.suggested_max ?? 1200;
    const presets = presetsFor(meta);
    const allTags = meta?.tags || [];
    const popular = allTags.length ? POPULAR_TAGS.filter((t) => allTags.includes(t)) : POPULAR_TAGS;
    const others = allTags.filter((t) => !POPULAR_TAGS.includes(t));
    const selected = filters.tags || [];
    const hiddenSelected = selected.filter((t) => others.includes(t)).length;

    const toggleTag = (t) => patch({ tags: selected.includes(t) ? selected.filter((x) => x !== t) : [...selected, t] });
    const setMin = (v) => patch({ min: v, max: Math.max(v, max) });
    const setMax = (v) => patch({ max: v, min: Math.min(v, min) });

    const submit = () => onGenerate({
        count: filters.count,
        min_rating: min,
        max_rating: max,
        tags: selected,
        tag_mode: filters.tagMode,
        email: !!filters.email,
    });

    const tagChip = (t) => {
        const on = selected.includes(t);
        return (
            <button key={t} type="button" onClick={() => toggleTag(t)} aria-pressed={on} className={cx('chip', on && 'chip-on')}>
                {t}
            </button>
        );
    };

    return (
        <Card className="card-pad">
            <CardHeader
                title="New set"
                subtitle="Unseen problems only — never repeats a suggestion"
                icon={Shuffle}
            />

            <div className="space-y-5">
                <div>
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                        <span className="label mb-0">Rating range</span>
                        <div className="flex flex-wrap gap-1.5">
                            {presets.map((p) => (
                                <button
                                    key={p.key}
                                    type="button"
                                    disabled={metaLoading}
                                    onClick={() => patch({ min: p.min, max: p.max })}
                                    className={cx('chip disabled:opacity-50', p.min === min && p.max === max && 'chip-on')}
                                    title={`${p.min}–${p.max}`}
                                >
                                    {p.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    {metaLoading ? (
                        <div className="grid grid-cols-2 gap-3">
                            <Skeleton className="h-10" />
                            <Skeleton className="h-10" />
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 gap-3">
                            <RatingSelect label="Min" value={min} onChange={setMin} />
                            <RatingSelect label="Max" value={max} onChange={setMax} />
                        </div>
                    )}
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="label mb-0">How many</span>
                    <Segmented
                        options={[{ value: 3, label: '3' }, { value: 5, label: '5' }, { value: 10, label: '10' }]}
                        value={filters.count}
                        onChange={(v) => patch({ count: v })}
                    />
                </div>

                <div>
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                        <span className="label mb-0 flex items-center gap-1.5">
                            <Tag className="h-3.5 w-3.5" aria-hidden />
                            Tags
                            {selected.length > 0 && <span className="text-subtle font-normal">· {selected.length} selected</span>}
                        </span>
                        <div className="flex items-center gap-1.5">
                            {selected.length >= 2 && (
                                <Segmented
                                    options={[{ value: 'any', label: 'Any' }, { value: 'all', label: 'All' }]}
                                    value={filters.tagMode}
                                    onChange={(v) => patch({ tagMode: v })}
                                />
                            )}
                            {selected.length > 0 && (
                                <Button variant="ghost" size="sm" icon={X} onClick={() => patch({ tags: [] })}>Clear</Button>
                            )}
                        </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                        {popular.map(tagChip)}
                        {others.length > 0 && (
                            <button
                                type="button"
                                onClick={() => setMoreOpen((o) => !o)}
                                aria-expanded={moreOpen}
                                className="chip border-dashed"
                            >
                                {moreOpen ? 'Fewer tags' : 'More tags'}
                                {!moreOpen && hiddenSelected > 0 && <span className="text-accent">· {hiddenSelected}</span>}
                                <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', moreOpen && 'rotate-180')} aria-hidden />
                            </button>
                        )}
                    </div>
                    {moreOpen && others.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-line animate-rise">
                            {others.map(tagChip)}
                        </div>
                    )}
                    {selected.length >= 2 && (
                        <p className="text-xs text-subtle mt-2">
                            {filters.tagMode === 'all' ? 'Problems must have every selected tag.' : 'Problems with any selected tag.'}
                        </p>
                    )}
                </div>

                <div className="flex items-center justify-between gap-3 rounded-xl bg-surface-2 border border-line px-3.5 py-2.5">
                    <span className="flex items-center gap-2 text-sm text-muted min-w-0">
                        <Mail className="h-4 w-4 shrink-0" aria-hidden />
                        <span className="truncate">Also email me this set</span>
                    </span>
                    <Toggle checked={!!filters.email} onChange={(v) => patch({ email: v })} label="Also email me this set" />
                </div>

                <Button
                    variant="primary"
                    size="lg"
                    icon={Sparkles}
                    className="w-full"
                    loading={generating}
                    disabled={metaLoading}
                    onClick={submit}
                >
                    {generating ? 'Finding problems…' : `Generate ${filters.count} problems`}
                </Button>
            </div>
        </Card>
    );
}

function RatingSelect({ label, value, onChange }) {
    return (
        <label className="block min-w-0">
            <span className="text-xs text-subtle mb-1 block">{label}</span>
            <select className="input font-mono" value={value} onChange={(e) => onChange(Number(e.target.value))}>
                {RATINGS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
        </label>
    );
}

function TagList({ topic, max = 3, className }) {
    const tags = splitTags(topic);
    if (!tags.length) return null;
    const shown = tags.slice(0, max);
    return (
        <div className={cx('flex flex-wrap gap-1 min-w-0', className)}>
            {shown.map((t) => (
                <span key={t} className="badge font-medium text-subtle bg-surface-2 border border-line">{t}</span>
            ))}
            {tags.length > max && (
                <span className="badge font-medium text-subtle" title={tags.slice(max).join(', ')}>+{tags.length - max}</span>
            )}
        </div>
    );
}

function LatestSet({ items, loading, onToggle, onDismiss }) {
    const solved = items.filter((l) => l.is_completed).length;
    const total = items.length;
    const done = total > 0 && solved === total;
    return (
        <Card className="card-pad animate-rise">
            <CardHeader
                title="Latest set"
                subtitle={items[0] ? `Generated ${timeAgo(items[0].timestamp)}` : 'Loading…'}
                icon={ListChecks}
                action={<Button variant="ghost" className="btn-icon h-8 w-8" onClick={onDismiss} aria-label="Hide latest set" title="Hide"><X className="h-4 w-4" /></Button>}
            />
            {loading ? (
                <div className="space-y-2">
                    {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}
                </div>
            ) : (
                <>
                    <div className="mb-4">
                        <div className="flex items-baseline justify-between mb-1.5">
                            <p className="text-sm">
                                <span className={cx('font-semibold font-mono', done ? 'text-ok' : 'text-fg')}>{solved}</span>
                                <span className="text-subtle"> / {total} solved</span>
                            </p>
                            {done && <span className="text-xs font-medium text-ok flex items-center gap-1"><Trophy className="h-3.5 w-3.5" /> Set cleared</span>}
                        </div>
                        <ProgressBar value={total ? (solved / total) * 100 : 0} color={done ? 'var(--ok)' : 'var(--accent)'} />
                    </div>
                    <ul className="space-y-2">
                        {items.map((l, i) => (
                            <li
                                key={l.id}
                                className={cx(
                                    'flex items-start gap-3 rounded-xl border border-line px-3 py-3 transition-colors animate-rise',
                                    l.is_completed ? 'bg-surface-2/60' : 'bg-surface hover:border-line-strong',
                                )}
                                style={{ animationDelay: `${i * 40}ms` }}
                            >
                                <Checkbox
                                    checked={l.is_completed}
                                    onChange={(v) => onToggle(l, v)}
                                    label={`Mark ${l.title} as ${l.is_completed ? 'unsolved' : 'solved'}`}
                                    className="mt-0.5"
                                />
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2 min-w-0">
                                        <RatingBadge rating={l.difficulty} />
                                        <a
                                            href={l.link}
                                            target="_blank"
                                            rel="noreferrer"
                                            className={cx(
                                                'text-sm font-medium truncate hover:text-accent transition-colors',
                                                l.is_completed && 'line-through text-subtle',
                                            )}
                                        >
                                            {l.title}
                                        </a>
                                    </div>
                                    <TagList topic={l.topic} className="mt-1.5" />
                                </div>
                                <a
                                    href={l.link}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="btn btn-ghost btn-icon h-8 w-8 -mr-1 -mt-1 shrink-0"
                                    aria-label={`Open ${l.title} on Codeforces`}
                                >
                                    <ExternalLink className="h-4 w-4" />
                                </a>
                            </li>
                        ))}
                    </ul>
                </>
            )}
        </Card>
    );
}

function HistoryCard({ logs, loading, error, view, setView, onToggle, onDelete, onRetry }) {
    const [limit, setLimit] = useState(HISTORY_PAGE);
    const counts = useMemo(() => {
        const solved = logs.filter((l) => l.is_completed).length;
        return { pending: logs.length - solved, solved, all: logs.length };
    }, [logs]);

    const filtered = useMemo(() => logs.filter((l) => (
        view === 'all' ? true : view === 'solved' ? l.is_completed : !l.is_completed
    )), [logs, view]);

    const groups = useMemo(() => {
        const out = [];
        for (const l of filtered.slice(0, limit)) {
            const label = dayLabel(l.timestamp);
            const last = out[out.length - 1];
            if (last && last.label === label) last.items.push(l);
            else out.push({ label, items: [l] });
        }
        return out;
    }, [filtered, limit]);

    const changeView = (v) => { setView(v); setLimit(HISTORY_PAGE); };

    return (
        <Card className="card-pad">
            <CardHeader title="History" subtitle={`${counts.all} suggested · ${counts.solved} solved`} icon={History} />
            <Segmented
                className="mb-3 max-w-full overflow-x-auto no-scrollbar"
                options={[
                    { value: 'pending', label: `Pending ${counts.pending || ''}`.trim() },
                    { value: 'solved', label: `Solved ${counts.solved || ''}`.trim() },
                    { value: 'all', label: 'All' },
                ]}
                value={view}
                onChange={changeView}
            />

            {loading ? (
                <div className="space-y-2">
                    {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
                </div>
            ) : error && !logs.length ? (
                <Empty
                    icon={CircleAlert}
                    title="Couldn't load history"
                    action={<Button size="sm" icon={RefreshCw} onClick={onRetry}>Retry</Button>}
                >
                    {error}
                </Empty>
            ) : !filtered.length ? (
                <Empty icon={view === 'solved' ? Trophy : Inbox} title={emptyTitle(view, logs.length)}>
                    {logs.length
                        ? view === 'solved' ? 'Tick problems off as you solve them, or sync from Codeforces.' : 'Generate a new set to keep going.'
                        : 'Your generated problems will show up here.'}
                </Empty>
            ) : (
                <div className="space-y-4">
                    {groups.map((g) => (
                        <div key={g.label}>
                            <p className="eyebrow mb-1.5 px-1">{g.label}</p>
                            <ul className="-mx-2">
                                {g.items.map((l) => (
                                    <HistoryRow key={l.id} log={l} onToggle={onToggle} onDelete={onDelete} />
                                ))}
                            </ul>
                        </div>
                    ))}
                    {filtered.length > limit && (
                        <Button variant="secondary" size="sm" className="w-full" onClick={() => setLimit((n) => n + HISTORY_PAGE)}>
                            Show more ({filtered.length - limit} left)
                        </Button>
                    )}
                </div>
            )}
        </Card>
    );
}

function emptyTitle(view, total) {
    if (!total) return 'No problems yet';
    if (view === 'pending') return 'All caught up';
    if (view === 'solved') return 'Nothing solved yet';
    return 'Nothing here';
}

function HistoryRow({ log, onToggle, onDelete }) {
    const tags = splitTags(log.topic).join(', ');
    return (
        <li className="group flex items-center gap-3 rounded-xl px-2 py-2 row-hover">
            <Checkbox
                checked={log.is_completed}
                onChange={(v) => onToggle(log, v)}
                label={`Mark ${log.title} as ${log.is_completed ? 'unsolved' : 'solved'}`}
            />
            <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 min-w-0">
                    <RatingBadge rating={log.difficulty} />
                    <a
                        href={log.link}
                        target="_blank"
                        rel="noreferrer"
                        className={cx(
                            'text-sm font-medium truncate hover:text-accent transition-colors',
                            log.is_completed && 'text-muted',
                        )}
                    >
                        {log.title}
                    </a>
                </div>
                <div className="flex items-center gap-1.5 mt-0.5 text-xs text-subtle min-w-0">
                    <span className="shrink-0">{timeAgo(log.timestamp)}</span>
                    {tags && <><span aria-hidden>·</span><span className="truncate" title={tags}>{tags}</span></>}
                </div>
            </div>
            <Button
                variant="ghost"
                className="btn-icon h-8 w-8 shrink-0 hover:text-danger sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                onClick={() => onDelete(log)}
                aria-label={`Delete ${log.title}`}
                title="Delete"
            >
                <Trash2 className="h-4 w-4" />
            </Button>
        </li>
    );
}
