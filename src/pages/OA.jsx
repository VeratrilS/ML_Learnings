import { useEffect, useMemo, useRef, useState } from 'react';
import {
    AlarmClock, ArrowLeft, BadgeCheck, CalendarPlus, ChevronRight, CircleAlert, ExternalLink, Flag,
    History, Hourglass, Lightbulb, Play, Plus, Target, Timer, Trophy, X,
} from 'lucide-react';
import {
    Button, Card, CardHeader, DifficultyBadge, Empty, ProgressBar, RatingBadge, Segmented, Skeleton, Spinner,
    useToast, cx,
} from '../components/ui';
import { api } from '../lib/api';
import { timeAgo, useApi, useLocalStorage } from '../lib/hooks';

const GRACE_MIN = 5;
const OUTCOMES = [
    { value: 'solved', label: 'Solved' },
    { value: 'partial', label: 'Partial' },
    { value: 'unsolved', label: 'Unsolved' },
];
const LETTERS = 'ABCDEF';
const CF_RATINGS = Array.from({ length: 28 }, (_, i) => 800 + i * 100);
const CUSTOM_DURATIONS = [30, 45, 60, 90, 120];
const PLATFORM_NAME = { leetcode: 'LeetCode', codeforces: 'Codeforces' };

const pad = (n) => String(n).padStart(2, '0');
function fmtClock(sec) {
    const s = Math.max(0, Math.floor(sec));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${pad(m)}:${pad(s % 60)}`;
}
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const problemPoints = (p) => (p.rating ? Math.max(100, Math.round(p.rating / 5)) : ({ Easy: 100, Medium: 200, Hard: 300 }[p.difficulty] ?? 200));

function beep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [0, 0.3, 0.6].forEach((t) => {
            const o = ctx.createOscillator();
            const g = ctx.createGain();
            o.frequency.value = 660;
            g.gain.setValueAtTime(0.0001, ctx.currentTime + t);
            g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + t + 0.02);
            g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.24);
            o.connect(g).connect(ctx.destination);
            o.start(ctx.currentTime + t);
            o.stop(ctx.currentTime + t + 0.26);
        });
    } catch { /* audio unavailable */ }
}

function Level({ p }) {
    return p.rating ? <RatingBadge rating={p.rating} /> : <DifficultyBadge value={p.difficulty} />;
}

function MixBadges({ preset }) {
    if (!preset.mix) return <span className="text-xs text-subtle">Your choice</span>;
    return (
        <div className="flex flex-wrap gap-1">
            {preset.mix.map((m, i) => (typeof m === 'number'
                ? <RatingBadge key={i} rating={m} />
                : <DifficultyBadge key={i} value={m} />))}
        </div>
    );
}

// ---------------- Lobby ----------------
function PresetCard({ preset, onStart, starting }) {
    const [duration, setDuration] = useState(preset.duration_min);
    const Icon = preset.platform === 'codeforces' ? Trophy : preset.key === 'lc-quick' ? Hourglass : Target;
    return (
        <Card className="card-pad flex flex-col gap-3">
            <div className="flex items-start gap-3">
                <div className="grid place-items-center h-9 w-9 rounded-xl bg-accent-soft text-accent shrink-0">
                    <Icon className="h-[18px] w-[18px]" aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                    <h3 className="text-[15px] font-semibold tracking-tight">{preset.label}</h3>
                    <p className="text-[13px] text-subtle">{preset.blurb}</p>
                </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
                <MixBadges preset={preset} />
                {preset.durations.length > 1 ? (
                    <Segmented
                        value={duration}
                        onChange={setDuration}
                        options={preset.durations.map((d) => ({ value: d, label: `${d}m` }))}
                    />
                ) : (
                    <span className="text-xs text-muted font-medium inline-flex items-center gap-1">
                        <Timer className="h-3.5 w-3.5" aria-hidden /> {duration} min
                    </span>
                )}
            </div>
            {preset.theta && (
                <p className="text-xs text-subtle">Climbs from your practice rating ({preset.theta}).</p>
            )}
            <Button
                variant="primary"
                icon={Play}
                className="w-full mt-auto"
                loading={starting === preset.key}
                disabled={!!starting}
                onClick={() => onStart({ preset: preset.key, duration_min: duration })}
            >
                Start
            </Button>
        </Card>
    );
}

function CustomCard({ onStart, starting }) {
    const [cfg, setCfg] = useLocalStorage('oa.custom', {
        platform: 'leetcode', difficulties: ['Medium', 'Medium'], ratings: [1200, 1400], duration: 60,
    });
    const isLc = cfg.platform === 'leetcode';
    const items = isLc ? cfg.difficulties : cfg.ratings;
    const set = (patch) => setCfg({ ...cfg, ...patch });
    const remove = (i) => set(isLc
        ? { difficulties: cfg.difficulties.filter((_, j) => j !== i) }
        : { ratings: cfg.ratings.filter((_, j) => j !== i) });
    const [newRating, setNewRating] = useState(1600);
    const canAdd = items.length < (isLc ? 5 : 6);

    return (
        <Card className="card-pad flex flex-col gap-3">
            <div className="flex items-start gap-3">
                <div className="grid place-items-center h-9 w-9 rounded-xl bg-surface-2 border border-line text-muted shrink-0">
                    <Plus className="h-[18px] w-[18px]" aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                    <h3 className="text-[15px] font-semibold tracking-tight">Custom</h3>
                    <p className="text-[13px] text-subtle">Pick the platform, problems and time.</p>
                </div>
            </div>
            <Segmented
                className="self-start"
                value={cfg.platform}
                onChange={(platform) => set({ platform })}
                options={[{ value: 'leetcode', label: 'LeetCode' }, { value: 'codeforces', label: 'Codeforces' }]}
            />
            <div className="flex flex-wrap items-center gap-1.5 min-h-8">
                {items.length === 0 && <span className="text-xs text-subtle">Add at least one problem.</span>}
                {items.map((v, i) => (
                    <button
                        key={`${v}-${i}`}
                        type="button"
                        onClick={() => remove(i)}
                        className="inline-flex items-center gap-1 rounded-lg pl-0.5 pr-1 py-0.5 hover:bg-surface-2 transition-colors"
                        aria-label={`Remove ${v}`}
                    >
                        {isLc ? <DifficultyBadge value={v} /> : <RatingBadge rating={v} />}
                        <X className="h-3 w-3 text-subtle" aria-hidden />
                    </button>
                ))}
            </div>
            {canAdd && (
                <div className="flex flex-wrap items-center gap-1.5">
                    {isLc ? ['Easy', 'Medium', 'Hard'].map((d) => (
                        <button key={d} type="button" className="chip" onClick={() => set({ difficulties: [...cfg.difficulties, d] })}>
                            <Plus className="h-3 w-3" aria-hidden /> {d}
                        </button>
                    )) : (
                        <>
                            <select
                                className="input h-8 w-28 text-[13px]"
                                value={newRating}
                                onChange={(e) => setNewRating(Number(e.target.value))}
                                aria-label="Rating to add"
                            >
                                {CF_RATINGS.map((r) => <option key={r} value={r}>{r}</option>)}
                            </select>
                            <Button size="sm" icon={Plus} onClick={() => set({ ratings: [...cfg.ratings, newRating].sort((a, b) => a - b) })}>
                                Add
                            </Button>
                        </>
                    )}
                </div>
            )}
            <div className="flex items-center justify-between gap-2">
                <label htmlFor="oa-custom-duration" className="text-[13px] text-muted font-medium">Duration</label>
                <select
                    id="oa-custom-duration"
                    className="input h-8 w-28 text-[13px]"
                    value={cfg.duration}
                    onChange={(e) => set({ duration: Number(e.target.value) })}
                >
                    {CUSTOM_DURATIONS.map((d) => <option key={d} value={d}>{d} min</option>)}
                </select>
            </div>
            <Button
                variant="primary"
                icon={Play}
                className="w-full mt-auto"
                loading={starting === 'custom'}
                disabled={!!starting || items.length === 0}
                onClick={() => onStart({
                    preset: 'custom', platform: cfg.platform, duration_min: cfg.duration,
                    ...(isLc ? { difficulties: cfg.difficulties } : { ratings: cfg.ratings }),
                })}
            >
                Start
            </Button>
        </Card>
    );
}

function Stat({ label, value, hint }) {
    return (
        <div className="rounded-xl bg-surface-2 border border-line px-3 py-2.5 min-w-0">
            <div className="eyebrow truncate">{label}</div>
            <div className="text-xl font-semibold tracking-tight tabular-nums mt-0.5">{value}</div>
            {hint && <div className="text-[11.5px] text-subtle truncate">{hint}</div>}
        </div>
    );
}

function StatsCard({ stats }) {
    const weak = (stats.by_topic || []).filter((t) => t.rate < 1).slice(0, 4);
    return (
        <Card className="card-pad">
            <CardHeader title="Your OA record" subtitle="Finished attempts only" icon={Trophy} />
            <div className="grid grid-cols-3 gap-2">
                <Stat label="Attempts" value={stats.attempts} hint={stats.abandoned ? `${stats.abandoned} abandoned` : 'finished'} />
                <Stat label="Avg score" value={stats.avg_score} hint={`${stats.avg_pct}% of max`} />
                <Stat label="Solved in time" value={pct(stats.solve_rate)} hint={`${stats.solved}/${stats.problems} problems`} />
            </div>
            {weak.length > 0 && (
                <div className="mt-4 space-y-2.5">
                    <p className="eyebrow">Weakest under pressure</p>
                    {weak.map((t) => (
                        <div key={t.topic} className="space-y-1">
                            <div className="flex items-center justify-between gap-2 text-[13px]">
                                <span className="truncate">{t.topic}</span>
                                <span className="text-subtle tabular-nums shrink-0">{t.solved}/{t.attempted}</span>
                            </div>
                            <ProgressBar value={t.rate * 100} color={t.rate < 0.5 ? 'var(--danger)' : 'var(--accent)'} />
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}

function HistoryCard({ history, onOpen }) {
    return (
        <Card className="card-pad">
            <CardHeader title="History" subtitle={history.length ? `${history.length} recent` : 'Nothing yet'} icon={History} />
            {history.length === 0 ? (
                <Empty icon={AlarmClock} title="No attempts yet">Start a set above. The clock is real.</Empty>
            ) : (
                <ul className="-mx-2">
                    {history.map((a) => {
                        const solved = Object.values(a.results || {}).filter((r) => r === 'solved').length;
                        const abandoned = a.status === 'abandoned';
                        return (
                            <li key={a.id}>
                                <button
                                    type="button"
                                    onClick={() => onOpen(a)}
                                    className="row-hover w-full flex items-center gap-3 rounded-xl px-2 py-2.5 text-left"
                                >
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-1.5 text-sm font-medium">
                                            <span className="truncate">{a.label}</span>
                                            {a.auto_verified && <BadgeCheck className="h-3.5 w-3.5 text-ok shrink-0" aria-label="Auto-verified" />}
                                        </div>
                                        <div className="text-xs text-subtle truncate">
                                            {timeAgo(a.started_at)} · {a.duration_min} min · {abandoned ? 'abandoned' : `${solved}/${a.problems.length} solved`}
                                        </div>
                                    </div>
                                    {abandoned ? (
                                        <span className="badge bg-surface-2 text-subtle">Abandoned</span>
                                    ) : (
                                        <div className="text-right shrink-0">
                                            <div className="text-sm font-semibold tabular-nums">{a.score}</div>
                                            <div className="text-[11px] text-subtle tabular-nums">/ {a.max_score}</div>
                                        </div>
                                    )}
                                    <ChevronRight className="h-4 w-4 text-subtle shrink-0" aria-hidden />
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </Card>
    );
}

// ---------------- Live attempt ----------------
function useNow(skew, active = true) {
    const [now, setNow] = useState(() => Date.now() + skew);
    useEffect(() => {
        if (!active) return undefined;
        const t = setInterval(() => setNow(Date.now() + skew), 500);
        return () => clearInterval(t);
    }, [skew, active]);
    return now;
}

function LiveAttempt({ attempt, skew, onFinished, onAbandoned }) {
    const toast = useToast();
    const [marks, setMarks] = useLocalStorage(`oa.marks.${attempt.id}`, {});
    const [busy, setBusy] = useState(null);
    const [timeUpOpen, setTimeUpOpen] = useState(false);
    const now = useNow(skew);
    const startMs = new Date(attempt.started_at).getTime();
    const endMs = new Date(attempt.ends_at).getTime();
    const left = (endMs - now) / 1000;
    const total = attempt.duration_min * 60;
    const timeUp = left <= 0;
    const graceLeft = (endMs + GRACE_MIN * 60000 - now) / 1000;
    const baseTitle = useRef(document.title);
    const alerted = useRef(false);

    useEffect(() => {
        const title = baseTitle.current;
        document.title = timeUp ? "Time's up · OA" : `${fmtClock(left)} · OA`;
        return () => { document.title = title; };
    }, [left, timeUp]);

    useEffect(() => {
        if (!timeUp || alerted.current) return;
        alerted.current = true;
        // Only make noise if the buzzer went off while the page was open (not on a stale reload).
        if (left > -10) beep();
        setTimeUpOpen(true);
    }, [timeUp, left]);

    const finish = async (confirmEarly = true) => {
        if (confirmEarly && !timeUp && left > 60 && !window.confirm('Finish now? The clock still has time left.')) return;
        setBusy('finish');
        try {
            const res = await api(`/oa/${attempt.id}/finish`, { method: 'POST', body: { results: marks } });
            try { localStorage.removeItem(`oa.marks.${attempt.id}`); } catch { /* storage unavailable */ }
            if (res.verify_error) toast(res.verify_error, 'info');
            onFinished(res.data, res.verify_error);
        } catch (e) {
            toast(e.message, 'error');
            setBusy(null);
        }
    };

    const abandon = async () => {
        if (!window.confirm('Abandon this attempt? It won’t count toward your stats.')) return;
        setBusy('abandon');
        try {
            await api(`/oa/${attempt.id}/abandon`, { method: 'POST' });
            try { localStorage.removeItem(`oa.marks.${attempt.id}`); } catch { /* storage unavailable */ }
            onAbandoned();
        } catch (e) {
            toast(e.message, 'error');
            setBusy(null);
        }
    };

    const tone = timeUp || left < 120 ? 'text-danger' : left < 600 ? 'text-accent' : 'text-fg';
    const barColor = timeUp || left < 120 ? 'var(--danger)' : left < 600 ? 'var(--accent)' : 'var(--fg)';
    const elapsedPct = Math.min(100, Math.max(0, ((now - startMs) / 1000 / total) * 100));
    const marked = attempt.problems.filter((p) => marks[p.id] === 'solved').length;

    return (
        <div className="space-y-4 sm:space-y-5">
            <Card className={cx('card-pad hero-accent', timeUp && 'border-danger/40')}>
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                    <div className="flex-1 min-w-0">
                        <p className="eyebrow flex items-center gap-1.5">
                            <span className={cx('h-1.5 w-1.5 rounded-full', timeUp ? 'bg-danger' : 'bg-accent animate-glow')} aria-hidden />
                            {timeUp ? "Time's up" : 'In progress'} · {attempt.label}
                        </p>
                        <div
                            className={cx('font-mono font-semibold tracking-tight tabular-nums leading-none mt-2 text-[56px] sm:text-[72px] transition-colors', tone)}
                            role="timer"
                            aria-live="off"
                        >
                            {fmtClock(left)}
                        </div>
                        <p className="text-[13px] text-subtle mt-2">
                            {timeUp
                                ? graceLeft > 0
                                    ? `Submissions in the next ${fmtClock(graceLeft)} still count for verification.`
                                    : 'Finish to verify and score this attempt.'
                                : `${attempt.duration_min} min · ends ${new Date(endMs - skew).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`}
                        </p>
                    </div>
                    <div className="flex sm:flex-col gap-2 sm:w-44 shrink-0">
                        <Button variant="primary" icon={Flag} className="flex-1 sm:flex-none" loading={busy === 'finish'} disabled={!!busy} onClick={() => finish()}>
                            Finish &amp; verify
                        </Button>
                        <Button variant="ghost" className="btn-danger" loading={busy === 'abandon'} disabled={!!busy} onClick={abandon}>
                            Abandon
                        </Button>
                    </div>
                </div>
                <ProgressBar value={elapsedPct} className="mt-4" color={barColor} />
            </Card>

            {timeUpOpen && (
                <div role="alertdialog" aria-labelledby="oa-timeup" className="card card-pad border-danger/40 animate-pop flex flex-col sm:flex-row sm:items-center gap-3">
                    <AlarmClock className="h-5 w-5 text-danger shrink-0" aria-hidden />
                    <div className="flex-1 min-w-0">
                        <p id="oa-timeup" className="text-sm font-semibold">Time&apos;s up. Pens down.</p>
                        <p className="text-[13px] text-subtle">Mark what you got, then finish. We&apos;ll check {PLATFORM_NAME[attempt.platform]} for accepted submissions.</p>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onClick={() => setTimeUpOpen(false)}>Mark first</Button>
                        <Button variant="primary" size="sm" icon={Flag} loading={busy === 'finish'} disabled={!!busy} onClick={() => finish(false)}>
                            Finish now
                        </Button>
                    </div>
                </div>
            )}

            <Card className="card-pad">
                <CardHeader
                    title="Problems"
                    subtitle={`${marked}/${attempt.problems.length} marked solved · open each in a new tab`}
                    icon={Target}
                />
                <ol className="space-y-2.5">
                    {attempt.problems.map((p, i) => (
                        <li key={p.id} className="rounded-xl border border-line bg-surface-2/60 p-3">
                            <div className="flex items-start gap-3">
                                <span className="grid place-items-center h-7 w-7 rounded-lg bg-surface border border-line font-mono text-[13px] font-semibold shrink-0">
                                    {LETTERS[i]}
                                </span>
                                <div className="min-w-0 flex-1">
                                    <p className="text-sm font-medium leading-snug break-words">{p.title}</p>
                                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                                        <Level p={p} />
                                        <span className="text-xs text-subtle truncate">{p.topic}</span>
                                        <span className="text-xs text-subtle tabular-nums">· {problemPoints(p)} pts</span>
                                    </div>
                                </div>
                                <a
                                    href={p.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="btn btn-secondary btn-sm shrink-0"
                                    aria-label={`Open ${p.title}`}
                                >
                                    <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                                    <span className="hidden sm:inline">Open</span>
                                </a>
                            </div>
                            <Segmented
                                className="mt-3 w-full sm:w-auto [&>button]:flex-1 sm:[&>button]:flex-none"
                                value={marks[p.id] || 'unsolved'}
                                onChange={(v) => setMarks({ ...marks, [p.id]: v })}
                                options={OUTCOMES}
                            />
                        </li>
                    ))}
                </ol>
                <p className="text-xs text-subtle mt-3 flex items-start gap-1.5">
                    <BadgeCheck className="h-3.5 w-3.5 text-ok shrink-0 mt-px" aria-hidden />
                    Accepted submissions on {PLATFORM_NAME[attempt.platform]} during the attempt are verified automatically; your marks fill in the rest.
                </p>
            </Card>
        </div>
    );
}

// ---------------- Results ----------------
const OUTCOME_STYLE = {
    solved: 'text-ok bg-ok/10',
    partial: 'text-medium bg-medium/10',
    unsolved: 'text-danger bg-danger/10',
};

function buildSuggestions(attempt, stats) {
    const out = [];
    const results = attempt.results || {};
    const used = attempt.ended_at ? (new Date(attempt.ended_at) - new Date(attempt.started_at)) / 60000 : attempt.duration_min;
    const solved = attempt.problems.filter((p) => results[p.id] === 'solved');
    const hardest = attempt.problems.reduce((m, p) => Math.max(m, p.rating || 0), 0);
    attempt.problems.forEach((p) => {
        const r = results[p.id];
        const isHard = p.difficulty === 'Hard' || (p.rating && p.rating === hardest && attempt.problems.length > 1);
        if (r === 'unsolved' && isHard) {
            out.push({ key: `rev-${p.id}`, text: `${p.title} beat you. Study the editorial, then re-solve it cold in a few days.`, problem: p });
        } else if (r === 'partial') {
            out.push({ key: `part-${p.id}`, text: `${p.title}: partial usually means a missed edge case or TLE. Re-solve from scratch tomorrow.`, problem: p });
        } else if (r === 'unsolved') {
            out.push({ key: `uns-${p.id}`, text: `${p.title} (${p.topic}) should be within reach. Drill a couple more ${p.topic} problems.`, problem: p });
        }
    });
    const selfOnly = solved.filter((p) => !p.verified);
    if (selfOnly.length) {
        out.push({ key: 'verify', text: `${selfOnly.length} solve${selfOnly.length > 1 ? 's were' : ' was'} self-reported. Submit on ${PLATFORM_NAME[attempt.platform]} during the attempt so it verifies next time.` });
    }
    if (solved.length === attempt.problems.length && used < attempt.duration_min * 0.6) {
        out.push({ key: 'harder', text: `Cleared everything in ${Math.round(used)} min. Step up: try a harder preset or a shorter clock.` });
    }
    if (solved.length === 0) {
        out.push({ key: 'easier', text: 'Nothing landed this time. Warm up with the Quick Screen and focus on getting one clean AC fast.' });
    }
    const weak = (stats?.by_topic || []).find((t) => t.attempted >= 3 && t.rate < 0.5);
    if (weak) out.push({ key: 'weak', text: `${weak.topic} is your weakest OA topic (${weak.solved}/${weak.attempted}). Give it a focused session this week.` });
    return out;
}

function Results({ attempt, verifyError, stats, onBack }) {
    const toast = useToast();
    const [added, setAdded] = useState({});
    const results = attempt.results || {};
    const abandoned = attempt.status === 'abandoned';
    const ratio = attempt.max_score ? attempt.score / attempt.max_score : 0;
    const used = attempt.ended_at ? Math.round((new Date(attempt.ended_at) - new Date(attempt.started_at)) / 60000) : null;
    const suggestions = useMemo(() => (abandoned ? [] : buildSuggestions(attempt, stats)), [attempt, stats, abandoned]);
    const verifiedCount = attempt.problems.filter((p) => p.verified).length;

    const addToPlan = async (s) => {
        setAdded((a) => ({ ...a, [s.key]: 'busy' }));
        try {
            const p = s.problem;
            const level = p.difficulty || p.rating;
            await api('/todos', { method: 'POST', body: { text: `Revisit OA problem: ${p.title} (${level}, ${p.topic}) ${p.url}`.slice(0, 300) } });
            setAdded((a) => ({ ...a, [s.key]: 'done' }));
            toast("Added to today's plan");
        } catch (e) {
            setAdded((a) => ({ ...a, [s.key]: null }));
            toast(e.message, 'error');
        }
    };

    return (
        <div className="space-y-4 sm:space-y-5 animate-rise">
            <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={onBack} className="-ml-2">Back to lobby</Button>

            <Card className="card-pad hero-accent">
                <p className="eyebrow">{attempt.label} · {new Date(attempt.started_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</p>
                {abandoned ? (
                    <p className="text-2xl font-bold tracking-tight mt-2">Abandoned</p>
                ) : (
                    <div className="flex items-end gap-2 mt-2">
                        <span className={cx('text-5xl font-bold tracking-tight tabular-nums', ratio >= 0.7 ? 'text-ok' : ratio >= 0.4 ? 'text-accent' : 'text-danger')}>
                            {attempt.score}
                        </span>
                        <span className="text-lg text-subtle tabular-nums pb-1">/ {attempt.max_score}</span>
                    </div>
                )}
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[13px] text-muted">
                    {!abandoned && <span>{Math.round(ratio * 100)}% of max</span>}
                    {used != null && <span>{Math.min(used, 999)} of {attempt.duration_min} min used</span>}
                    {verifiedCount > 0 && (
                        <span className="inline-flex items-center gap-1 text-ok">
                            <BadgeCheck className="h-3.5 w-3.5" aria-hidden /> {verifiedCount} verified on {PLATFORM_NAME[attempt.platform]}
                        </span>
                    )}
                </div>
                {verifyError && (
                    <p className="mt-3 text-[13px] text-muted flex items-start gap-1.5">
                        <CircleAlert className="h-4 w-4 text-accent shrink-0 mt-px" aria-hidden /> {verifyError}
                    </p>
                )}
            </Card>

            <Card className="card-pad">
                <CardHeader title="Per problem" icon={Target} />
                <ul className="divide-y divide-line">
                    {attempt.problems.map((p, i) => {
                        const r = results[p.id] || 'unsolved';
                        return (
                            <li key={p.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                                <span className="font-mono text-[13px] font-semibold text-subtle w-4 shrink-0">{LETTERS[i]}</span>
                                <div className="min-w-0 flex-1">
                                    <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:text-accent transition-colors break-words">
                                        {p.title}
                                    </a>
                                    <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                                        <Level p={p} />
                                        <span className="text-xs text-subtle">{p.topic}</span>
                                        {p.verified && (
                                            <span className="badge text-ok bg-ok/10">
                                                <BadgeCheck className="h-3 w-3" aria-hidden />
                                                {p.solved_in_min != null ? `Verified · ${p.solved_in_min}m` : 'Verified'}
                                            </span>
                                        )}
                                    </div>
                                </div>
                                {!abandoned && <span className={cx('badge capitalize shrink-0', OUTCOME_STYLE[r])}>{r}</span>}
                            </li>
                        );
                    })}
                </ul>
            </Card>

            {suggestions.length > 0 && (
                <Card className="card-pad">
                    <CardHeader title="What to do next" icon={Lightbulb} />
                    <ul className="space-y-2.5">
                        {suggestions.map((s) => (
                            <li key={s.key} className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-xl bg-surface-2 border border-line px-3 py-2.5">
                                <p className="text-[13.5px] leading-snug flex-1">{s.text}</p>
                                {s.problem && (
                                    <Button
                                        size="sm"
                                        icon={added[s.key] === 'done' ? BadgeCheck : CalendarPlus}
                                        loading={added[s.key] === 'busy'}
                                        disabled={added[s.key] === 'done'}
                                        onClick={() => addToPlan(s)}
                                        className="self-start sm:self-auto shrink-0"
                                    >
                                        {added[s.key] === 'done' ? 'Added' : 'Add to plan'}
                                    </Button>
                                )}
                            </li>
                        ))}
                    </ul>
                </Card>
            )}
        </div>
    );
}

// ---------------- Page ----------------
export default function OA() {
    const toast = useToast();
    // Server clock offset, measured when the response lands, so the countdown survives skewed device clocks.
    const res = useApi('/oa', { select: (d) => ({ ...d, skew: d.now ? Date.parse(d.now) - Date.now() : 0 }) });
    const [starting, setStarting] = useState(null);
    const [view, setView] = useState(null); // { attempt, verifyError } when showing results
    const data = res.data?.data;
    const skew = Number.isFinite(res.data?.skew) ? res.data.skew : 0;

    const start = async (body) => {
        setStarting(body.preset);
        try {
            const r = await api('/oa/start', { method: 'POST', body });
            if (r.resumed) toast('You already have an attempt running. Picking it back up.', 'info');
            await res.reload({ silent: true });
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setStarting(null);
        }
    };

    const onFinished = async (attempt, verifyError) => {
        setView({ attempt, verifyError });
        window.scrollTo({ top: 0 });
        await res.reload({ silent: true });
    };

    const onAbandoned = async () => {
        toast('Attempt abandoned', 'info');
        await res.reload({ silent: true });
    };

    const header = (
        <header className="animate-rise">
            <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight flex items-center gap-2">
                <AlarmClock className="h-7 w-7 text-accent shrink-0" aria-hidden />
                OA Simulator
            </h1>
            <p className="text-sm text-muted mt-1">Timed sets that feel like the real thing.</p>
        </header>
    );

    if (res.loading && !data) {
        return (
            <div className="space-y-5">
                {header}
                <div className="grid sm:grid-cols-2 gap-3 sm:gap-4">
                    {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-44" />)}
                </div>
                <Skeleton className="h-40" />
            </div>
        );
    }

    if (res.error && !data) {
        return (
            <div className="space-y-5">
                {header}
                <Card className="card-pad">
                    <Empty icon={CircleAlert} title="Couldn't load the OA simulator" action={<Button onClick={() => res.reload()}>Retry</Button>}>
                        {res.error}
                    </Empty>
                </Card>
            </div>
        );
    }

    if (view) {
        return (
            <div className="space-y-5">
                {header}
                <Results attempt={view.attempt} verifyError={view.verifyError} stats={data?.stats} onBack={() => setView(null)} />
            </div>
        );
    }

    if (data?.active) {
        return (
            <div className="space-y-5">
                {header}
                <LiveAttempt
                    key={data.active.id}
                    attempt={data.active}
                    skew={skew}
                    onFinished={onFinished}
                    onAbandoned={onAbandoned}
                />
            </div>
        );
    }

    const presets = data?.presets || [];
    return (
        <div className="space-y-5 sm:space-y-6">
            {header}
            <section aria-labelledby="oa-presets" className="space-y-3">
                <div className="flex items-center justify-between">
                    <h2 id="oa-presets" className="eyebrow">Choose a set</h2>
                    {res.loading && <Spinner className="h-3.5 w-3.5 text-subtle" />}
                </div>
                <div className="grid sm:grid-cols-2 gap-3 sm:gap-4">
                    {presets.filter((p) => p.key !== 'custom').map((p) => (
                        <PresetCard key={p.key} preset={p} onStart={start} starting={starting} />
                    ))}
                    <CustomCard onStart={start} starting={starting} />
                </div>
            </section>
            <div className="grid lg:grid-cols-2 gap-4 items-start">
                {data?.stats && <StatsCard stats={data.stats} />}
                <HistoryCard history={data?.history || []} onOpen={(a) => setView({ attempt: a, verifyError: null })} />
            </div>
        </div>
    );
}
