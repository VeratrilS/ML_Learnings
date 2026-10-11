// Procedural ambience via WebAudio: no audio assets. One sound plays at a time,
// cross-faded on switch. API: start(kind, volume?), stop(), setVolume(0..1), chime().

export const AMBIENTS = [
    { id: 'brown', label: 'Brown noise' },
    { id: 'rain', label: 'Rain' },
    { id: 'cafe', label: 'Café' },
    { id: 'gym', label: 'Gym' },
];

let ctx = null;
let master = null;
let active = null; // { kind, out: GainNode, teardown() }
let volume = 0.5;
const buffers = {};

function audio() {
    if (!ctx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return null;
        ctx = new AC();
        master = ctx.createGain();
        master.gain.value = curve(volume);
        master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume().catch(() => { /* needs a user gesture */ });
    return ctx;
}

const curve = (v) => Math.max(0, Math.min(1, v)) ** 2 * 0.9;

function noise(type) {
    if (buffers[type]) return buffers[type];
    const len = ctx.sampleRate * 4;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    let last = 0;
    let b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < len; i++) {
        const w = Math.random() * 2 - 1;
        if (type === 'brown') {
            last = (last + 0.02 * w) / 1.02;
            d[i] = last * 3.5;
        } else if (type === 'pink') {
            b0 = 0.99765 * b0 + w * 0.099046;
            b1 = 0.963 * b1 + w * 0.2965164;
            b2 = 0.57 * b2 + w * 1.0526913;
            d[i] = (b0 + b1 + b2 + w * 0.1848) * 0.2;
        } else d[i] = w;
    }
    return (buffers[type] = buf);
}

function loop(type, dest, gain = 1) {
    const src = ctx.createBufferSource();
    src.buffer = noise(type);
    src.loop = true;
    src.loopStart = Math.random() * 3;
    const g = ctx.createGain();
    g.gain.value = gain;
    src.connect(g).connect(dest);
    src.start(0, src.loopStart);
    return { src, g };
}

function filter(type, freq, q = 0.7) {
    const f = ctx.createBiquadFilter();
    f.type = type;
    f.frequency.value = freq;
    f.Q.value = q;
    return f;
}

// Fire `fn` at random intervals in [min, max] ms until cleared.
function every(min, max, fn, timers) {
    const tick = () => { fn(); timers.id = setTimeout(tick, min + Math.random() * (max - min)); };
    timers.id = setTimeout(tick, min + Math.random() * (max - min));
}

// A short decaying sine (clinks, thumps, chime notes).
function blip(dest, { freq, to, dur, gain, type = 'sine', at = 0 }) {
    const t = ctx.currentTime + at;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(dest);
    o.start(t);
    o.stop(t + dur + 0.05);
}

// Short filtered noise burst (raindrops).
function burst(dest, { freq, dur, gain }) {
    const t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = noise('white');
    const f = filter('bandpass', freq, 4);
    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f).connect(g).connect(dest);
    src.start(t, Math.random() * 3, dur + 0.02);
}

const BUILD = {
    brown(out) {
        const lp = filter('lowpass', 900);
        lp.connect(out);
        return [loop('brown', lp, 0.9)];
    },
    rain(out, timers) {
        const hiss = filter('bandpass', 2500, 0.4);
        hiss.connect(out);
        const body = filter('lowpass', 500);
        body.connect(out);
        const drops = ctx.createGain();
        drops.gain.value = 0.5;
        drops.connect(out);
        every(25, 90, () => burst(drops, { freq: 1800 + Math.random() * 4500, dur: 0.02 + Math.random() * 0.04, gain: 0.05 + Math.random() * 0.15 }), timers);
        return [loop('pink', hiss, 0.55), loop('brown', body, 0.5)];
    },
    cafe(out, timers) {
        // Murmur: band-limited noise with wandering loudness, like overlapping voices.
        const voice = filter('bandpass', 600, 0.9);
        const level = ctx.createGain();
        level.gain.value = 0.5;
        voice.connect(level).connect(out);
        const room = filter('lowpass', 300);
        room.connect(out);
        const clinks = ctx.createGain();
        clinks.gain.value = 0.12;
        clinks.connect(out);
        const t1 = {}, t2 = {};
        every(180, 420, () => {
            level.gain.setTargetAtTime(0.25 + Math.random() * 0.5, ctx.currentTime, 0.12);
            voice.frequency.setTargetAtTime(400 + Math.random() * 600, ctx.currentTime, 0.2);
        }, t1);
        every(1800, 7000, () => {
            const f = 2400 + Math.random() * 2400;
            blip(clinks, { freq: f, dur: 0.35, gain: 0.5 });
            blip(clinks, { freq: f * 1.51, dur: 0.25, gain: 0.25 });
            if (Math.random() < 0.4) blip(clinks, { freq: f * 0.9, dur: 0.3, gain: 0.35, at: 0.09 });
        }, t2);
        timers.extra = [t1, t2];
        return [loop('pink', voice, 0.9), loop('brown', room, 0.6)];
    },
    gym(out, timers) {
        const lp = filter('lowpass', 140);
        lp.connect(out);
        const hum = ctx.createOscillator();
        const humG = ctx.createGain();
        hum.frequency.value = 55;
        humG.gain.value = 0.04;
        hum.connect(humG).connect(out);
        hum.start();
        const hits = ctx.createGain();
        hits.gain.value = 0.6;
        hits.connect(out);
        every(3000, 9000, () => {
            blip(hits, { freq: 110, to: 38, dur: 0.45, gain: 0.8 }); // dropped weight thump
            if (Math.random() < 0.35) blip(hits, { freq: 740 + Math.random() * 300, dur: 0.18, gain: 0.05, type: 'triangle', at: 0.04 }); // plate clank
        }, timers);
        return [loop('brown', lp, 1), { src: hum }];
    },
};

/** Start (or switch to) an ambience with a fade-in. Must follow a user gesture at least once. */
export function start(kind, vol) {
    if (vol != null) setVolume(vol);
    if (active?.kind === kind) return;
    if (!BUILD[kind] || !audio()) return;
    stop();
    const out = ctx.createGain();
    out.gain.value = 0.0001;
    out.connect(master);
    const timers = {};
    const nodes = BUILD[kind](out, timers);
    out.gain.setTargetAtTime(1, ctx.currentTime, 0.4); // ~1.2s fade-in
    active = {
        kind,
        out,
        teardown() {
            [timers, ...(timers.extra || [])].forEach((t) => clearTimeout(t.id));
            nodes.forEach((n) => { try { n.src.stop(); } catch { /* already stopped */ } });
            out.disconnect();
        },
    };
}

/** Fade out and release the current ambience. */
export function stop() {
    if (!active || !ctx) return;
    const { out, teardown } = active;
    active = null;
    out.gain.cancelScheduledValues(ctx.currentTime);
    out.gain.setTargetAtTime(0.0001, ctx.currentTime, 0.25);
    // Timers keep firing during the fade; harmless since `out` fades to silence.
    setTimeout(teardown, 1200);
}

export function setVolume(v) {
    volume = Math.max(0, Math.min(1, Number(v) || 0));
    if (master) master.gain.setTargetAtTime(curve(volume), ctx.currentTime, 0.08);
}

export const current = () => active?.kind ?? null;

/** Soft three-note completion chime (independent of ambient volume). */
export function chime() {
    if (!audio()) return;
    const g = ctx.createGain();
    g.gain.value = 0.35;
    g.connect(ctx.destination);
    [[659.25, 0], [880, 0.18], [1318.5, 0.36]].forEach(([freq, at]) => blip(g, { freq, dur: 1.4, gain: 0.5, at }));
    setTimeout(() => g.disconnect(), 2500);
}
