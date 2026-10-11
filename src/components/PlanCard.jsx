import { useEffect, useRef, useState } from 'react';
import { ListChecks, Plus, X, GripVertical, CornerDownLeft, PartyPopper, History, RotateCcw } from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, CardHeader, Checkbox, Empty, ProgressBar, Skeleton, useToast, cx } from './ui';

const MAX_LEN = 300;
const isTemp = (id) => typeof id === 'string';
const byPlan = (a, b) => Number(a.done) - Number(b.done) || (a.position ?? 0) - (b.position ?? 0) || String(a.id).localeCompare(String(b.id), undefined, { numeric: true });

const isTyping = (el) => !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));

const fmtDay = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) : '');

export default function PlanCard({ onChange }) {
    const { data, error, loading, reload, setData } = useApi('/todos');
    // Quick capture (and other features) announce new tasks with a window event.
    useEffect(() => {
        const onChanged = () => reload({ silent: true });
        window.addEventListener('todos-changed', onChanged);
        return () => window.removeEventListener('todos-changed', onChanged);
    }, [reload]);
    const toast = useToast();
    const [draft, setDraft] = useState('');
    const [editingId, setEditingId] = useState(null);
    const [dragId, setDragId] = useState(null);
    const inputRef = useRef(null);
    const dragMoved = useRef(false);
    const tempSeq = useRef(0);

    const items = data ? [...data].sort(byPlan) : [];
    const total = items.length;
    const done = items.filter((t) => t.done).length;
    const pct = total ? Math.round((done / total) * 100) : 0;
    const complete = total > 0 && done === total;

    // "n" anywhere (not while typing) jumps to the add input.
    useEffect(() => {
        const onKey = (e) => {
            if (e.key !== 'n' || e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
            if (isTyping(document.activeElement) || document.querySelector('[role="dialog"]')) return;
            e.preventDefault();
            inputRef.current?.focus();
        };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, []);

    const patch = (id, fields) => setData((list) => (list || []).map((t) => (t.id === id ? { ...t, ...fields } : t)));

    const fail = (e) => {
        toast(e.message, 'error');
        reload({ silent: true });
    };

    const add = async (e) => {
        e?.preventDefault();
        const text = draft.trim();
        if (!text) return;
        if (text.length > MAX_LEN) return toast(`Keep it under ${MAX_LEN} characters.`, 'error');
        const tempId = `tmp-${++tempSeq.current}`;
        const position = Math.max(0, ...items.map((t) => t.position ?? 0)) + 1;
        setData((list) => [...(list || []), { id: tempId, text, done: false, carried: false, position, pending: true }]);
        setDraft('');
        try {
            const res = await api('/todos', { method: 'POST', body: { text } });
            setData((list) => (list || []).map((t) => (t.id === tempId ? { ...res.data, key: tempId } : t)));
            onChange?.();
        } catch (err) {
            setData((list) => (list || []).filter((t) => t.id !== tempId));
            setDraft((d) => d || text);
            toast(err.message, 'error');
        }
    };

    const toggle = async (t, value) => {
        if (isTemp(t.id)) return;
        patch(t.id, { done: value, done_at: value ? new Date().toISOString() : null });
        try {
            await api(`/todos/${t.id}`, { method: 'PUT', body: { done: value } });
            onChange?.();
        } catch (e) { fail(e); }
    };

    const rename = async (t, raw) => {
        setEditingId(null);
        const text = raw.trim();
        if (!text || text === t.text) return;
        if (text.length > MAX_LEN) return toast(`Keep it under ${MAX_LEN} characters.`, 'error');
        patch(t.id, { text });
        try {
            await api(`/todos/${t.id}`, { method: 'PUT', body: { text } });
            onChange?.();
        } catch (e) { fail(e); }
    };

    const remove = async (t) => {
        if (isTemp(t.id)) return;
        setData((list) => (list || []).filter((x) => x.id !== t.id));
        try {
            await api(`/todos/${t.id}`, { method: 'DELETE' });
            onChange?.();
        } catch (e) { fail(e); }
    };

    // Drag to reorder (pointer devices); only open tasks reorder among themselves.
    const dragOver = (e, over) => {
        if (dragId == null || over.done) return;
        e.preventDefault();
        if (over.id === dragId) return;
        const open = items.filter((t) => !t.done);
        const from = open.findIndex((t) => t.id === dragId);
        const to = open.findIndex((t) => t.id === over.id);
        if (from < 0 || to < 0) return;
        const next = [...open];
        next.splice(to, 0, next.splice(from, 1)[0]);
        const pos = new Map(next.map((t, i) => [t.id, i]));
        dragMoved.current = true;
        setData((list) => (list || []).map((t) => (pos.has(t.id) ? { ...t, position: pos.get(t.id) } : t)));
    };

    const dragEnd = async () => {
        setDragId(null);
        if (!dragMoved.current) return;
        dragMoved.current = false;
        const ids = items.filter((t) => !t.done && !isTemp(t.id)).map((t) => t.id);
        try {
            await api('/todos/reorder', { method: 'POST', body: { ids } });
            onChange?.();
        } catch (e) { fail(e); }
    };

    return (
        <Card className="overflow-hidden">
            <div className="card-pad pb-0">
                <CardHeader
                    title="Today's plan"
                    subtitle={data ? (total ? `${done} of ${total} done` : 'Nothing planned yet') : 'Loading…'}
                    icon={ListChecks}
                    action={total > 0 && (
                        <div className="flex items-center gap-2" title={`${pct}% done`}>
                            <span className={cx('text-xs font-semibold tabular-nums', complete ? 'text-ok' : 'text-subtle')}>{pct}%</span>
                            <ProgressBar value={pct} className="w-16 sm:w-24" color={complete ? 'var(--ok)' : 'var(--accent)'} />
                        </div>
                    )}
                    className="mb-3"
                />

                <form onSubmit={add} className="relative mb-3">
                    <Plus className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-subtle" aria-hidden />
                    <input
                        ref={inputRef}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Escape') { setDraft(''); e.currentTarget.blur(); } }}
                        maxLength={MAX_LEN}
                        enterKeyHint="done"
                        placeholder="Add a task… press Enter"
                        aria-label="Add a task"
                        className="input pl-9 pr-12"
                    />
                    <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center">
                        {draft.trim() ? (
                            <button type="submit" className="btn btn-primary btn-sm btn-icon h-7 w-7 rounded-lg animate-rise" aria-label="Add task" title="Add (Enter)">
                                <CornerDownLeft className="h-3.5 w-3.5" />
                            </button>
                        ) : (
                            <kbd className="hidden sm:grid place-items-center h-6 min-w-6 px-1.5 mr-0.5 rounded-md border border-line bg-surface-2 font-mono text-[11px] text-subtle" title="Press N to add a task">N</kbd>
                        )}
                    </div>
                </form>
            </div>

            {loading && !data ? (
                <div className="px-4 sm:px-5 pb-4 space-y-2.5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-9" />)}</div>
            ) : error && !data ? (
                <Empty icon={ListChecks} title="Couldn't load your plan" action={<Button size="sm" icon={RotateCcw} onClick={() => reload()}>Try again</Button>}>
                    {error}
                </Empty>
            ) : total === 0 ? (
                <div className="border-t border-line">
                    <Empty icon={ListChecks} title="Plan your day">Add 3 things that would make today a win.</Empty>
                </div>
            ) : (
                <ul className="divide-y divide-line border-t border-line">
                    {items.map((t) => (
                        <PlanRow
                            key={t.key ?? t.id}
                            todo={t}
                            editing={editingId === t.id}
                            dragging={dragId === t.id}
                            onToggle={(v) => toggle(t, v)}
                            onEdit={() => !isTemp(t.id) && setEditingId(t.id)}
                            onRename={(text) => rename(t, text)}
                            onCancel={() => setEditingId(null)}
                            onRemove={() => remove(t)}
                            onDragStart={() => { dragMoved.current = false; setDragId(t.id); }}
                            onDragOver={(e) => dragOver(e, t)}
                            onDragEnd={dragEnd}
                        />
                    ))}
                </ul>
            )}

            {complete && (
                <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3 border-t border-line bg-ok/10 text-sm animate-rise">
                    <PartyPopper className="h-4 w-4 text-ok shrink-0" />
                    <span className="font-medium">Plan complete. <span className="text-muted font-normal">Well fought.</span></span>
                </div>
            )}
        </Card>
    );
}

function PlanRow({ todo: t, editing, dragging, onToggle, onEdit, onRename, onCancel, onRemove, onDragStart, onDragOver, onDragEnd }) {
    const canDrag = !t.done && !editing && !t.pending;

    return (
        <li
            draggable={canDrag}
            onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(t.id)); onDragStart(); }}
            onDragOver={onDragOver}
            onDrop={(e) => e.preventDefault()}
            onDragEnd={onDragEnd}
            className={cx(
                'group relative flex items-start gap-2.5 sm:gap-3 pl-3 pr-2 sm:pl-2 sm:pr-3 py-2.5 row-hover animate-rise',
                dragging && 'opacity-50 bg-surface-2',
                t.pending && 'opacity-70',
            )}
        >
            {canDrag && (
                <GripVertical
                    aria-hidden
                    className="hidden sm:block h-4 w-4 mt-0.5 -mr-1 shrink-0 cursor-grab text-subtle opacity-0 group-hover:opacity-60 transition-opacity"
                />
            )}
            {!canDrag && <span aria-hidden className="hidden sm:block w-3 shrink-0" />}

            <Checkbox checked={!!t.done} onChange={onToggle} label={`Mark "${t.text}" ${t.done ? 'not done' : 'done'}`} className="mt-px" />

            <div className="min-w-0 flex-1">
                {editing ? (
                    <InlineEdit text={t.text} onSave={onRename} onCancel={onCancel} />
                ) : (
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <button
                            type="button"
                            onClick={onEdit}
                            title={t.done ? undefined : 'Click to edit'}
                            className={cx(
                                'text-left text-sm leading-5 break-words [overflow-wrap:anywhere] min-w-0 cursor-text rounded-sm',
                                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                                t.done ? 'text-subtle line-through decoration-line-strong' : 'text-fg font-medium',
                            )}
                        >
                            {t.text}
                        </button>
                        {t.carried && !t.done && (
                            <span className="badge bg-surface-2 border border-line text-subtle font-medium" title={t.carried_from ? `Carried over from ${fmtDay(t.carried_from)}` : 'Carried over'}>
                                <History className="h-3 w-3" aria-hidden /> carried over
                            </span>
                        )}
                    </div>
                )}
            </div>

            {!editing && (
                <button
                    type="button"
                    onClick={onRemove}
                    disabled={t.pending}
                    aria-label={`Delete "${t.text}"`}
                    title="Delete"
                    className={cx(
                        'btn btn-ghost btn-icon h-7 w-7 -my-0.5 rounded-lg shrink-0 hover:text-danger',
                        // Always visible on touch screens; revealed on hover/focus where hovering exists.
                        '[@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100',
                    )}
                >
                    <X className="h-4 w-4" />
                </button>
            )}
        </li>
    );
}

// Enter saves, Esc cancels, blur saves. `settled` guards against a second save from the blur on unmount.
function InlineEdit({ text, onSave, onCancel }) {
    const [value, setValue] = useState(text);
    const settled = useRef(false);
    const finish = (save) => {
        if (settled.current) return;
        settled.current = true;
        if (save) onSave(value); else onCancel();
    };
    return (
        <input
            autoFocus
            value={value}
            maxLength={MAX_LEN}
            onChange={(e) => setValue(e.target.value)}
            onFocus={(e) => { const n = e.currentTarget.value.length; e.currentTarget.setSelectionRange(n, n); }}
            onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); finish(true); }
                if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(false); }
            }}
            onBlur={() => finish(true)}
            enterKeyHint="done"
            aria-label="Edit task"
            className="input h-8 -my-1 -ml-2 px-2 w-[calc(100%+0.5rem)]"
        />
    );
}
