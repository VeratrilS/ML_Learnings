import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
    Search, House, Code2, Swords, FileText, Settings as SettingsIcon, Send, Sparkles, RefreshCw,
    CircleCheck, Circle, Tv, Timer, SunMoon, CirclePause, CirclePlay, CornerDownLeft,
} from 'lucide-react';
import { api } from '../lib/api';
import { navigate } from '../lib/hooks';
import { useTheme } from '../themes/ThemeContext';
import { useToast, Spinner, cx } from './ui';

const DIFF = {
    Easy: 'text-easy bg-easy/10',
    Medium: 'text-medium bg-medium/10',
    Hard: 'text-hard bg-hard/10',
};

const NAV = [
    { id: 'today', label: 'Today', icon: House, keywords: 'home dashboard daily' },
    { id: 'problems', label: 'DSA Problems', icon: Code2, keywords: 'leetcode list dsa' },
    { id: 'cf', label: 'Codeforces', icon: Swords, keywords: 'cf contest' },
    { id: 'pdf', label: 'PDF Studio', icon: FileText, keywords: 'documents notes' },
    { id: 'settings', label: 'Settings', icon: SettingsIcon, keywords: 'preferences config options' },
];

const isTyping = (el) => el && (/^(input|textarea|select)$/i.test(el.tagName) || el.isContentEditable);

// All query words must appear in label + keywords; lower score ranks higher.
function score(cmd, words, q) {
    const label = cmd.label.toLowerCase();
    const hay = `${label} ${cmd.keywords || ''} ${cmd.group}`.toLowerCase();
    if (!words.every((w) => hay.includes(w))) return -1;
    if (label.startsWith(q)) return 0;
    if (label.split(/[\s:/]+/).some((t) => t.startsWith(words[0]))) return 1;
    if (label.includes(words[0])) return 2;
    return 3;
}

async function getActiveSeries() {
    const res = await api('/watch');
    const list = res.data || [];
    return list.find((s) => s.is_active) || null;
}

export default function CommandPalette() {
    const { isDark, toggleTheme } = useTheme();
    const toast = useToast();
    const uid = useId();

    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState('');
    const [sel, setSel] = useState(0);
    const [running, setRunning] = useState(null);
    const [paused, setPaused] = useState(null); // null = unknown
    const [problems, setProblems] = useState([]);

    const listRef = useRef(null);
    const inputRef = useRef(null);
    const openRef = useRef(false);
    const restoreFocusRef = useRef(null);
    useEffect(() => { openRef.current = open; }, [open]);

    const openPalette = useCallback(() => {
        if (openRef.current) return;
        openRef.current = true;
        restoreFocusRef.current = document.activeElement;
        setQuery('');
        setSel(0);
        setOpen(true);
    }, []);

    const close = useCallback(() => setOpen(false), []);

    // Global shortcuts + external open event
    useEffect(() => {
        const onKey = (e) => {
            if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                if (openRef.current) setOpen(false);
                else openPalette();
                return;
            }
            if (e.key === '/' && !openRef.current && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target)) {
                e.preventDefault();
                openPalette();
            }
        };
        const onOpenEvent = () => openPalette();
        window.addEventListener('keydown', onKey);
        window.addEventListener('open-command-palette', onOpenEvent);
        return () => {
            window.removeEventListener('keydown', onKey);
            window.removeEventListener('open-command-palette', onOpenEvent);
        };
    }, [openPalette]);

    // Body scroll lock, focus restore, and fresh data on every open
    useEffect(() => {
        if (!open) return;
        const prevOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        const onEsc = (e) => { if (e.key === 'Escape') setOpen(false); };
        window.addEventListener('keydown', onEsc);
        const ctrl = new AbortController();
        api('/settings', { signal: ctrl.signal })
            .then((s) => setPaused(String(s.leetcode_paused) === '1'))
            .catch(() => {});
        api('/logs?type=leetcode', { signal: ctrl.signal })
            .then((r) => setProblems((r.data || []).slice(0, 30)))
            .catch(() => {});
        return () => {
            ctrl.abort();
            window.removeEventListener('keydown', onEsc);
            document.body.style.overflow = prevOverflow;
            const el = restoreFocusRef.current;
            if (el && typeof el.focus === 'function' && document.contains(el)) el.focus({ preventScroll: true });
        };
    }, [open]);

    const commands = useMemo(() => {
        const nav = NAV.map((n) => ({
            id: `nav-${n.id}`, group: 'Navigate', label: n.label, icon: n.icon, keywords: `go open ${n.keywords}`,
            hint: 'Jump', run: () => navigate(n.id),
        }));

        const actions = [
            {
                id: 'lc-send', label: 'Send me a new LeetCode problem', icon: Send, keywords: 'email trigger new question daily',
                hint: 'Email', async: true, runningHint: 'Picking a problem… up to 2 min',
                run: async () => {
                    const res = await api('/trigger', { method: 'POST', body: { type: 'leetcode' } });
                    toast(`Sent: ${res.data?.title || 'new problem'}`);
                },
            },
            {
                id: 'cf-suggest', label: 'Generate 5 Codeforces problems', icon: Sparkles, keywords: 'cf suggest practice set',
                hint: 'Generate', async: true, runningHint: 'Generating…',
                run: async () => {
                    await api('/cf/suggest', { method: 'POST', body: { count: 5 } });
                    toast('5 Codeforces problems ready');
                    navigate('cf');
                },
            },
            {
                id: 'lc-sync', label: 'Sync solved from LeetCode', icon: RefreshCw, keywords: 'refresh solved accepted lc',
                hint: 'Sync', async: true, runningHint: 'Syncing…',
                run: async () => {
                    const res = await api('/leetcode/sync', { method: 'POST' });
                    const n = res.updated?.length || 0;
                    toast(n ? `Synced ${n} solved problem${n === 1 ? '' : 's'} from LeetCode` : 'Already up to date', n ? 'success' : 'info');
                },
            },
            {
                id: 'cf-sync', label: 'Sync solved from Codeforces', icon: RefreshCw, keywords: 'refresh solved accepted cf',
                hint: 'Sync', async: true, runningHint: 'Syncing…',
                run: async () => {
                    const res = await api('/cf/sync', { method: 'POST' });
                    const n = res.updated?.length || 0;
                    toast(n ? `Synced ${n} solved problem${n === 1 ? '' : 's'} from Codeforces` : 'Already up to date', n ? 'success' : 'info');
                },
            },
            {
                id: 'watch-mark', label: "Mark today's episode watched", icon: CircleCheck, keywords: 'anime show series done tv',
                hint: 'Done', async: true, runningHint: 'Saving…',
                run: async () => {
                    const s = await getActiveSeries();
                    if (!s) return toast('No active series. Add one on Today.', 'info');
                    if (s.finished) return toast(`${s.title} is finished. Add the next season!`, 'info');
                    await api(`/watch/${s.id}/watched`, { method: 'POST' });
                    toast(`Episode ${s.next_episode} watched`);
                },
            },
            {
                id: 'watch-open', label: "Watch today's episode", icon: Tv, keywords: 'anime show series play tv',
                hint: 'New tab', async: true, runningHint: 'Opening…',
                run: async () => {
                    // Open the tab synchronously-ish to reduce popup blocking, then point it at the episode.
                    const win = window.open('about:blank', '_blank');
                    try {
                        const s = await getActiveSeries();
                        if (!s || !s.next_url) {
                            win?.close();
                            return toast(s ? `${s.title} is finished. Add the next season!` : 'No active series. Add one on Today.', 'info');
                        }
                        if (win) { win.opener = null; win.location.href = s.next_url; }
                        else window.open(s.next_url, '_blank', 'noopener');
                    } catch (e) {
                        win?.close();
                        throw e;
                    }
                },
            },
            {
                id: 'focus', label: 'Start a 25-min focus session', icon: Timer, keywords: 'pomodoro timer concentrate',
                hint: 'Start',
                run: () => {
                    const onToday = /^#?\/?(today)?$/.test(window.location.hash);
                    navigate('today');
                    const fire = () => window.dispatchEvent(new CustomEvent('focus-timer', { detail: { action: 'start' } }));
                    if (onToday) fire();
                    else setTimeout(fire, 80); // let Today (and its timer) mount first
                    toast('Focus started');
                },
            },
            {
                id: 'theme', label: 'Toggle light / dark theme', icon: SunMoon, keywords: 'appearance mode color night',
                hint: isDark ? 'Go light' : 'Go dark', run: () => toggleTheme(),
            },
        ];

        const pauseCmd = {
            id: 'pause', label: 'Pause automatic problem emails', icon: CirclePause, keywords: 'stop mute schedule cron leetcode',
            hint: 'Pause', async: true, runningHint: 'Saving…',
            run: async () => {
                const s = await api('/settings', { method: 'POST', body: { leetcode_paused: '1' } });
                setPaused(String(s.leetcode_paused ?? '1') === '1');
                toast('Automatic problem emails paused', 'info');
            },
        };
        const resumeCmd = {
            id: 'resume', label: 'Resume automatic problem emails', icon: CirclePlay, keywords: 'start unmute schedule cron leetcode',
            hint: 'Resume', async: true, runningHint: 'Saving…',
            run: async () => {
                const s = await api('/settings', { method: 'POST', body: { leetcode_paused: '0' } });
                setPaused(String(s.leetcode_paused ?? '0') === '1');
                toast('Automatic problem emails resumed');
            },
        };
        if (paused === true) actions.push(resumeCmd);
        else if (paused === false) actions.push(pauseCmd);
        else actions.push(pauseCmd, resumeCmd);

        const probs = problems.map((p) => ({
            id: `prob-${p.id}`, group: 'Problems', label: `Open problem: ${p.title}`,
            icon: p.is_completed ? CircleCheck : Circle, done: p.is_completed,
            keywords: `${p.difficulty || ''} ${p.is_completed ? 'solved done' : 'pending todo'}`,
            badge: p.difficulty, hint: 'Open', run: () => navigate(`problems/${p.id}`),
        }));

        return {
            nav,
            actions: actions.map((a) => ({ ...a, group: 'Actions' })),
            probs,
        };
    }, [isDark, toggleTheme, toast, paused, problems]);

    // Filtered, ranked, grouped list
    const { groups, flat } = useMemo(() => {
        const q = query.trim().toLowerCase();
        let items;
        if (!q) {
            const pending = commands.probs.filter((p) => !p.done).slice(0, 5).map((p) => ({ ...p, group: 'Pending problems' }));
            items = [...commands.nav, ...commands.actions, ...pending];
        } else {
            const words = q.split(/\s+/).filter(Boolean);
            items = [...commands.nav, ...commands.actions, ...commands.probs]
                .map((c, i) => ({ c, i, s: score(c, words, q) }))
                .filter((x) => x.s >= 0)
                .sort((a, b) => a.s - b.s || a.i - b.i)
                .map((x) => x.c);
        }
        // Group in order of first appearance so best matches stay on top.
        const map = new Map();
        for (const it of items) {
            if (!map.has(it.group)) map.set(it.group, []);
            map.get(it.group).push(it);
        }
        const grouped = [...map.entries()].map(([name, list]) => ({ name, list }));
        return { groups: grouped, flat: grouped.flatMap((g) => g.list) };
    }, [commands, query]);

    const selIndex = flat.length ? Math.min(sel, flat.length - 1) : -1;
    const optId = (i) => `${uid}-opt-${i}`;

    useEffect(() => {
        if (!open || selIndex < 0) return;
        listRef.current?.querySelector(`[data-index="${selIndex}"]`)?.scrollIntoView({ block: 'nearest' });
    }, [open, selIndex]);

    const runCommand = useCallback(async (cmd) => {
        if (!cmd || running) return;
        if (!cmd.async) {
            setOpen(false);
            try { cmd.run(); } catch (e) { toast(e.message || 'Something went wrong', 'error'); }
            return;
        }
        setRunning(cmd.id);
        try {
            await cmd.run();
            setOpen(false);
        } catch (e) {
            if (e?.name !== 'AbortError') toast(e.message || 'Something went wrong', 'error');
        } finally {
            setRunning(null);
        }
    }, [running, toast]);

    const onKeyDown = (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            close();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (flat.length) setSel((selIndex + 1) % flat.length);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (flat.length) setSel((selIndex - 1 + flat.length) % flat.length);
        } else if (e.key === 'Home' && flat.length) {
            e.preventDefault();
            setSel(0);
        } else if (e.key === 'End' && flat.length) {
            e.preventDefault();
            setSel(flat.length - 1);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selIndex >= 0) runCommand(flat[selIndex]);
        } else if (e.key === 'Tab') {
            e.preventDefault(); // keep focus trapped in the input
        }
    };

    if (!open) return null;

    const listboxId = `${uid}-listbox`;
    let idx = -1;

    return (
        <div className="fixed inset-0 z-[80] flex items-start justify-center px-2 sm:px-4 pt-3 sm:pt-[12vh]">
            <div
                className="absolute inset-0 bg-black/40 backdrop-blur-sm animate-fade"
                onClick={close}
                aria-hidden
            />
            <div
                role="dialog"
                aria-modal="true"
                aria-label="Command palette"
                className="card relative w-full sm:max-w-xl overflow-hidden shadow-2xl animate-rise flex flex-col max-h-[calc(100dvh-1.5rem)] sm:max-h-[70vh]"
            >
                <div className="flex items-center gap-3 px-4 border-b border-line">
                    <Search className="h-5 w-5 text-subtle shrink-0" aria-hidden />
                    <input
                        ref={inputRef}
                        autoFocus
                        value={query}
                        onChange={(e) => { setQuery(e.target.value); setSel(0); }}
                        onKeyDown={onKeyDown}
                        placeholder="Type a command or search problems…"
                        className="flex-1 min-w-0 h-14 bg-transparent text-base sm:text-[15px] text-fg placeholder:text-subtle outline-none"
                        role="combobox"
                        aria-expanded="true"
                        aria-controls={listboxId}
                        aria-autocomplete="list"
                        aria-activedescendant={selIndex >= 0 ? optId(selIndex) : undefined}
                        autoComplete="off"
                        autoCorrect="off"
                        spellCheck={false}
                    />
                    <button
                        type="button"
                        onClick={close}
                        className="shrink-0 font-mono text-[10.5px] text-subtle border border-line rounded-md px-1.5 py-0.5 hover:text-fg hover:border-line-strong transition-colors"
                        aria-label="Close command palette"
                    >
                        esc
                    </button>
                </div>

                <div
                    ref={listRef}
                    id={listboxId}
                    role="listbox"
                    aria-label="Commands"
                    className="flex-1 overflow-y-auto overscroll-contain p-2"
                >
                    {flat.length === 0 ? (
                        <div className="py-10 text-center animate-fade">
                            <p className="text-sm font-medium">No results</p>
                            <p className="text-[13px] text-subtle mt-1">Nothing matches “{query.trim()}”.</p>
                        </div>
                    ) : groups.map((g) => (
                        <div key={g.name} role="group" aria-labelledby={`${uid}-g-${g.name}`} className="mb-1 last:mb-0">
                            <div id={`${uid}-g-${g.name}`} className="eyebrow px-2.5 pt-2 pb-1.5">{g.name}</div>
                            {g.list.map((cmd) => {
                                idx += 1;
                                const i = idx;
                                const active = i === selIndex;
                                const isRunning = running === cmd.id;
                                const Icon = cmd.icon;
                                return (
                                    <div
                                        key={`${g.name}-${cmd.id}`}
                                        id={optId(i)}
                                        data-index={i}
                                        role="option"
                                        aria-selected={active}
                                        aria-busy={isRunning || undefined}
                                        onMouseMove={() => { if (sel !== i) setSel(i); }}
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={() => runCommand(cmd)}
                                        className={cx(
                                            'relative flex items-center gap-3 rounded-xl pl-3 pr-2.5 h-11 cursor-pointer select-none transition-colors',
                                            active ? 'bg-surface-2 text-fg' : 'text-muted',
                                            running && !isRunning && 'opacity-50',
                                        )}
                                    >
                                        <span
                                            aria-hidden
                                            className={cx(
                                                'absolute left-0 top-2 bottom-2 w-[3px] rounded-full transition-colors',
                                                active ? 'bg-accent' : 'bg-transparent',
                                            )}
                                        />
                                        <span
                                            className={cx(
                                                'grid place-items-center h-7 w-7 rounded-lg border shrink-0 transition-colors',
                                                active ? 'bg-accent-soft border-accent/30 text-accent' : 'bg-surface-2 border-line text-subtle',
                                            )}
                                        >
                                            {isRunning ? <Spinner className="h-3.5 w-3.5" /> : <Icon className={cx('h-3.5 w-3.5', cmd.done && 'text-ok')} aria-hidden />}
                                        </span>
                                        <span className={cx('flex-1 min-w-0 truncate text-sm', active ? 'font-medium' : '')}>
                                            {cmd.label}
                                        </span>
                                        {cmd.badge && (
                                            <span className={cx('badge shrink-0', DIFF[cmd.badge] || 'text-muted bg-surface-2')}>{cmd.badge}</span>
                                        )}
                                        <span className="shrink-0 flex items-center gap-1.5 text-[11.5px] text-subtle">
                                            {isRunning ? (
                                                <span className="text-accent font-medium">{cmd.runningHint || 'Working…'}</span>
                                            ) : active ? (
                                                <>
                                                    <span className="hidden sm:inline">{cmd.hint}</span>
                                                    <kbd className="grid place-items-center h-5 w-5 rounded border border-line bg-surface text-muted">
                                                        <CornerDownLeft className="h-3 w-3" aria-hidden />
                                                    </kbd>
                                                </>
                                            ) : null}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    ))}
                </div>

                <div className="flex items-center justify-between gap-3 px-4 h-10 border-t border-line text-[11.5px] text-subtle bg-surface">
                    <span className="truncate">
                        <kbd className="font-mono">↑↓</kbd> navigate · <kbd className="font-mono">↵</kbd> run · <kbd className="font-mono">esc</kbd> close
                    </span>
                    {running ? (
                        <span className="flex items-center gap-1.5 text-accent shrink-0"><Spinner className="h-3 w-3" /> Running</span>
                    ) : (
                        <span className="hidden sm:inline shrink-0 font-mono">{/Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K'}</span>
                    )}
                </div>
            </div>
        </div>
    );
}
