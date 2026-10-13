import { useEffect, useId, useRef, useState } from 'react';
import {
    ChevronLeft, ChevronRight, Copy, ExternalLink, Flag, Footprints, History, Lightbulb, LifeBuoy,
    MessageSquareQuote, Pause, Play, RotateCcw, Wind,
} from 'lucide-react';
import { useApi, useLocalStorage } from '../lib/hooks';
import { Button, Card, CardHeader, DifficultyBadge, Segmented, cx, useToast } from '../components/ui';

const TICK = 200;
const OTHER = '__other';
const MAX_SESSIONS = 20;
const DURATIONS = [
    { value: 30, label: '30s' },
    { value: 60, label: '60s' },
    { value: 90, label: '90s' },
];
const PATTERNS = ['Sorting?', 'Two pointers?', 'Hashing?', 'BFS/DFS?', 'DP?', 'Binary search?', 'Heap?', 'Prefix sums?'];

const STEPS = [
    {
        key: 'breathe',
        title: 'Breathe',
        icon: Wind,
        prompt: 'One slow breath: in for 4, out for 6. Drop your shoulders. You are not stuck, you just have not started yet.',
        say: "I'm going to think out loud.",
    },
    {
        key: 'restate',
        title: 'Restate',
        icon: MessageSquareQuote,
        prompt: 'Rewrite the problem in one sentence. Then note the input, the output, and how big n can get.',
        say: 'So if I understand it right, we need to … and n can be up to about 10^5?',
        field: { name: 'restate', label: 'The problem in one sentence + input/output sizes', placeholder: 'Given n ≤ 10^5 integers, return the length of …' },
    },
    {
        key: 'know',
        title: 'One thing I know',
        icon: Lightbulb,
        prompt: 'Name the smallest thing you know is true. Could a pattern fit? Tap any that might.',
        say: 'One thing I notice is … which makes me think of a hash map.',
        chips: true,
        field: { name: 'fact', label: 'The smallest true fact', placeholder: 'The array is sorted / I need pairs that sum to k / …', rows: 2 },
    },
    {
        key: 'example',
        title: 'Tiny example',
        icon: Footprints,
        prompt: 'Work one small example by hand, 3 to 5 elements. Watch what your hands do: that is the algorithm.',
        say: 'Let me walk through a small example to make sure I understand.',
        field: { name: 'example', label: 'Your example, worked by hand', placeholder: '[2, 7, 11, 15], k = 9 → 2 + 7 = 9 → answer (0, 1)' },
    },
    {
        key: 'brute',
        title: 'Brute force first',
        icon: Flag,
        prompt: 'Describe the naive solution and its time and space complexity. A working slow answer beats a silent fast one.',
        say: 'Let me start with a brute-force approach and then optimise.',
        field: { name: 'brute', label: 'Naive solution + complexity', placeholder: 'Try every pair with two loops: O(n²) time, O(1) space.' },
        after: true,
    },
];
const LAST = STEPS.length - 1;
const EMPTY_NOTES = { restate: '', fact: '', patterns: [], example: '', brute: '', optimise: '' };

const isTyping = (el) => !!el && (/^(input|textarea|select)$/i.test(el.tagName) || el.isContentEditable);
// Mouse/touch clicks on the script controls shouldn't keep focus, so Space keeps meaning pause.
const keepFocus = (e) => e.preventDefault();
const fmtWhen = (iso) => {
    try {
        return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
};

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            ta.remove();
            return ok;
        } catch { return false; }
    }
}

function buildNotes(problem, notes) {
    const line = (label, v) => `${label}: ${v?.trim() ? v.trim() : '-'}`;
    const out = [`Freeze Breaker · ${new Date().toLocaleString()}`];
    if (problem?.title) out.push(`Problem: ${problem.title}${problem.link ? ` (${problem.link})` : ''}`);
    out.push(
        '',
        line('1. Restate', notes.restate),
        line('2. One thing I know', [notes.patterns.join(', '), notes.fact.trim()].filter(Boolean).join(' · ')),
        line('3. Tiny example', notes.example),
        line('4. Brute force', notes.brute),
        line('5. One optimisation', notes.optimise),
    );
    return out.join('\n');
}

function Ring({ fraction, children, breathing }) {
    const size = 200;
    const stroke = 10;
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const pct = Math.max(0, Math.min(1, fraction));
    return (
        <div className="relative h-44 w-44 sm:h-52 sm:w-52 shrink-0">
            <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full -rotate-90" aria-hidden>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
                <circle
                    cx={size / 2} cy={size / 2} r={r} fill="none"
                    stroke="var(--accent)" strokeWidth={stroke} strokeLinecap="round"
                    strokeDasharray={c} strokeDashoffset={c * (1 - pct)}
                    style={{ transition: `stroke-dashoffset ${TICK}ms linear` }}
                />
            </svg>
            {breathing && (
                <div aria-hidden className="absolute inset-[18%] rounded-full bg-accent-soft animate-glow" />
            )}
            <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
        </div>
    );
}

function ProblemLink({ problem, className }) {
    if (!problem?.title) return null;
    return (
        <div className={cx('flex flex-wrap items-center gap-x-2 gap-y-1 min-w-0 text-sm', className)}>
            <span className="text-subtle shrink-0">Problem</span>
            {problem.link ? (
                <a
                    href={problem.link}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 min-w-0 font-medium wrap-break-word hover:text-accent transition-colors rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                    <span className="min-w-0 wrap-break-word">{problem.title}</span>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span className="sr-only">(opens in a new tab)</span>
                </a>
            ) : (
                <span className="font-medium min-w-0 wrap-break-word">{problem.title}</span>
            )}
            {problem.difficulty && <DifficultyBadge value={problem.difficulty} />}
        </div>
    );
}

function Sessions({ sessions }) {
    const n = sessions.length;
    const count = n >= MAX_SESSIONS ? `${MAX_SESSIONS}+` : String(n);
    return (
        <Card className="card-pad min-w-0">
            <CardHeader
                title={n ? `You've broken ${count} ${n === 1 ? 'freeze' : 'freezes'}` : 'No freezes broken yet'}
                subtitle={n ? 'Every one is proof the next blank is temporary' : 'The first one is the hardest. It gets faster.'}
                icon={History}
                className={n ? undefined : 'mb-0'}
            />
            {n > 0 && (
                <ul className="divide-y divide-line">
                    {sessions.slice(0, 5).map((s, i) => (
                        <li key={`${s.date}-${i}`} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0 text-sm">
                            <div className="min-w-0">
                                <div className="font-medium truncate">{s.problem || 'Untitled problem'}</div>
                                <div className="text-xs text-subtle tabular-nums">{fmtWhen(s.date)}</div>
                            </div>
                            <span className="badge shrink-0 tabular-nums text-muted bg-surface-2">{s.steps}/{STEPS.length} steps</span>
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    );
}

/** Freeze Breaker (beta): a ~60-second guided script for when the mind blanks mid-problem. */
export default function Unstuck() {
    const toast = useToast();
    const uid = useId();
    const pending = useApi('/logs?type=leetcode', { select: (d) => (d.data || []).filter((l) => !l.is_completed) });
    const [sessions, setSessions] = useLocalStorage('unstuck:sessions', []);
    const [duration, setDuration] = useLocalStorage('unstuck:duration', 60);
    const perStep = ((DURATIONS.some((d) => d.value === duration) ? duration : 60) * 1000) / STEPS.length;

    const [phase, setPhase] = useState('intro'); // intro | script | done
    const [pick, setPick] = useState('');
    const [custom, setCustom] = useState('');
    const [notes, setNotes] = useState(EMPTY_NOTES);
    const [step, setStep] = useState(0);
    const [reached, setReached] = useState(0);
    const [paused, setPaused] = useState(false);
    const [timeUp, setTimeUp] = useState(false);
    const [left, setLeft] = useState(perStep);
    const leftRef = useRef(perStep);
    const stepHeading = useRef(null);
    const doneHeading = useRef(null);

    const list = Array.isArray(pending.data) ? pending.data : [];
    const picked = list.find((p) => String(p.id) === pick);
    const problem = pick === OTHER
        ? (custom.trim() ? { title: custom.trim() } : null)
        : picked ? { title: picked.title, link: picked.link, difficulty: picked.difficulty } : null;

    const goTo = (i) => {
        const next = Math.max(0, Math.min(LAST, i));
        setStep(next);
        setReached((r) => Math.max(r, next));
        leftRef.current = perStep;
        setLeft(perStep);
        setTimeUp(false);
    };
    const start = () => {
        setNotes(EMPTY_NOTES);
        setReached(0);
        setPaused(false);
        goTo(0);
        setPhase('script');
    };
    const finish = () => {
        const steps = Math.min(STEPS.length, reached + 1);
        setSessions((s) => [
            { date: new Date().toISOString(), problem: problem?.title || '', steps },
            ...(Array.isArray(s) ? s : []),
        ].slice(0, MAX_SESSIONS));
        setPaused(false);
        setPhase('done');
    };
    const next = () => (step < LAST ? goTo(step + 1) : finish());
    const back = () => step > 0 && goTo(step - 1);
    const restart = () => { setPaused(false); goTo(0); };
    const togglePause = () => { if (!timeUp) setPaused((p) => !p); };

    // Countdown. On timeout auto-advance, unless he's mid-sentence in a text box (or on the last step).
    useEffect(() => {
        if (phase !== 'script' || paused || timeUp) return;
        let last = performance.now();
        const id = setInterval(() => {
            const now = performance.now();
            leftRef.current = Math.max(0, leftRef.current - (now - last));
            last = now;
            setLeft(leftRef.current);
            if (leftRef.current > 0) return;
            clearInterval(id);
            if (step < LAST && !isTyping(document.activeElement)) goTo(step + 1);
            else setTimeUp(true);
        }, TICK);
        return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [phase, paused, timeUp, step]);

    // Space = pause/resume, ←/→ = back/next; ignored while typing.
    useEffect(() => {
        if (phase !== 'script') return;
        const onKey = (e) => {
            if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
            if (e.key === ' ' || e.code === 'Space') {
                if (e.target?.closest?.('button, a, [role="checkbox"]')) return; // let native activation run
                e.preventDefault();
                togglePause();
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                next();
            } else if (e.key === 'ArrowLeft') {
                e.preventDefault();
                back();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    });

    // Move focus to the new screen's heading when the phase changes (not on every step).
    useEffect(() => {
        if (phase === 'script') stepHeading.current?.focus({ preventScroll: true });
        if (phase === 'done') doneHeading.current?.focus();
    }, [phase]);

    const setField = (name) => (e) => setNotes((n) => ({ ...n, [name]: e.target.value }));
    const togglePattern = (p) => setNotes((n) => ({
        ...n,
        patterns: n.patterns.includes(p) ? n.patterns.filter((x) => x !== p) : [...n.patterns, p],
    }));
    const blurOnEscape = (e) => { if (e.key === 'Escape') e.currentTarget.blur(); };

    const copyNotes = async () => {
        const ok = await copyText(buildNotes(problem, notes));
        toast(ok ? 'Notes copied' : 'Could not copy. Select the text and copy it manually.', ok ? 'success' : 'error');
    };
    const startAgain = () => { setNotes(EMPTY_NOTES); setPhase('intro'); };

    const s = STEPS[step];
    const secs = Math.ceil(left / 1000);
    const totalLeft = Math.ceil(((LAST - step) * perStep + left) / 1000);
    const announce = phase === 'script'
        ? `Step ${step + 1} of ${STEPS.length}: ${s.title}.${paused ? ' Paused.' : ''}${timeUp ? " Time's up." : ''}`
        : phase === 'done' ? 'Script complete. Your notes are below.' : '';

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="animate-rise min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Freeze Breaker</h1>
                    <span className="badge text-accent bg-accent-soft">Beta</span>
                </div>
                <p className="text-sm text-muted mt-1">Blank on a problem? Breathe, then follow the script. 60 seconds.</p>
            </header>

            <p className="sr-only" aria-live="polite" aria-atomic="true">{announce}</p>

            {phase === 'intro' && (
                <div className="grid gap-4 lg:gap-6 lg:grid-cols-5 items-start animate-rise">
                    <Card className="card-pad min-w-0 lg:col-span-3 hero-accent">
                        <CardHeader title="Before you start" subtitle="Both optional. The script works without them." icon={LifeBuoy} />
                        <div className="space-y-4">
                            <div className="min-w-0">
                                <label htmlFor={`${uid}-pick`} className="label">Which problem?</label>
                                <select
                                    id={`${uid}-pick`}
                                    className="input"
                                    value={pick}
                                    onChange={(e) => setPick(e.target.value)}
                                >
                                    <option value="">No specific problem</option>
                                    {pending.loading && !list.length && <option disabled value="__loading">Loading your pending problems…</option>}
                                    {list.length > 0 && (
                                        <optgroup label={`Unsolved LeetCode (${list.length})`}>
                                            {list.map((p) => (
                                                <option key={p.id} value={String(p.id)}>
                                                    {p.title}{p.difficulty ? ` · ${p.difficulty}` : ''}
                                                </option>
                                            ))}
                                        </optgroup>
                                    )}
                                    <option value={OTHER}>Something else (type it)</option>
                                </select>
                                {pending.error && !list.length && (
                                    <p className="mt-1.5 text-xs text-subtle">Couldn't load your problem list. You can still type one.</p>
                                )}
                                {pick === OTHER && (
                                    <div className="mt-2">
                                        <label htmlFor={`${uid}-custom`} className="sr-only">Problem title</label>
                                        <input
                                            id={`${uid}-custom`}
                                            className="input"
                                            value={custom}
                                            maxLength={200}
                                            onChange={(e) => setCustom(e.target.value)}
                                            placeholder="e.g. Longest substring without repeating characters"
                                        />
                                    </div>
                                )}
                                {problem && <ProblemLink problem={problem} className="mt-2.5" />}
                            </div>

                            <div role="group" aria-labelledby={`${uid}-dur`}>
                                <div id={`${uid}-dur`} className="label">Script length</div>
                                <Segmented options={DURATIONS} value={duration} onChange={setDuration} />
                                <p className="mt-1.5 text-xs text-subtle tabular-nums">
                                    {STEPS.length} steps · {Math.round(perStep / 1000)}s each
                                </p>
                            </div>

                            <ol className="grid gap-1.5 text-sm text-muted">
                                {STEPS.map((st, i) => (
                                    <li key={st.key} className="flex items-center gap-2 min-w-0">
                                        <span className="grid place-items-center h-5 w-5 rounded-full bg-surface-2 border border-line text-[11px] font-semibold text-fg tabular-nums shrink-0">{i + 1}</span>
                                        <span className="truncate">{st.title}</span>
                                    </li>
                                ))}
                            </ol>

                            <Button variant="primary" size="lg" icon={Play} onClick={start} className="w-full sm:w-auto">
                                Start the script
                            </Button>
                        </div>
                    </Card>
                    <div className="lg:col-span-2 min-w-0">
                        <Sessions sessions={Array.isArray(sessions) ? sessions : []} />
                    </div>
                </div>
            )}

            {phase === 'script' && (
                <Card className="card-pad min-w-0 animate-rise">
                    <div className="flex items-center gap-1.5" aria-hidden>
                        {STEPS.map((st, i) => (
                            <div
                                key={st.key}
                                className={cx(
                                    'h-1.5 flex-1 rounded-full transition-colors',
                                    i < step ? 'bg-accent' : i === step ? 'bg-accent/50' : 'bg-surface-3',
                                )}
                            />
                        ))}
                    </div>

                    <div className="mt-5 flex flex-col sm:flex-row items-center sm:items-start gap-5 sm:gap-7">
                        <div className="flex flex-col items-center gap-2 shrink-0">
                            <Ring fraction={left / perStep} breathing={step === 0 && !paused && !timeUp}>
                                <div role="timer" aria-label={`${secs} seconds left in this step`}>
                                    <div className="text-5xl sm:text-6xl font-bold tracking-tight tabular-nums leading-none">{secs}</div>
                                    <div className={cx('mt-1.5 text-xs font-medium', paused || timeUp ? 'text-accent' : 'text-subtle')}>
                                        {timeUp ? "Time's up" : paused ? 'Paused' : 'seconds'}
                                    </div>
                                </div>
                            </Ring>
                            <div className="text-xs text-subtle tabular-nums">{totalLeft}s left in the script</div>
                        </div>

                        <div className="min-w-0 w-full flex-1">
                            <ProblemLink problem={problem} className="mb-3" />
                            <div className="eyebrow">Step {step + 1} of {STEPS.length}</div>
                            <h2
                                ref={stepHeading}
                                tabIndex={-1}
                                className="mt-1 flex items-center gap-2 text-xl sm:text-2xl font-bold tracking-tight focus:outline-none"
                            >
                                <s.icon className="h-5 w-5 text-accent shrink-0" aria-hidden />
                                <span className="min-w-0">{s.title}</span>
                            </h2>
                            <p className="mt-2 text-sm text-muted leading-relaxed">{s.prompt}</p>

                            <figure className="mt-3 rounded-xl border border-accent/25 bg-accent-soft px-3.5 py-2.5">
                                <figcaption className="eyebrow text-accent flex items-center gap-1.5">
                                    <MessageSquareQuote className="h-3.5 w-3.5 shrink-0" aria-hidden /> Say it aloud
                                </figcaption>
                                <blockquote className="mt-1 text-[15px] font-medium leading-snug wrap-break-word">“{s.say}”</blockquote>
                            </figure>

                            {s.chips && (
                                <div className="mt-4" role="group" aria-label="Pattern hints">
                                    <div className="label">Could it be…</div>
                                    <div className="flex flex-wrap gap-1.5">
                                        {PATTERNS.map((p) => {
                                            const on = notes.patterns.includes(p);
                                            return (
                                                <button
                                                    key={p}
                                                    type="button"
                                                    aria-pressed={on}
                                                    onClick={() => togglePattern(p)}
                                                    className={cx('chip focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent', on && 'chip-on')}
                                                >
                                                    {p}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}

                            {s.field && (
                                <div className="mt-4">
                                    <label htmlFor={`${uid}-${s.field.name}`} className="label">{s.field.label}</label>
                                    <textarea
                                        key={s.field.name}
                                        id={`${uid}-${s.field.name}`}
                                        className="input h-auto py-2.5 leading-relaxed resize-y"
                                        rows={s.field.rows || 3}
                                        maxLength={2000}
                                        value={notes[s.field.name]}
                                        onChange={setField(s.field.name)}
                                        onKeyDown={blurOnEscape}
                                        placeholder={s.field.placeholder}
                                    />
                                </div>
                            )}

                            {s.after && (
                                <div className="mt-4 rounded-xl border border-line bg-surface-2 px-3.5 py-3">
                                    <div className="text-sm font-semibold">Now optimise one step</div>
                                    <p className="mt-0.5 text-xs text-muted">What work repeats? Could a hash map, sorting, two pointers or a prefix sum remove it?</p>
                                    <label htmlFor={`${uid}-optimise`} className="sr-only">One optimisation</label>
                                    <textarea
                                        id={`${uid}-optimise`}
                                        className="input h-auto mt-2 py-2.5 leading-relaxed resize-y"
                                        rows={2}
                                        maxLength={2000}
                                        value={notes.optimise}
                                        onChange={setField('optimise')}
                                        onKeyDown={blurOnEscape}
                                        placeholder="Store seen values in a hash map → O(n)."
                                    />
                                </div>
                            )}
                        </div>
                    </div>

                    {timeUp && (
                        <p className="mt-4 text-sm text-accent font-medium text-center sm:text-left">
                            {step === LAST ? "Time's up. Finish when you're ready." : "Time's up. Hit Next when you've finished typing."}
                        </p>
                    )}

                    <div className="mt-5 pt-4 border-t border-line flex flex-wrap items-center justify-center sm:justify-between gap-2">
                        <div className="flex flex-wrap items-center justify-center gap-2">
                            <Button icon={ChevronLeft} onMouseDown={keepFocus} onClick={back} disabled={step === 0} aria-label="Back" title="Back (←)">
                                <span className="hidden min-[400px]:inline">Back</span>
                            </Button>
                            <Button
                                icon={paused ? Play : Pause}
                                onMouseDown={keepFocus}
                                onClick={togglePause}
                                disabled={timeUp}
                                aria-pressed={paused}
                                title={paused ? 'Resume (Space)' : 'Pause (Space)'}
                                className="min-w-[96px]"
                            >
                                {paused ? 'Resume' : 'Pause'}
                            </Button>
                            <Button
                                variant="primary"
                                onMouseDown={keepFocus}
                                onClick={next}
                                title={step === LAST ? 'Finish' : 'Next (→)'}
                                className={cx(timeUp && 'animate-glow')}
                            >
                                {step === LAST ? 'Finish' : 'Next'}
                                {step === LAST ? <Flag className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
                            </Button>
                            <Button variant="ghost" size="icon" icon={RotateCcw} onMouseDown={keepFocus} onClick={restart} aria-label="Restart the script" title="Restart" />
                        </div>
                        {step < LAST && (
                            <Button variant="ghost" size="sm" onClick={finish}>I'm moving, finish</Button>
                        )}
                    </div>
                    <p className="hidden sm:block mt-3 text-[11px] text-subtle">
                        Space pause · ← → move between steps · Esc leaves a text box
                    </p>
                </Card>
            )}

            {phase === 'done' && (
                <div className="grid gap-4 lg:gap-6 lg:grid-cols-5 items-start animate-rise">
                    <Card className="card-pad min-w-0 lg:col-span-3">
                        <h2 ref={doneHeading} tabIndex={-1} className="text-xl font-bold tracking-tight focus:outline-none">
                            You're moving again.
                        </h2>
                        <p className="mt-1 text-sm text-muted">Here's what you got down. Keep going from the brute force.</p>
                        <ProblemLink problem={problem} className="mt-3" />

                        <dl className="mt-4 divide-y divide-line">
                            {[
                                ['Restate', notes.restate],
                                ['One thing I know', [notes.patterns.join(', '), notes.fact.trim()].filter(Boolean).join(' · ')],
                                ['Tiny example', notes.example],
                                ['Brute force', notes.brute],
                                ['One optimisation', notes.optimise],
                            ].map(([label, v]) => (
                                <div key={label} className="py-2.5 first:pt-0 last:pb-0">
                                    <dt className="eyebrow">{label}</dt>
                                    <dd className={cx('mt-0.5 text-sm whitespace-pre-wrap wrap-break-word', v?.trim() ? 'text-fg' : 'text-subtle')}>
                                        {v?.trim() || 'Nothing written'}
                                    </dd>
                                </div>
                            ))}
                        </dl>

                        <div className="mt-5 flex flex-wrap gap-2">
                            <Button variant="primary" icon={Copy} onClick={copyNotes} className="flex-1 sm:flex-none">Copy notes</Button>
                            <Button icon={RotateCcw} onClick={startAgain} className="flex-1 sm:flex-none">Start again</Button>
                        </div>
                    </Card>
                    <div className="lg:col-span-2 min-w-0">
                        <Sessions sessions={Array.isArray(sessions) ? sessions : []} />
                    </div>
                </div>
            )}
        </div>
    );
}
