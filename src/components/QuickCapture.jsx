import { useCallback, useEffect, useRef, useState } from 'react';
import { CalendarDays, Code2, CornerDownLeft, Hash, Link2, ListTodo, PlayCircle, Sparkles, Trophy, X, Zap } from 'lucide-react';
import { api } from '../lib/api';
import { invalidate } from '../lib/hooks';
import { consumeShareParams, sharePrefill } from '../lib/share';
import { Button, Spinner, cx, useToast } from './ui';

// Global quick capture: press `c`, dispatch `open-capture` ({detail:{text}}), or share a link to the PWA.
// Live-parses the line into chips (LeetCode / Codeforces / video / link / to-do, today|tomorrow, #tags);
// Enter commits them as to-dos, Esc closes.

const KBD = 'font-mono text-[10px] border border-line rounded px-1 py-0.5 bg-surface-2 text-muted mr-1';
const isTyping = (el) => !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));

const KIND = {
    leetcode: { icon: Code2, label: 'LeetCode', tone: 'text-medium bg-medium/10' },
    codeforces: { icon: Trophy, label: 'Codeforces', tone: 'text-accent bg-accent-soft' },
    video: { icon: PlayCircle, label: 'Video', tone: 'text-hard bg-hard/10' },
    link: { icon: Link2, label: 'Link', tone: 'text-muted bg-surface-2' },
    todo: { icon: ListTodo, label: 'Task', tone: 'text-ok bg-ok/10' },
};

const itemLabel = (it) => {
    if (it.kind === 'leetcode' || it.kind === 'codeforces') return `Solve: ${it.title || it.key || 'problem'}`;
    if (it.kind === 'video') return it.title ? `Watch: ${it.title}` : 'Watch video';
    if (it.kind === 'link') return it.title ? `Read: ${it.title}` : 'Read link';
    return it.text;
};

function ItemRow({ item, onToggleDay, onRemove }) {
    const k = KIND[item.kind] || KIND.todo;
    const Icon = k.icon;
    return (
        <li className="flex items-center gap-2 py-1.5 animate-rise">
            <span className={cx('badge shrink-0 gap-1', k.tone)}>
                <Icon className="h-3 w-3" aria-hidden />{k.label}
            </span>
            <span className="text-[13px] truncate flex-1 min-w-0" title={item.url || undefined}>{itemLabel(item)}</span>
            {(item.tags || []).slice(0, 3).map((t) => (
                <span key={t} className="badge shrink-0 text-subtle bg-surface-2 hidden sm:inline-flex">
                    <Hash className="h-3 w-3" aria-hidden />{t}
                </span>
            ))}
            <button
                type="button"
                onClick={onToggleDay}
                className={cx('badge shrink-0 gap-1 transition-colors hover:border-line-strong border border-transparent',
                    item.day === 'tomorrow' ? 'text-accent bg-accent-soft' : 'text-muted bg-surface-2')}
                title="Toggle today / tomorrow"
            >
                <CalendarDays className="h-3 w-3" aria-hidden />{item.day === 'tomorrow' ? 'Tomorrow' : 'Today'}
            </button>
            <button type="button" onClick={onRemove} className="btn btn-ghost btn-icon h-6 w-6 shrink-0 text-subtle" aria-label="Remove item">
                <X className="h-3.5 w-3.5" />
            </button>
        </li>
    );
}

const EMPTY = { items: [], ambiguous: false, source: 'rules', for: '' };

// Clean /share and #/today?capture=1 at import time, before the hash router's first read.
consumeShareParams();

export default function QuickCapture() {
    const toast = useToast();
    // Share target / ?capture=1 opens prefilled on first render (read once per page load).
    const [boot] = useState(() => consumeShareParams());
    const [open, setOpen] = useState(!!boot?.capture);
    const [text, setText] = useState(() => (boot?.capture ? sharePrefill(boot) : ''));
    const [res, setRes] = useState(EMPTY);
    const [parsing, setParsing] = useState(false);
    const [aiBusy, setAiBusy] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const inputRef = useRef(null);
    const ctrlRef = useRef(null);
    const timerRef = useRef(null);
    const openRef = useRef(open);
    // { title, url } from a share; sent as hints while that url is still in the input
    const hintRef = useRef(boot?.capture && boot.url ? { title: boot.title, url: boot.url } : null);

    useEffect(() => { openRef.current = open; }, [open]);

    const parse = useCallback(async (value, { ai = false } = {}) => {
        ctrlRef.current?.abort();
        const ctrl = new AbortController();
        ctrlRef.current = ctrl;
        const body = { text: value };
        const hint = hintRef.current;
        if (hint?.url && value.includes(hint.url)) Object.assign(body, { url: hint.url, title: hint.title || undefined });
        if (ai) body.ai = true;
        const r = await api('/capture/parse', { method: 'POST', body, signal: ctrl.signal });
        const next = { ...r.data, for: value };
        if (!ctrl.signal.aborted) setRes(next);
        return next;
    }, []);

    // Debounced live parse; only state updates from timers/promises (called from handlers).
    const scheduleParse = useCallback((raw, delay = 220) => {
        clearTimeout(timerRef.current);
        const value = raw.trim();
        timerRef.current = setTimeout(() => {
            if (!value) { ctrlRef.current?.abort(); setRes(EMPTY); setParsing(false); return; }
            setParsing(true);
            parse(value)
                .then(() => setError(''))
                .catch((e) => { if (e.name !== 'AbortError') setError(e.message); })
                .finally(() => setParsing(false));
        }, value ? delay : 0);
    }, [parse]);

    const show = useCallback((prefill = '') => {
        hintRef.current = null;
        setText(prefill);
        setRes(EMPTY);
        setError('');
        setOpen(true);
        scheduleParse(prefill, 0);
    }, [scheduleParse]);
    const close = useCallback(() => {
        clearTimeout(timerRef.current);
        ctrlRef.current?.abort();
        setOpen(false);
        setAiBusy(false);
        setParsing(false);
    }, []);

    const onInput = (e) => {
        setText(e.target.value);
        scheduleParse(e.target.value);
    };

    // Triggers: boot payload, `c` key, `open-capture` event
    useEffect(() => {
        let t;
        if (boot?.capture) scheduleParse(sharePrefill(boot), 0);
        else if (boot?.focus) t = setTimeout(() => window.dispatchEvent(new CustomEvent('focus-timer', { detail: { action: 'start' } })), 400);

        const onKey = (e) => {
            if (e.key !== 'c' || e.ctrlKey || e.metaKey || e.altKey || e.repeat || openRef.current) return;
            if (isTyping(e.target) || document.querySelector('[role="dialog"]')) return;
            e.preventDefault();
            show();
        };
        const onOpen = (e) => show(typeof e.detail?.text === 'string' ? e.detail.text : '');
        window.addEventListener('keydown', onKey);
        window.addEventListener('open-capture', onOpen);
        return () => {
            clearTimeout(t);
            clearTimeout(timerRef.current);
            window.removeEventListener('keydown', onKey);
            window.removeEventListener('open-capture', onOpen);
        };
    }, [boot, show, scheduleParse]);

    // Esc + scroll lock + autofocus
    useEffect(() => {
        if (!open) return;
        const onEsc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
        window.addEventListener('keydown', onEsc);
        const prev = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        const f = setTimeout(() => inputRef.current?.focus(), 30);
        return () => { window.removeEventListener('keydown', onEsc); document.body.style.overflow = prev; clearTimeout(f); };
    }, [open, close]);

    const splitWithAi = async () => {
        const value = text.trim();
        if (!value || aiBusy) return;
        setAiBusy(true);
        try {
            const r = await parse(value, { ai: true });
            if (r.source !== 'ai') toast('AI split unavailable, keeping it as one task.', 'info');
        } catch (e) {
            if (e.name !== 'AbortError') setError(e.message);
        } finally {
            setAiBusy(false);
        }
    };

    const commit = async () => {
        const value = text.trim();
        if (!value || saving) return;
        setSaving(true);
        setError('');
        try {
            let items = res.items;
            if (res.for !== value || !items.length) items = (await parse(value)).items;
            if (!items.length) throw new Error('Nothing to add.');
            const r = await api('/capture/commit', { method: 'POST', body: { items } });
            invalidate('/todos');
            window.dispatchEvent(new CustomEvent('todos-changed'));
            const n = r.data?.length || 0;
            const dup = r.skipped ? ` (${r.skipped} already on the list)` : '';
            toast(n ? `Added ${n} task${n === 1 ? '' : 's'}${dup}` : `Already on the list${dup ? '' : '.'}`, n ? 'success' : 'info');
            close();
        } catch (e) {
            if (e.name !== 'AbortError') setError(e.message);
        } finally {
            setSaving(false);
        }
    };

    const updateItem = (i, patch) => setRes((r) => ({ ...r, items: r.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) }));
    const removeItem = (i) => setRes((r) => ({ ...r, items: r.items.filter((_, j) => j !== i) }));

    if (!open) return null;
    const fresh = res.for === text.trim();
    const items = res.items; // last parse stays visible (dimmed) while typing
    return (
        <div className="fixed inset-0 z-[65] flex items-end sm:items-start sm:justify-center sm:pt-[14vh]">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-fade" onClick={close} />
            <div
                role="dialog"
                aria-modal="true"
                aria-label="Quick capture"
                className="relative w-full sm:max-w-xl bg-surface border-t sm:border border-line shadow-2xl rounded-t-3xl sm:rounded-2xl animate-sheet sm:animate-rise pb-[env(safe-area-inset-bottom)]"
            >
                <div className="sm:hidden flex justify-center pt-2.5">
                    <div className="h-1 w-10 rounded-full bg-line-strong" />
                </div>
                <form
                    onSubmit={(e) => { e.preventDefault(); commit(); }}
                    className="flex items-center gap-2.5 px-4 h-14 border-b border-line"
                >
                    <Zap className="h-4 w-4 text-accent shrink-0" aria-hidden />
                    <input
                        ref={inputRef}
                        value={text}
                        onChange={onInput}
                        placeholder="Task, LeetCode / CF / YouTube link… try “revise OS tomorrow #exam”"
                        className="flex-1 min-w-0 bg-transparent outline-none text-[15px] placeholder:text-subtle"
                        maxLength={4000}
                        enterKeyHint="done"
                        autoComplete="off"
                        aria-label="Capture"
                    />
                    {(parsing || saving) && <Spinner className="h-4 w-4 text-subtle shrink-0" />}
                    <button type="button" onClick={close} className="btn btn-ghost btn-icon shrink-0 sm:hidden" aria-label="Close">
                        <X className="h-4 w-4" />
                    </button>
                </form>

                <div className="px-4 py-2 min-h-[52px]">
                    {items.length > 0 ? (
                        <ul className={cx('divide-y divide-line transition-opacity', !fresh && 'opacity-60')}>
                            {items.map((it, i) => (
                                <ItemRow
                                    key={`${i}-${it.kind}-${it.url || it.text}`}
                                    item={it}
                                    onToggleDay={() => updateItem(i, { day: it.day === 'tomorrow' ? 'today' : 'tomorrow' })}
                                    onRemove={() => removeItem(i)}
                                />
                            ))}
                        </ul>
                    ) : (
                        <p className="text-[13px] text-subtle py-2">
                            {text.trim() ? (parsing ? 'Reading…' : 'Nothing to add yet.') : 'One per line or separated by “;”. Links become “Solve:” / “Watch:” tasks.'}
                        </p>
                    )}
                    {fresh && res.ambiguous && (
                        <div className="flex items-center gap-2 mt-1 text-[12px] text-muted">
                            <span className="flex-1">Looks like several tasks.</span>
                            <Button size="sm" variant="ghost" icon={Sparkles} loading={aiBusy} onClick={splitWithAi}>Split with AI</Button>
                        </div>
                    )}
                    {error && <p className="text-[12px] text-danger mt-1" role="alert">{error}</p>}
                </div>

                <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-line text-[11px] text-subtle">
                    <span className="hidden sm:flex items-center gap-3">
                        <span><kbd className={KBD}>↵</kbd> add</span>
                        <span><kbd className={KBD}>esc</kbd> close</span>
                        <span><kbd className={KBD}>c</kbd> open anywhere</span>
                    </span>
                    <Button
                        variant="primary"
                        size="sm"
                        icon={CornerDownLeft}
                        loading={saving}
                        disabled={!text.trim() || (fresh && !res.items.length && !parsing)}
                        onClick={commit}
                        className="ml-auto"
                    >
                        Add{fresh && res.items.length > 1 ? ` ${res.items.length}` : ''}
                    </Button>
                </div>
            </div>
        </div>
    );
}
