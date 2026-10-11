import { useMemo, useState } from 'react';
import { Search, Send, RefreshCw, Code2, Layers } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, useLocalStorage, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Empty, ProgressBar, Segmented, Skeleton, useToast, cx } from '../components/ui';
import ProblemRow from '../components/ProblemRow';
import ProblemDetail from '../components/ProblemDetail';

const DIFFS = ['Easy', 'Medium', 'Hard'];
const DIFF_COLOR = { Easy: 'var(--easy)', Medium: 'var(--medium)', Hard: 'var(--hard)' };

export default function Problems({ openId, onChange }) {
    const logs = useApi('/logs?type=leetcode');
    const settings = useApi('/settings', { select: (d) => d });
    const [filter, setFilter] = useLocalStorage('problems:filter', 'pending');
    const [diff, setDiff] = useState(null);
    const [topic, setTopic] = useState('');
    const [q, setQ] = useState('');
    const [sending, setSending] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const toast = useToast();

    const all = useMemo(() => logs.data || [], [logs.data]);
    const topics = useMemo(() => {
        const m = {};
        for (const l of all) {
            if (!l.topic) continue;
            m[l.topic] ??= { sent: 0, solved: 0 };
            m[l.topic].sent += 1;
            m[l.topic].solved += l.is_completed ? 1 : 0;
        }
        return Object.entries(m).sort((a, b) => b[1].sent - a[1].sent);
    }, [all]);

    const visible = all.filter((l) =>
        (filter === 'all' || (filter === 'solved') === l.is_completed) &&
        (!diff || l.difficulty === diff) &&
        (!topic || l.topic === topic) &&
        (!q || l.title.toLowerCase().includes(q.toLowerCase())));

    const solved = all.filter((l) => l.is_completed).length;

    const toggle = async (log, value) => {
        logs.setData((list) => list.map((l) => (l.id === log.id ? { ...l, is_completed: value } : l)));
        try {
            await api(`/logs/${log.id}`, { method: 'PUT', body: { is_completed: value } });
            if (value) toast(`Solved: ${log.title}`);
            onChange?.();
        } catch (e) {
            toast(e.message, 'error');
            logs.reload({ silent: true });
        }
    };

    const sendNew = async () => {
        setSending(true);
        try {
            const res = await api('/trigger', { method: 'POST', body: { type: 'leetcode' } });
            toast(`Sent to your inbox: ${res.data.title}`);
            await logs.reload({ silent: true });
            onChange?.();
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
            logs.reload({ silent: true });
            onChange?.();
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setSyncing(false);
        }
    };

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 animate-rise">
                <div>
                    <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">DSA Problems</h1>
                    <p className="text-sm text-muted mt-1">Striver A2Z, one fresh problem at a time. Never a repeat.</p>
                </div>
                <div className="flex gap-2">
                    {settings.data?.leetcode_username && (
                        <Button icon={RefreshCw} loading={syncing} onClick={sync}>Sync LeetCode</Button>
                    )}
                    <Button variant="primary" icon={Send} loading={sending} onClick={sendNew}>New problem</Button>
                </div>
            </header>

            {/* Summary */}
            <Card className="card-pad">
                {logs.data ? (
                    <div className="grid grid-cols-1 sm:grid-cols-4 gap-5 items-center">
                        <div>
                            <div className="eyebrow">Solved</div>
                            <div className="mt-1 text-3xl font-bold tracking-tight tabular-nums">
                                {solved}<span className="text-subtle text-lg font-semibold"> / {all.length}</span>
                            </div>
                        </div>
                        {DIFFS.map((d) => {
                            const sent = all.filter((l) => l.difficulty === d);
                            const done = sent.filter((l) => l.is_completed).length;
                            return (
                                <button key={d} onClick={() => setDiff(diff === d ? null : d)} className={cx('text-left rounded-xl p-2 -m-2 transition-colors', diff === d ? 'bg-surface-2' : 'hover:bg-surface-2/60')}>
                                    <div className="flex items-center justify-between text-xs">
                                        <span className="font-semibold" style={{ color: DIFF_COLOR[d] }}>{d}</span>
                                        <span className="text-subtle tabular-nums">{done}/{sent.length}</span>
                                    </div>
                                    <ProgressBar value={sent.length ? (100 * done) / sent.length : 0} color={DIFF_COLOR[d]} className="mt-2" />
                                </button>
                            );
                        })}
                    </div>
                ) : <Skeleton className="h-14" />}
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 sm:gap-6 items-start">
                <Card className="lg:col-span-2 overflow-hidden">
                    <div className="p-3 sm:p-4 flex flex-col sm:flex-row gap-3 border-b border-line">
                        <Segmented value={filter} onChange={setFilter} options={[{ value: 'pending', label: 'Pending' }, { value: 'solved', label: 'Solved' }, { value: 'all', label: 'All' }]} />
                        <div className="relative flex-1">
                            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
                            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search problems" className="input h-9 pl-9" />
                        </div>
                    </div>
                    {(diff || topic) && (
                        <div className="flex flex-wrap gap-2 px-4 py-2.5 border-b border-line bg-surface-2/40">
                            {diff && <button className="chip chip-on" onClick={() => setDiff(null)}>{diff} ✕</button>}
                            {topic && <button className="chip chip-on" onClick={() => setTopic('')}>{topic} ✕</button>}
                        </div>
                    )}
                    {logs.loading && !logs.data ? (
                        <div className="p-4 space-y-3">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-11" />)}</div>
                    ) : visible.length ? (
                        <ul className="divide-y divide-line">
                            {visible.map((l) => <ProblemRow key={l.id} log={l} onToggle={toggle} />)}
                        </ul>
                    ) : (
                        <Empty icon={Code2} title={filter === 'pending' && !q && !diff && !topic ? 'Nothing pending' : 'No matches'}
                            action={filter === 'pending' && !q && <Button size="sm" variant="primary" icon={Send} loading={sending} onClick={sendNew}>Get a new problem</Button>}>
                            {filter === 'pending' && !q ? 'You are all caught up. Nice work.' : 'Try a different filter.'}
                        </Empty>
                    )}
                </Card>

                <Card className="card-pad">
                    <CardHeader title="Topics" subtitle="Tap to filter" icon={Layers} />
                    {topics.length ? (
                        <ul className="space-y-1">
                            {topics.map(([name, t]) => (
                                <li key={name}>
                                    <button onClick={() => setTopic(topic === name ? '' : name)}
                                        className={cx('w-full text-left rounded-lg px-2 py-2 transition-colors', topic === name ? 'bg-surface-2' : 'hover:bg-surface-2/60')}>
                                        <div className="flex items-center justify-between text-[13px]">
                                            <span className="font-medium truncate">{name}</span>
                                            <span className="text-subtle tabular-nums text-xs">{t.solved}/{t.sent}</span>
                                        </div>
                                        <ProgressBar value={(100 * t.solved) / t.sent} className="mt-1.5 h-1" />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    ) : <p className="text-sm text-subtle">Topics appear as problems arrive.</p>}
                </Card>
            </div>

            <ProblemDetail
                id={openId}
                onClose={() => navigate('problems')}
                onToggle={async (log, v) => { await toggle(log, v); }}
            />
        </div>
    );
}
