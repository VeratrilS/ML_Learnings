// Global keyboard-shortcut registry.
//
//   const off = registerShortcut({ keys: 'g p', description: 'Go to problems', group: 'Go to', handler });
//   off(); // unregister
//
// `keys` is one combo ('f', 'shift+?', 'ctrl+k') or a two-step sequence ('g p') whose
// second key must follow within SEQ_TIMEOUT ms. Shortcuts are ignored while typing in
// inputs / textareas / selects / contenteditable, and while a modal dialog is open unless
// registered with `global: true`. A key that starts a sequence never also fires as a single.

const SEQ_TIMEOUT = 900;
const MOD_ORDER = ['ctrl', 'alt', 'meta', 'shift'];
const MOD_ALIASES = { control: 'ctrl', cmd: 'meta', command: 'meta', option: 'alt', opt: 'alt' };
const KEY_ALIASES = { space: ' ', spacebar: ' ', esc: 'escape', del: 'delete', return: 'enter' };
const MODIFIER_KEYS = new Set(['shift', 'control', 'alt', 'meta', 'os', 'altgraph', 'capslock']);

const registry = new Map();
const listeners = new Set();
let snapshot = [];
let nextId = 1;
let pending = null; // { combo, at }

const isTyping = (el) => !!el && (/^(input|textarea|select)$/i.test(el.tagName || '') || !!el.isContentEditable);

// Shift is implied by non-letter printable characters ('?', '!', ...), so drop it for matching.
function canonical(mods, key) {
    if (key.length === 1 && !/[a-z]/.test(key)) mods.delete('shift');
    return [...MOD_ORDER.filter((m) => mods.has(m)), key].join('+');
}

function parseCombo(str) {
    const raw = str.trim().toLowerCase();
    const parts = raw === '+' ? ['+'] : raw.split('+').filter(Boolean);
    let key = parts.pop() || '';
    key = KEY_ALIASES[key] ?? key;
    const mods = new Set(parts.map((m) => MOD_ALIASES[m] || m));
    return canonical(mods, key);
}

function eventCombo(e) {
    if (!e.key) return null;
    const key = e.key.toLowerCase();
    if (MODIFIER_KEYS.has(key)) return null;
    const mods = new Set();
    if (e.ctrlKey) mods.add('ctrl');
    if (e.altKey) mods.add('alt');
    if (e.metaKey) mods.add('meta');
    if (e.shiftKey) mods.add('shift');
    return canonical(mods, key);
}

function emit() {
    snapshot = [...registry.values()].map(({ id, keys, steps, description, group }) => ({ id, keys, steps, description, group }));
    listeners.forEach((fn) => fn());
}

function fire(entry, e) {
    e.preventDefault();
    e.stopPropagation();
    try {
        entry.handler(e);
    } catch (err) {
        console.error('[shortcuts]', entry.keys, err);
    }
}

function onKeyDown(e) {
    if (e.defaultPrevented || e.isComposing) return;
    if (isTyping(e.target) || isTyping(document.activeElement)) { pending = null; return; }
    const combo = eventCombo(e);
    if (!combo) return;
    if (combo === 'escape') { pending = null; return; }

    const modal = !!document.querySelector('[role="dialog"][aria-modal="true"]');
    const usable = [...registry.values()].filter((s) => !modal || s.global);
    const now = Date.now();

    if (pending && now - pending.at <= SEQ_TIMEOUT) {
        const first = pending.combo;
        pending = null;
        const hit = usable.find((s) => s.steps.length === 2 && s.steps[0] === first && s.steps[1] === combo);
        if (hit) return fire(hit, e);
        // Not a valid continuation: fall through and treat as a fresh key.
    } else {
        pending = null;
    }
    if (e.repeat) return;

    if (usable.some((s) => s.steps.length === 2 && s.steps[0] === combo)) {
        pending = { combo, at: now };
        return;
    }
    const single = usable.find((s) => s.steps.length === 1 && s.steps[0] === combo);
    if (single) fire(single, e);
}

function install() {
    if (typeof window === 'undefined') return;
    // Survive HMR re-evaluation: drop any listener left by a previous module instance.
    if (window.__dailyShortcutsListener) window.removeEventListener('keydown', window.__dailyShortcutsListener, true);
    window.__dailyShortcutsListener = onKeyDown;
    window.addEventListener('keydown', onKeyDown, true);
}

export function registerShortcut({ keys, description = '', group = 'General', handler, global = false }) {
    if (!keys || typeof handler !== 'function') throw new Error('registerShortcut needs keys and a handler');
    const steps = keys.trim().split(/\s+/).slice(0, 2).map(parseCombo);
    const id = nextId++;
    registry.set(id, { id, keys, steps, description, group, handler, global });
    emit();
    return () => {
        if (registry.delete(id)) emit();
    };
}

export function listShortcuts() {
    return snapshot;
}

// For useSyncExternalStore(subscribeShortcuts, listShortcuts).
export function subscribeShortcuts(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
}

const PRETTY = {
    ' ': 'Space', escape: 'Esc', enter: 'Enter', arrowup: '↑', arrowdown: '↓', arrowleft: '←', arrowright: '→',
    ctrl: 'Ctrl', alt: 'Alt', meta: '⌘', shift: 'Shift', tab: 'Tab', backspace: '⌫',
};

// 'g p' -> [['G'], ['P']], 'ctrl+k' -> [['Ctrl', 'K']]  (for rendering <kbd> chips)
export function formatKeys(keys) {
    return keys.trim().split(/\s+/).map((step) => parseCombo(step).split(/\+(?!$)/).map((k) => PRETTY[k] || (k.length === 1 ? k.toUpperCase() : k)));
}

// ---------------- Defaults ----------------
const GOTO = [
    ['t', 'today', 'Today'],
    ['p', 'problems', 'DSA problems'],
    ['s', 'study', 'Study'],
    ['l', 'learn', 'Learn'],
    ['c', 'cf', 'Codeforces'],
    ['i', 'insights', 'Insights'],
    ['y', 'gym', 'Gym'],
    ['n', 'notes', 'Notes'],
    ['o', 'placements', 'Placements'],
    ['f', 'cards', 'Flashcards'],
    ['a', 'aptitude', 'Aptitude'],
    ['r', 'review', 'Review'],
    ['m', 'mistakes', 'Mistakes'],
    ['q', 'sql', 'SQL'],
    ['k', 'interview', 'Interview'],
    ['e', 'oa', 'Online assessments'],
    [',', 'settings', 'Settings'],
];

install();

GOTO.forEach(([key, id, label]) => registerShortcut({
    keys: `g ${key}`,
    description: `Go to ${label}`,
    group: 'Go to',
    handler: () => { window.location.hash = `#/${id}`; },
}));

registerShortcut({
    keys: 'f',
    description: 'Open focus mode',
    group: 'Actions',
    handler: () => window.dispatchEvent(new CustomEvent('open-focus-mode')),
});

registerShortcut({
    keys: 'c',
    description: 'Quick capture',
    group: 'Actions',
    handler: () => window.dispatchEvent(new CustomEvent('open-capture')),
});
