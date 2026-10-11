import { useCallback, useEffect, useRef, useState } from 'react';
import {
    ArrowLeft, CheckCircle2, CircleAlert, CodeXml, ExternalLink, Flag, History, Lightbulb, ListChecks,
    Mic, MicOff, Network, RotateCcw, SendHorizontal, Sparkles, Timer, Trash2, Users, Volume2, VolumeX,
} from 'lucide-react';
import { Button, Card, Empty, ProgressBar, Segmented, Skeleton, Spinner, cx, useToast } from '../components/ui';
import Markdown from '../components/Markdown';
import { api, streamSSE } from '../lib/api';
import { navigate, timeAgo, useApi, useHashRoute, useLocalStorage } from '../lib/hooks';

const MODES = [
    {
        id: 'dsa', label: 'DSA', icon: CodeXml, meta: '~45 min · 1 problem',
        blurb: 'A LeetCode Medium, out loud: clarify → brute force → optimal → complexity → edge cases → dry run.',
    },
    {
        id: 'behavioral', label: 'Behavioral', icon: Users, meta: '~25 min · 2–3 questions',
        blurb: 'HR questions with STAR follow-ups that probe your own role, actions and measurable impact.',
    },
    {
        id: 'system_design', label: 'System Design', icon: Network, meta: '~40 min · 1 system',
        blurb: 'Fresher-level HLD: requirements, APIs, data model, scaling and trade-offs.',
    },
];
const MODE = Object.fromEntries(MODES.map((m) => [m.id, m]));

const VERDICT = {
    'strong hire': 'text-ok bg-ok/10',
    hire: 'text-easy bg-easy/10',
    'lean hire': 'text-medium bg-medium/10',
    'no hire': 'text-hard bg-hard/10',
};

// Chat panel fills the viewport between the mobile top bar and the bottom tab bar (64px + safe area).
// The negative margin cancels the page's bottom padding so the page itself never scrolls.
const LAYOUT_CSS = `
.iv-panel { height: calc(100dvh - 56px - env(safe-area-inset-top) - 20px - 64px - env(safe-area-inset-bottom) - 8px); min-height: 360px; margin-bottom: -40px; }
@media (min-width: 640px) { .iv-panel { height: calc(100dvh - 56px - env(safe-area-inset-top) - 32px - 64px - env(safe-area-inset-bottom) - 8px); } }
@media (min-width: 1024px) { .iv-panel { height: calc(100dvh - 80px); min-height: 520px; margin-bottom: -16px; } }
`;

const scoreColor = (n) => (n >= 4 ? 'var(--ok)' : n >= 3 ? 'var(--medium)' : 'var(--danger)');

function fmtClock(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = String(total % 60).padStart(2, '0');
    return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

function duration(s) {
    if (!s?.created_at || !s?.ended_at) return null;
    const min = Math.max(1, Math.round((Date.parse(s.ended_at) - Date.parse(s.created_at)) / 60000));
    return `${min} min`;
}

// ---------------- speech ----------------
const stripMd = (t) => (t || '')
    .replace(/```[\s\S]*?```/g, ' code block. ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`#>]+/g, '')
    .replace(/\s+/g, ' ')
    .trim();

const canSpeak = () => typeof window !== 'undefined' && 'speechSynthesis' in window;

function speak(text) {
    if (!canSpeak() || !text) return;
    const synth = window.speechSynthesis;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(stripMd(text));
    const voices = synth.getVoices();
    const voice = voices.find((v) => v.lang === 'en-IN') || voices.find((v) => v.lang?.startsWith('en'));
    if (voice) u.voice = voice;
    u.lang = voice?.lang || 'en-IN';
    u.rate = 1.03;
    synth.speak(u);
}

function stopSpeaking() {
    if (canSpeak()) window.speechSynthesis.cancel();
}

function getRecognition() {
    if (typeof window === 'undefined') return null;
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

// Web Speech dictation (en-IN). onText(base, spoken) is called with the text present when dictation began.
function useDictation(onText, onError) {
    const Rec = getRecognition();
    const [listening, setListening] = useState(false);
    const recRef = useRef(null);
    const cb = useRef({ onText, onError });
    cb.current = { onText, onError };

    const stop = useCallback(() => { recRef.current?.stop(); }, []);
    const start = useCallback((base) => {
        if (!Rec) return;
        recRef.current?.abort();
        const rec = new Rec();
        rec.lang = 'en-IN';
        rec.continuous = true;
        rec.interimResults = true;
        rec.onresult = (e) => {
            let spoken = '';
            for (let i = 0; i < e.results.length; i++) spoken += e.results[i][0].transcript;
            cb.current.onText(base, spoken);
        };
        rec.onerror = (e) => {
            if (e.error !== 'aborted' && e.error !== 'no-speech') {
                cb.current.onError(e.error === 'not-allowed' ? 'Microphone permission denied.' : `Voice input error: ${e.error}`);
            }
        };
        rec.onend = () => { setListening(false); if (recRef.current === rec) recRef.current = null; };
        recRef.current = rec;
        try {
            rec.start();
            setListening(true);
        } catch {
            setListening(false);
        }
    }, [Rec]);

    useEffect(() => () => recRef.current?.abort(), []);
    return { supported: !!Rec, listening, start, stop };
}

function useNow(active) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        if (!active) return undefined;
        const t = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(t);
    }, [active]);
    return now;
}

// ---------------- page ----------------
export default function Interview() {
    const push = useToast();
    const [, idPart] = useHashRoute();
    const openId = Number(idPart) || null;
    const hist = useApi('/interview', { select: (d) => d });
    const [session, setSession] = useState(null);
    const [loadingId, setLoadingId] = useState(null);
    const [starting, setStarting] = useState(null);
    const [speakOn, setSpeakOn] = useLocalStorage('interview:speak', false);
    const reloadHist = hist.reload;

    // The open session lives in the hash (#/interview/12), so refresh and the back button just work.
    useEffect(() => {
        if (!openId) { setSession(null); return undefined; }
        if (session?.id === openId) return undefined;
        let live = true;
        setLoadingId(openId);
        api(`/interview/${openId}`)
            .then((res) => { if (live) setSession(res.data); })
            .catch((e) => { if (live) { push(e.message, 'error'); navigate('interview'); } })
            .finally(() => { if (live) setLoadingId(null); });
        return () => { live = false; };
    }, [openId, session?.id, push]);

    useEffect(() => () => stopSpeaking(), []);

    const start = async (mode) => {
        if (starting) return;
        setStarting(mode);
        try {
            const res = await api('/interview/start', { method: 'POST', body: { mode } });
            setSession(res.data);
            navigate(`interview/${res.data.id}`);
            window.scrollTo({ top: 0 });
            if (speakOn) speak(res.data.transcript?.[0]?.text);
            reloadHist({ silent: true });
        } catch (e) {
            push(e.message, 'error');
        } finally {
            setStarting(null);
        }
    };

    const back = () => {
        stopSpeaking();
        navigate('interview');
        reloadHist({ silent: true });
    };

    const remove = async (id) => {
        if (!window.confirm('Delete this interview from your history?')) return;
        try {
            await api(`/interview/${id}`, { method: 'DELETE' });
            hist.setData((d) => d && { ...d, data: d.data.filter((x) => x.id !== id) });
            reloadHist({ silent: true });
        } catch (e) {
            push(e.message, 'error');
        }
    };

    if (openId) {
        return (
            <>
                <style>{LAYOUT_CSS}</style>
                {session?.id === openId && !loadingId ? (
                    <SessionView
                        key={session.id}
                        initial={session}
                        onBack={back}
                        onChanged={() => reloadHist({ silent: true })}
                        onRestart={start}
                        restarting={starting}
                        speakOn={speakOn}
                        setSpeakOn={setSpeakOn}
                    />
                ) : (
                    <Card className="iv-panel p-4 flex flex-col gap-3">
                        <Skeleton className="h-9 w-2/3" />
                        <Skeleton className="h-24 w-4/5" />
                        <Skeleton className="h-16 w-3/5 self-end" />
                        <Skeleton className="h-20 w-4/5" />
                    </Card>
                )}
            </>
        );
    }

    return (
        <Lobby
            hist={hist}
            starting={starting}
            onStart={start}
            onOpen={(id) => navigate(`interview/${id}`)}
            onDelete={remove}
        />
    );
}

// ---------------- lobby ----------------
function Lobby({ hist, starting, onStart, onOpen, onDelete }) {
    const items = hist.data?.data || [];
    const avg = hist.data?.averages;

    return (
        <div className="space-y-6 animate-rise">
            <header>
                <p className="eyebrow">Placement prep</p>
                <h1 className="text-2xl sm:text-[28px] font-semibold tracking-tight mt-1">Interview Lab</h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Mock rounds with an AI interviewer that pushes back like a real one. Think aloud, then end the round for a
                    scored rubric and the three fixes that matter most.
                </p>
            </header>

            <div className="grid gap-3 sm:gap-4 md:grid-cols-3">
                {MODES.map((m) => {
                    const stats = avg?.by_mode?.[m.id];
                    const busy = starting === m.id;
                    return (
                        <Card key={m.id} className="card-pad flex flex-col">
                            <div className="flex items-center gap-3">
                                <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0">
                                    <m.icon className="h-5 w-5" />
                                </div>
                                <div className="min-w-0">
                                    <h2 className="text-[15px] font-semibold tracking-tight">{m.label}</h2>
                                    <p className="text-xs text-subtle">{m.meta}</p>
                                </div>
                            </div>
                            <p className="text-[13px] text-muted mt-3 leading-relaxed flex-1">{m.blurb}</p>
                            <div className="mt-4 flex items-center justify-between gap-2">
                                <span className="text-xs text-subtle tabular-nums">
                                    {stats ? `Avg ${stats.overall.toFixed(1)}/5 · ${stats.count} graded` : 'Not tried yet'}
                                </span>
                                <Button
                                    variant="primary"
                                    size="sm"
                                    loading={busy}
                                    disabled={!!starting}
                                    onClick={() => onStart(m.id)}
                                >
                                    {busy ? (m.id === 'dsa' ? 'Picking problem…' : 'Starting…') : 'Start'}
                                </Button>
                            </div>
                        </Card>
                    );
                })}
            </div>

            {avg?.graded > 0 && (
                <Card className="card-pad flex flex-wrap items-center gap-x-6 gap-y-3">
                    <div>
                        <p className="eyebrow">Average score</p>
                        <p className="text-2xl font-semibold tabular-nums tracking-tight mt-0.5">
                            {avg.overall.toFixed(1)}<span className="text-sm text-subtle font-medium">/5</span>
                        </p>
                    </div>
                    <div>
                        <p className="eyebrow">Graded rounds</p>
                        <p className="text-2xl font-semibold tabular-nums tracking-tight mt-0.5">{avg.graded}</p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                        {Object.keys(VERDICT).filter((v) => avg.verdicts?.[v]).map((v) => (
                            <span key={v} className={cx('badge capitalize', VERDICT[v])}>{v} · {avg.verdicts[v]}</span>
                        ))}
                    </div>
                </Card>
            )}

            <Card className="card-pad">
                <div className="flex items-center gap-2 mb-3">
                    <History className="h-4 w-4 text-subtle" />
                    <h2 className="text-[15px] font-semibold tracking-tight">History</h2>
                </div>
                {hist.loading && !hist.data ? (
                    <div className="space-y-2">
                        <Skeleton className="h-12" /><Skeleton className="h-12" /><Skeleton className="h-12" />
                    </div>
                ) : hist.error && !hist.data ? (
                    <Empty icon={CircleAlert} title="Couldn't load your interviews" action={<Button size="sm" onClick={() => hist.reload()}>Retry</Button>}>
                        {hist.error}
                    </Empty>
                ) : items.length === 0 ? (
                    <Empty icon={Sparkles} title="No interviews yet">Pick a round above. Your first one takes about 20–40 minutes.</Empty>
                ) : (
                    <ul className="-mx-2">
                        {items.map((s) => {
                            const M = MODE[s.mode] || MODES[0];
                            return (
                                <li key={s.id} className="group flex items-center gap-1 rounded-xl row-hover">
                                    <button
                                        type="button"
                                        onClick={() => onOpen(s.id)}
                                        className="flex flex-1 min-w-0 items-center gap-3 px-2 py-2.5 text-left rounded-xl focus-visible:outline-2 focus-visible:outline-accent"
                                    >
                                        <div className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line text-muted shrink-0">
                                            <M.icon className="h-4 w-4" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium truncate">{s.title}</p>
                                            <p className="text-xs text-subtle truncate">
                                                {M.label} · {timeAgo(s.created_at)}
                                                {duration(s) ? ` · ${duration(s)}` : ''}
                                                {` · ${s.turns} ${s.turns === 1 ? 'answer' : 'answers'}`}
                                            </p>
                                        </div>
                                        {s.status === 'active' ? (
                                            <span className="badge text-accent bg-accent-soft">In progress</span>
                                        ) : s.verdict ? (
                                            <span className={cx('badge capitalize', VERDICT[s.verdict])}>
                                                {s.verdict}{s.overall != null ? ` · ${Number(s.overall).toFixed(1)}` : ''}
                                            </span>
                                        ) : (
                                            <span className="badge text-subtle bg-surface-2">No feedback</span>
                                        )}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => onDelete(s.id)}
                                        className="btn btn-ghost btn-icon btn-sm shrink-0 sm:opacity-0 sm:group-hover:opacity-100 focus-visible:opacity-100"
                                        aria-label={`Delete ${s.title}`}
                                    >
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Card>
        </div>
    );
}

// ---------------- session ----------------
function SessionView({ initial, onBack, onChanged, onRestart, restarting, speakOn, setSpeakOn }) {
    const push = useToast();
    const [s, setS] = useState(initial);
    const [input, setInput] = useState('');
    const [stream, setStream] = useState(null); // { text } while the interviewer is replying
    const [error, setError] = useState(null);
    const [ending, setEnding] = useState(false);
    const [tab, setTab] = useState(initial.status === 'done' ? 'feedback' : 'chat');
    const ctrl = useRef(null);
    const scroller = useRef(null);
    const textarea = useRef(null);
    const stick = useRef(initial.status === 'active');
    const speakRef = useRef(speakOn);
    speakRef.current = speakOn;

    const active = s.status === 'active';
    const now = useNow(active);
    const M = MODE[s.mode] || MODES[0];
    const transcript = s.transcript || [];
    const last = transcript[transcript.length - 1];
    const candidateTurns = transcript.filter((m) => m.role === 'candidate').length;
    const needsRetry = active && !stream && last?.role === 'candidate';
    const elapsed = (s.ended_at ? Date.parse(s.ended_at) : now) - Date.parse(s.created_at);

    const dict = useDictation(
        (base, spoken) => setInput(base ? `${base.replace(/\s+$/, '')} ${spoken.trimStart()}` : spoken.trimStart()),
        (msg) => push(msg, 'error'),
    );
    const { stop: stopDictation } = dict;

    useEffect(() => () => { ctrl.current?.abort(); }, []);

    // Auto-scroll while the user is at the bottom.
    useEffect(() => {
        const el = scroller.current;
        if (el && stick.current) el.scrollTop = el.scrollHeight;
    }, [transcript.length, stream?.text, error, tab, ending]);

    // Auto-grow the composer.
    useEffect(() => {
        const el = textarea.current;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
    }, [input]);

    const onScroll = () => {
        const el = scroller.current;
        if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };

    const send = async ({ retry = false } = {}) => {
        const text = input.trim();
        if (stream || ending || !active || (!retry && !text)) return;
        stopDictation();
        stopSpeaking();
        setError(null);
        if (!retry) {
            setS((p) => ({ ...p, transcript: [...p.transcript, { role: 'candidate', text, at: new Date().toISOString() }] }));
            setInput('');
        }
        stick.current = true;
        setStream({ text: '' });
        const controller = new AbortController();
        ctrl.current = controller;
        let acc = '';
        let finished = false;
        try {
            await streamSSE(`/interview/${s.id}/reply`, retry ? { retry: true } : { text }, (ev) => {
                if (ev.type === 'delta') {
                    acc += ev.text;
                    setStream({ text: acc });
                } else if (ev.type === 'done') {
                    finished = true;
                    setS((p) => ({ ...p, transcript: [...p.transcript, ev.message] }));
                    if (speakRef.current) speak(ev.message.text);
                } else if (ev.type === 'error') {
                    finished = true;
                    setError(ev.message || 'The interviewer could not respond.');
                }
            }, controller.signal);
            if (!finished && !controller.signal.aborted) setError('Connection dropped before the interviewer finished.');
        } catch (e) {
            if (e.name === 'AbortError') return;
            setError(e.message);
            // The request never reached the stream, so the answer wasn't saved: give it back.
            if (!retry && !/network|fetch/i.test(e.message)) {
                setS((p) => ({ ...p, transcript: p.transcript.slice(0, -1) }));
                setInput(text);
            }
        } finally {
            if (ctrl.current === controller) ctrl.current = null;
            setStream(null);
        }
    };

    const end = async () => {
        if (stream || ending) return;
        if (candidateTurns < 2 && !window.confirm(
            candidateTurns === 0 ? 'You haven\'t answered yet, so there will be no feedback. End anyway?' : 'Only one answer so far. End and get feedback anyway?',
        )) return;
        stopDictation();
        stopSpeaking();
        setEnding(true);
        setError(null);
        try {
            const res = await api(`/interview/${s.id}/end`, { method: 'POST' });
            setS(res.data);
            setTab('feedback');
            onChanged();
        } catch (e) {
            push(e.message, 'error');
        } finally {
            setEnding(false);
        }
    };

    const toggleSpeak = () => {
        if (speakOn) stopSpeaking();
        setSpeakOn(!speakOn);
    };

    const onKeyDown = (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            send();
        }
    };

    return (
        <Card className="iv-panel flex flex-col overflow-hidden animate-rise">
            {/* Top bar */}
            <div className="flex items-center gap-1.5 sm:gap-2 border-b border-line px-2 sm:px-3 h-14 shrink-0">
                <button type="button" onClick={onBack} className="btn btn-ghost btn-icon shrink-0" aria-label="Back to Interview Lab">
                    <ArrowLeft className="h-4 w-4" />
                </button>
                <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle flex items-center gap-1">
                        <M.icon className="h-3 w-3" /> {M.label}
                    </p>
                    <p className="text-sm font-semibold truncate leading-tight">{s.title}</p>
                </div>
                {active ? (
                    <>
                        <span
                            className="hidden min-[360px]:inline-flex items-center gap-1 rounded-lg bg-surface-2 border border-line px-2 h-8 text-xs font-mono tabular-nums text-muted shrink-0"
                            aria-label="Elapsed time"
                        >
                            <Timer className="h-3.5 w-3.5" /> {fmtClock(elapsed)}
                        </span>
                        {canSpeak() && (
                            <button
                                type="button"
                                onClick={toggleSpeak}
                                className={cx('btn btn-ghost btn-icon shrink-0', speakOn && 'text-accent')}
                                aria-label={speakOn ? 'Stop reading replies aloud' : 'Read replies aloud'}
                                aria-pressed={speakOn}
                                title={speakOn ? 'Read aloud: on' : 'Read aloud: off'}
                            >
                                {speakOn ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
                            </button>
                        )}
                        <Button variant="secondary" size="sm" icon={Flag} onClick={end} loading={ending} disabled={!!stream} className="shrink-0">
                            <span className="hidden sm:inline">End &amp; get feedback</span>
                            <span className="sm:hidden">End</span>
                        </Button>
                    </>
                ) : (
                    <Segmented
                        className="shrink-0"
                        value={tab}
                        onChange={(v) => { stick.current = false; setTab(v); }}
                        options={[{ value: 'feedback', label: 'Feedback' }, { value: 'chat', label: 'Transcript' }]}
                    />
                )}
            </div>

            {/* Body */}
            <div ref={scroller} onScroll={onScroll} className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
                {!active && tab === 'feedback' ? (
                    <Feedback session={s} onRestart={onRestart} restarting={restarting} onBack={onBack} />
                ) : (
                    <div className="px-3 sm:px-5 py-4 space-y-3" aria-live="polite">
                        {transcript.map((m, i) => <Bubble key={`${i}-${m.at}`} msg={m} />)}
                        {stream && (
                            stream.text
                                ? <Bubble msg={{ role: 'interviewer', text: stream.text }} streaming />
                                : (
                                    <div className="flex items-center gap-2 text-[13px] text-subtle px-1">
                                        <Spinner className="h-3.5 w-3.5" /> Interviewer is thinking…
                                    </div>
                                )
                        )}
                        {(error || needsRetry) && !stream && (
                            <div className="flex items-start gap-2 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2.5 text-[13px] text-danger">
                                <CircleAlert className="h-4 w-4 mt-0.5 shrink-0" />
                                <span className="flex-1 min-w-0">{error || 'The interviewer hasn\'t replied to your last answer yet.'}</span>
                                {needsRetry && (
                                    <Button size="sm" variant="secondary" icon={RotateCcw} onClick={() => send({ retry: true })} className="-my-1 shrink-0">
                                        Retry
                                    </Button>
                                )}
                            </div>
                        )}
                        {ending && (
                            <div className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2.5 text-[13px] text-muted">
                                <Spinner className="h-3.5 w-3.5" /> Grading your interview… this can take up to a minute.
                            </div>
                        )}
                        {!active && !s.rubric && (
                            <p className="text-center text-xs text-subtle pt-2">This interview ended without feedback.</p>
                        )}
                    </div>
                )}
            </div>

            {/* Composer */}
            {active && (
                <div className="border-t border-line bg-surface px-2.5 sm:px-3 pt-2.5 pb-2.5 shrink-0">
                    <div className="flex items-end gap-2">
                        {dict.supported && (
                            <button
                                type="button"
                                onClick={() => (dict.listening ? dict.stop() : dict.start(input))}
                                disabled={ending}
                                className={cx('btn btn-icon h-10 w-10 shrink-0', dict.listening ? 'btn-primary animate-glow' : 'btn-secondary')}
                                aria-label={dict.listening ? 'Stop voice input' : 'Speak your answer'}
                                aria-pressed={dict.listening}
                            >
                                {dict.listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                            </button>
                        )}
                        <textarea
                            ref={textarea}
                            rows={1}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={onKeyDown}
                            disabled={ending}
                            maxLength={6000}
                            placeholder={dict.listening ? 'Listening…' : 'Think aloud… your approach, a question, or code'}
                            aria-label="Your answer"
                            className="input h-10 min-h-10 py-[7px] leading-6 resize-none text-base sm:text-sm"
                        />
                        <Button
                            variant="primary"
                            icon={SendHorizontal}
                            onClick={() => send()}
                            disabled={!input.trim() || !!stream || ending}
                            className="btn-icon h-10 w-10 shrink-0"
                            aria-label="Send (Ctrl+Enter)"
                        />
                    </div>
                    <p className="hidden sm:block text-[11px] text-subtle mt-1.5 px-1">
                        Ctrl/⌘ + Enter to send · explain before you code · ask for a hint if you're stuck
                    </p>
                </div>
            )}
        </Card>
    );
}

function Bubble({ msg, streaming }) {
    if (msg.role === 'candidate') {
        return (
            <div className="flex justify-end">
                <div className="max-w-[88%] sm:max-w-[78%] rounded-2xl rounded-tr-md bg-accent-soft border border-accent/20 px-3.5 py-2.5 text-[14.5px] leading-relaxed text-fg whitespace-pre-wrap break-words">
                    {msg.text}
                </div>
            </div>
        );
    }
    return (
        <div className="flex">
            <div className="max-w-[92%] sm:max-w-[80%] rounded-2xl rounded-tl-md bg-surface-2 border border-line px-3.5 py-2.5 min-w-0 break-words">
                <Markdown streaming={streaming}>{msg.text}</Markdown>
            </div>
        </div>
    );
}

// ---------------- feedback ----------------
function Feedback({ session, onRestart, restarting, onBack }) {
    const r = session.rubric;
    if (!r) {
        return (
            <Empty
                icon={CircleAlert}
                title="No feedback for this round"
                action={<Button variant="primary" loading={restarting === session.mode} onClick={() => onRestart(session.mode)}>Try again</Button>}
            >
                It ended before you answered anything.
            </Empty>
        );
    }
    const scores = r.scores || (session.dimensions || []).map((d) => ({ ...d, score: r[d.key] }));
    return (
        <div className="px-4 sm:px-6 py-5 space-y-6 animate-rise">
            <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
                <div>
                    <p className="eyebrow">Overall</p>
                    <p className="text-4xl font-semibold tabular-nums tracking-tight mt-1">
                        {Number(r.overall ?? 0).toFixed(1)}<span className="text-base text-subtle font-medium">/5</span>
                    </p>
                </div>
                <span className={cx('badge capitalize text-[13px] px-2.5 py-1 mb-1.5', VERDICT[r.verdict] || 'text-muted bg-surface-2')}>
                    {r.verdict}
                </span>
                <div className="text-xs text-subtle mb-2 basis-full sm:basis-auto sm:ml-auto flex flex-wrap gap-x-3 gap-y-1">
                    {duration(session) && <span>{duration(session)}</span>}
                    <span>{session.turns} answers</span>
                    <span>{timeAgo(session.created_at)}</span>
                    {session.problem?.link && (
                        <a href={session.problem.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
                            LeetCode <ExternalLink className="h-3 w-3" />
                        </a>
                    )}
                </div>
            </div>

            <section className="space-y-3">
                {scores.map((d) => (
                    <div key={d.key} className="grid grid-cols-[minmax(0,9.5rem)_1fr_2.25rem] sm:grid-cols-[11rem_1fr_2.5rem] items-center gap-3">
                        <span className="text-[13px] text-muted truncate">{d.label}</span>
                        <ProgressBar value={(d.score / 5) * 100} color={scoreColor(d.score)} className="h-2" />
                        <span className="text-[13px] font-semibold tabular-nums text-right">{d.score}/5</span>
                    </div>
                ))}
            </section>

            <div className="grid gap-4 md:grid-cols-2">
                <section className="rounded-xl border border-line bg-surface-2/50 p-4">
                    <h3 className="text-sm font-semibold flex items-center gap-1.5 mb-2.5">
                        <CheckCircle2 className="h-4 w-4 text-ok" /> Strengths
                    </h3>
                    {r.strengths?.length ? (
                        <ul className="space-y-1.5 text-[13.5px] text-fg/90">
                            {r.strengths.map((x, i) => <li key={i} className="flex gap-2"><span className="text-ok">•</span><span>{x}</span></li>)}
                        </ul>
                    ) : <p className="text-[13px] text-subtle">None noted this time.</p>}
                </section>
                <section className="rounded-xl border border-line bg-surface-2/50 p-4">
                    <h3 className="text-sm font-semibold flex items-center gap-1.5 mb-2.5">
                        <ListChecks className="h-4 w-4 text-accent" /> Top fixes
                    </h3>
                    {r.top_fixes?.length ? (
                        <ol className="space-y-2 text-[13.5px] text-fg/90">
                            {r.top_fixes.map((x, i) => (
                                <li key={i} className="flex gap-2.5">
                                    <span className="grid place-items-center h-5 w-5 rounded-full bg-accent-soft text-accent text-[11px] font-bold shrink-0">{i + 1}</span>
                                    <span>{x}</span>
                                </li>
                            ))}
                        </ol>
                    ) : <p className="text-[13px] text-subtle">Nothing specific.</p>}
                </section>
            </div>

            {r.model_answer_outline && (
                <section>
                    <h3 className="text-sm font-semibold flex items-center gap-1.5 mb-2">
                        <Lightbulb className="h-4 w-4 text-medium" /> Model answer outline
                    </h3>
                    <div className="rounded-xl border border-line p-4">
                        <Markdown>{r.model_answer_outline}</Markdown>
                    </div>
                </section>
            )}

            <div className="flex flex-wrap gap-2 pt-1 pb-2">
                <Button variant="primary" icon={RotateCcw} loading={restarting === session.mode} disabled={!!restarting} onClick={() => onRestart(session.mode)}>
                    Another {MODE[session.mode]?.label || ''} round
                </Button>
                <Button variant="ghost" icon={ArrowLeft} onClick={onBack}>Back to lab</Button>
            </div>
        </div>
    );
}
