// Tiny WebAudio synth for the Gym: no audio files, everything is generated.
//   play('jab')   short punch, < 80 ms
//   play('combo') three quick jabs
//   play('bell')  boxing bell, ding-ding
// localStorage `sfx:on`: 'off' | 'big' (default: only bell + combo) | 'all'.

const KEY = 'sfx:on';
const BIG = new Set(['bell', 'combo']);
export const SFX_MODES = ['off', 'big', 'all'];

export function getMode() {
    try {
        const v = localStorage.getItem(KEY);
        if (v === 'off' || v === 'big' || v === 'all') return v;
        if (v === '0' || v === 'false') return 'off';
        if (v === '1' || v === 'true') return 'all';
    } catch { /* storage unavailable */ }
    return 'big';
}

export function setMode(mode) {
    const m = SFX_MODES.includes(mode) ? mode : 'big';
    try { localStorage.setItem(KEY, m); } catch { /* storage unavailable */ }
    try { window.dispatchEvent(new CustomEvent('sfx-mode', { detail: m })); } catch { /* no window */ }
    return m;
}

export const enabled = (name) => {
    const m = getMode();
    return m === 'all' || (m === 'big' && BIG.has(name));
};

// ---------------- audio graph ----------------
let ctx = null;
let noiseBuf = null;

function audio(create = true) {
    if (typeof window === 'undefined') return null;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!ctx && create) {
        try { ctx = new AC(); } catch { return null; }
    }
    if (ctx?.state === 'suspended') ctx.resume().catch(() => {});
    return ctx;
}

// Browsers only start audio after a user gesture: warm the context up on the first one.
if (typeof window !== 'undefined') {
    const unlock = () => {
        if (getMode() === 'off') return;
        const ac = audio();
        if (ac && ac.state === 'running') {
            window.removeEventListener('pointerdown', unlock);
            window.removeEventListener('keydown', unlock);
        }
    };
    window.addEventListener('pointerdown', unlock, { passive: true });
    window.addEventListener('keydown', unlock);
}

function noise(ac) {
    if (noiseBuf && noiseBuf.sampleRate === ac.sampleRate) return noiseBuf;
    const len = Math.floor(ac.sampleRate * 0.06);
    noiseBuf = ac.createBuffer(1, len, ac.sampleRate);
    const ch = noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) ch[i] = Math.random() * 2 - 1;
    return noiseBuf;
}

function env(gain, t, peak, attack, end) {
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(peak, t + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + end);
}

// Low thump + a bandpassed noise snap. Whole hit is ~72 ms.
function jab(ac, out, t) {
    const o = ac.createOscillator();
    const g = ac.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(190, t);
    o.frequency.exponentialRampToValueAtTime(55, t + 0.06);
    env(g, t, 0.9, 0.004, 0.068);
    o.connect(g).connect(out);
    o.start(t);
    o.stop(t + 0.072);

    const n = ac.createBufferSource();
    n.buffer = noise(ac);
    const f = ac.createBiquadFilter();
    f.type = 'bandpass';
    f.frequency.value = 1700;
    f.Q.value = 0.9;
    const ng = ac.createGain();
    env(ng, t, 0.55, 0.002, 0.04);
    n.connect(f).connect(ng).connect(out);
    n.start(t);
    n.stop(t + 0.045);
}

// One bell strike: inharmonic partials with long exponential decay.
const PARTIALS = [[1, 0.5, 1.5], [2.76, 0.22, 1.0], [5.4, 0.1, 0.55], [8.93, 0.05, 0.3]];
function strike(ac, out, t) {
    for (const [ratio, amp, dur] of PARTIALS) {
        const o = ac.createOscillator();
        const g = ac.createGain();
        o.type = 'sine';
        o.frequency.value = 830 * ratio;
        env(g, t, amp, 0.003, dur);
        o.connect(g).connect(out);
        o.start(t);
        o.stop(t + dur + 0.02);
    }
}

const SOUNDS = {
    jab: (ac, out, t) => jab(ac, out, t),
    combo: (ac, out, t) => { jab(ac, out, t); jab(ac, out, t + 0.11); jab(ac, out, t + 0.22); },
    bell: (ac, out, t) => { strike(ac, out, t); strike(ac, out, t + 0.34); },
};

/** Play a sound if the user's sfx mode allows it (`force` skips the check, e.g. a preview). */
export function play(name, { force = false } = {}) {
    const fn = SOUNDS[name];
    if (!fn || (!force && !enabled(name))) return false;
    const ac = audio();
    if (!ac) return false;
    try {
        const out = ac.createGain();
        out.gain.value = 0.35;
        out.connect(ac.destination);
        fn(ac, out, ac.currentTime + 0.01);
        setTimeout(() => { try { out.disconnect(); } catch { /* already gone */ } }, 2500);
        return true;
    } catch {
        return false;
    }
}

/** Vibrate (Android); silent no-op elsewhere or when sounds are off. */
export function haptic(ms = 20) {
    if (getMode() === 'off') return false;
    try { return typeof navigator !== 'undefined' && navigator.vibrate ? navigator.vibrate(ms) : false; }
    catch { return false; }
}
