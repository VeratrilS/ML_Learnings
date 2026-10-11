import { Fragment, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { Keyboard, X } from 'lucide-react';
import { formatKeys, listShortcuts, registerShortcut, subscribeShortcuts } from '../lib/shortcuts';

// Shortcuts handled by their own listeners elsewhere (App, CommandPalette, PlanCard, Flashcards, dialogs).
// Each `keys` entry is a kbd combo (array of chips) or a plain separator string.
const BUILT_IN = [
    { group: 'Navigation', description: 'Switch section (nav order)', keys: [['1'], '–', ['8']] },
    { group: 'Navigation', description: 'Command palette', keys: [['Ctrl', 'K'], 'or', ['⌘', 'K']] },
    { group: 'Navigation', description: 'Command palette (search)', keys: [['/']] },
    { group: 'Today', description: 'Add a task', keys: [['N']] },
    { group: 'Flashcards', description: 'Flip card', keys: [['Space']] },
    { group: 'Flashcards', description: 'Grade card', keys: [['1'], '–', ['4']] },
    { group: 'General', description: 'Close dialog / palette', keys: [['Esc']] },
];

const GROUP_ORDER = ['General', 'Navigation', 'Go to', 'Actions', 'Today', 'Flashcards'];

function Kbd({ children }) {
    return (
        <kbd className="inline-flex items-center justify-center min-w-6 h-6 px-1.5 rounded-md border border-line-strong border-b-2 bg-surface-2 font-mono text-[11px] font-semibold leading-none text-fg">
            {children}
        </kbd>
    );
}

function Keys({ parts }) {
    return (
        <span className="flex items-center gap-1 shrink-0">
            {parts.map((p, i) => (
                <Fragment key={i}>
                    {typeof p === 'string'
                        ? <span className="text-[11px] text-subtle px-0.5">{p}</span>
                        : p.map((k, j) => (
                            <Fragment key={j}>
                                {j > 0 && <span className="text-[11px] text-subtle">+</span>}
                                <Kbd>{k}</Kbd>
                            </Fragment>
                        ))}
                </Fragment>
            ))}
        </span>
    );
}

// [['G'], ['P']] -> [['G'], 'then', ['P']]
const withThen = (steps) => steps.flatMap((s, i) => (i ? ['then', s] : [s]));

export default function ShortcutsOverlay() {
    const [open, setOpen] = useState(false);
    const registered = useSyncExternalStore(subscribeShortcuts, listShortcuts, listShortcuts);
    const closeRef = useRef(null);
    const titleId = useId();

    useEffect(() => registerShortcut({
        keys: 'shift+?',
        description: 'Show keyboard shortcuts',
        group: 'General',
        global: true,
        handler: () => setOpen((o) => !o),
    }), []);

    // Lets other UI (e.g. the command palette) open the cheat-sheet.
    useEffect(() => {
        const onOpen = () => setOpen(true);
        window.addEventListener('open-shortcuts', onOpen);
        return () => window.removeEventListener('open-shortcuts', onOpen);
    }, []);

    useEffect(() => {
        if (!open) return;
        const onKey = (e) => {
            if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setOpen(false); }
        };
        document.addEventListener('keydown', onKey);
        const prevOverflow = document.body.style.overflow;
        const prevFocus = document.activeElement;
        document.body.style.overflow = 'hidden';
        closeRef.current?.focus();
        return () => {
            document.removeEventListener('keydown', onKey);
            document.body.style.overflow = prevOverflow;
            if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus();
        };
    }, [open]);

    const groups = useMemo(() => {
        const map = new Map();
        const add = (group, item) => {
            if (!map.has(group)) map.set(group, []);
            map.get(group).push(item);
        };
        registered.forEach((s) => add(s.group, { description: s.description, keys: withThen(formatKeys(s.keys)) }));
        BUILT_IN.forEach((s) => add(s.group, s));
        const rank = (g) => (GROUP_ORDER.includes(g) ? GROUP_ORDER.indexOf(g) : GROUP_ORDER.length);
        return [...map.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
    }, [registered]);

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-80 grid place-items-center p-4">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-fade" onClick={() => setOpen(false)} />
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                className="relative w-full max-w-3xl max-h-[85dvh] overflow-y-auto rounded-2xl border border-line bg-surface shadow-2xl animate-rise"
            >
                <header className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-line bg-surface px-5 py-3.5">
                    <div className="flex items-center gap-2.5 min-w-0">
                        <div className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line text-muted shrink-0">
                            <Keyboard className="h-4 w-4" aria-hidden />
                        </div>
                        <div className="min-w-0">
                            <h2 id={titleId} className="text-[15px] font-semibold tracking-tight">Keyboard shortcuts</h2>
                            <p className="text-xs text-subtle truncate">Ignored while typing. Press <Kbd>?</Kbd> to toggle.</p>
                        </div>
                    </div>
                    <button ref={closeRef} type="button" onClick={() => setOpen(false)} className="btn btn-ghost btn-icon" aria-label="Close">
                        <X className="h-4 w-4" />
                    </button>
                </header>
                <div className="px-5 py-4 sm:columns-2 sm:gap-8">
                    {groups.map(([group, items]) => (
                        <section key={group} className="break-inside-avoid mb-5">
                            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-subtle mb-1.5">{group}</h3>
                            <ul className="divide-y divide-line">
                                {items.map((it, i) => (
                                    <li key={`${it.description}-${i}`} className="flex items-center justify-between gap-3 py-1.5">
                                        <span className="text-[13px] text-muted min-w-0 truncate">{it.description}</span>
                                        <Keys parts={it.keys} />
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ))}
                </div>
            </div>
        </div>
    );
}
