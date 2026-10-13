import { useEffect, useRef, useState } from 'react';
import {
    Timer, Zap, Trophy, Play, RotateCcw, Check, Sparkles, ChevronRight, Award,
    Flame, Flag, Bot, User, Gauge,
} from 'lucide-react';
import { Button, Card, ProgressBar, Skeleton, useToast, cx } from '../components/ui';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

// WebAudio Sound FX Generator
function playSfx(type) {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        const now = ctx.currentTime;
        if (type === 'type') {
            osc.frequency.setValueAtTime(600, now);
            gain.gain.setValueAtTime(0.02, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
            osc.start(now);
            osc.stop(now + 0.04);
        } else if (type === 'win') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(440, now);
            osc.frequency.setValueAtTime(554.37, now + 0.1);
            osc.frequency.setValueAtTime(659.25, now + 0.2);
            gain.gain.setValueAtTime(0.12, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
            osc.start(now);
            osc.stop(now + 0.4);
        } else if (type === 'lose') {
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(300, now);
            osc.frequency.setValueAtTime(220, now + 0.15);
            gain.gain.setValueAtTime(0.1, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.35);
        }
    } catch {
        // AudioContext disabled or blocked
    }
}

export default function Ghost() {
    const toast = useToast();
    const tracksRes = useApi('/ghost/tracks');
    const profileRes = useApi('/ghost/profile');

    const tracks = tracksRes.data?.tracks || [];
    const stats = profileRes.data?.stats || { ghost_elo: 1200, ghost_wins: 0, top_wpm: 0, avg_wpm: 0 };

    const [selectedTrack, setSelectedTrack] = useState(null);
    const [typed, setTyped] = useState('');
    const [racing, setRacing] = useState(false);
    const [startTime, setStartTime] = useState(null);
    const [elapsedMs, setElapsedMs] = useState(0);
    const [finished, setFinished] = useState(false);
    const [result, setResult] = useState(null);

    const inputRef = useRef(null);
    const timerRef = useRef(null);

    // Default to first track once loaded
    useEffect(() => {
        if (!selectedTrack && tracks.length > 0) {
            setSelectedTrack(tracks[0]);
        }
    }, [tracks, selectedTrack]);

    // Timer loop during race
    useEffect(() => {
        if (racing && !finished) {
            timerRef.current = setInterval(() => {
                setElapsedMs(Date.now() - startTime);
            }, 50);
        } else {
            clearInterval(timerRef.current);
        }
        return () => clearInterval(timerRef.current);
    }, [racing, finished, startTime]);

    const startRace = () => {
        setTyped('');
        setElapsedMs(0);
        setFinished(false);
        setResult(null);
        setStartTime(Date.now());
        setRacing(true);
        setTimeout(() => inputRef.current?.focus(), 50);
    };

    const resetRace = () => {
        setRacing(false);
        setFinished(false);
        setTyped('');
        setElapsedMs(0);
        setResult(null);
    };

    const targetCode = selectedTrack?.target_code || '';
    const userProgress = targetCode.length > 0 ? Math.min(100, Math.round((typed.length / targetCode.length) * 100)) : 0;

    // Ghost runner progress based on ghost_wpm (5 chars per word)
    const ghostCharsPerSec = ((selectedTrack?.ghost_wpm || 70) * 5) / 60;
    const ghostCharsTyped = (elapsedMs / 1000) * ghostCharsPerSec;
    const ghostProgress = targetCode.length > 0 ? Math.min(100, Math.round((ghostCharsTyped / targetCode.length) * 100)) : 0;

    // Handle typing input
    const handleType = async (e) => {
        if (!racing || finished) return;
        const val = e.target.value;
        setTyped(val);
        playSfx('type');

        // Check if finished
        if (val.length >= targetCode.length) {
            setFinished(true);
            setRacing(false);
            const totalTimeMs = Date.now() - startTime;

            // Compute accuracy
            let correct = 0;
            for (let i = 0; i < targetCode.length; i++) {
                if (val[i] === targetCode[i]) correct++;
            }
            const accuracy = Math.round((correct / targetCode.length) * 100);

            try {
                const res = await api('/ghost/submit', {
                    method: 'POST',
                    body: {
                        track_id: selectedTrack.id,
                        time_ms: totalTimeMs,
                        accuracy,
                        code: val,
                    },
                });

                if (res?.run) {
                    setResult(res.run);
                    if (res.run.ghost_beaten) {
                        playSfx('win');
                        toast(`🏆 Ghost Defeated! +${res.run.xp_earned} XP`, 'success');
                    } else {
                        playSfx('lose');
                        toast(`Ghost won this round. Try again!`, 'info');
                    }
                    tracksRes.reload({ silent: true });
                    profileRes.reload({ silent: true });
                }
            } catch (err) {
                toast(err.message || 'Submission error', 'error');
            }
        }
    };

    const currentWpm = elapsedMs > 500 ? Math.round(((typed.length / 5) / (elapsedMs / 60000))) : 0;

    return (
        <div className="space-y-6 animate-rise">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
                <div>
                    <div className="flex items-center gap-2">
                        <span className="badge text-accent bg-accent/10 border border-accent/20">Beta Lab · Speed Trials</span>
                        <span className="badge text-purple-400 bg-purple-500/10 border border-purple-500/20 font-mono">
                            {stats.ghost_elo} ELO
                        </span>
                    </div>
                    <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight mt-1.5 flex items-center gap-2.5">
                        <Timer className="h-7 w-7 text-accent" /> Ghost Racer
                    </h1>
                    <p className="text-sm text-muted mt-1 max-w-2xl">
                        Build algorithm muscle memory in real-time time trials. Race head-to-head against AI Sensei ghosts and your past personal best.
                    </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                    <div className="px-3 py-1.5 rounded-xl bg-surface-2 border border-line flex items-center gap-3 text-xs">
                        <div>
                            <span className="text-subtle">Wins:</span> <b className="text-ok font-mono">{stats.ghost_wins}</b>
                        </div>
                        <div className="h-3 w-px bg-line" />
                        <div>
                            <span className="text-subtle">Peak:</span> <b className="text-accent font-mono">{stats.top_wpm} WPM</b>
                        </div>
                    </div>
                </div>
            </div>

            {/* Track Selector & Arena Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-5 items-start">
                {/* Track list */}
                <Card className="card-pad space-y-2 lg:col-span-1">
                    <h2 className="text-xs font-bold uppercase tracking-wider text-subtle px-1">Circuit Tracks</h2>
                    {tracks.map((t) => (
                        <button
                            key={t.id}
                            type="button"
                            onClick={() => {
                                setSelectedTrack(t);
                                resetRace();
                            }}
                            className={cx(
                                'w-full text-left p-2.5 rounded-xl border transition-all text-xs flex items-center justify-between gap-2',
                                selectedTrack?.id === t.id
                                    ? 'bg-surface-2 border-accent text-fg font-semibold shadow-xs'
                                    : 'border-line hover:border-line-strong text-muted hover:text-fg'
                            )}
                        >
                            <div className="min-w-0">
                                <div className="truncate">{t.title}</div>
                                <div className="text-[10px] text-subtle mt-0.5">{t.ghost_wpm} WPM · {t.difficulty}</div>
                            </div>
                            {t.ghost_beaten && <Check className="h-3.5 w-3.5 text-ok shrink-0" strokeWidth={3} />}
                        </button>
                    ))}
                </Card>

                {/* Race Track Canvas */}
                <div className="space-y-4 lg:col-span-3">
                    <Card className="card-pad space-y-4 border-accent/20">
                        {/* Race Track Header */}
                        <div className="flex items-center justify-between gap-2 border-b border-line pb-3">
                            <div>
                                <span className="text-[11px] font-bold uppercase tracking-wider text-accent">
                                    {selectedTrack?.difficulty} · {selectedTrack?.category}
                                </span>
                                <h3 className="text-lg font-bold tracking-tight text-fg">{selectedTrack?.title}</h3>
                                <p className="text-xs text-subtle mt-0.5">{selectedTrack?.description}</p>
                            </div>

                            <div className="flex items-center gap-2">
                                {!racing && !finished ? (
                                    <Button variant="primary" icon={Play} onClick={startRace}>
                                        Start Race
                                    </Button>
                                ) : (
                                    <Button variant="ghost" icon={RotateCcw} onClick={resetRace}>
                                        Restart
                                    </Button>
                                )}
                            </div>
                        </div>

                        {/* Live Racers Lane */}
                        <div className="p-3.5 rounded-2xl bg-surface-2/60 border border-line space-y-3">
                            {/* Player Lane */}
                            <div className="space-y-1.5">
                                <div className="flex items-center justify-between text-xs font-semibold">
                                    <span className="flex items-center gap-1.5 text-ok">
                                        <User className="h-3.5 w-3.5" /> You
                                    </span>
                                    <span className="font-mono text-fg tabular-nums">{currentWpm} WPM ({userProgress}%)</span>
                                </div>
                                <ProgressBar value={userProgress} color="var(--ok)" className="h-2" />
                            </div>

                            {/* Ghost Sensei Lane */}
                            <div className="space-y-1.5">
                                <div className="flex items-center justify-between text-xs font-semibold">
                                    <span className="flex items-center gap-1.5 text-purple-400">
                                        <Bot className="h-3.5 w-3.5" /> {selectedTrack?.ghost_name}
                                    </span>
                                    <span className="font-mono text-purple-400 tabular-nums">{selectedTrack?.ghost_wpm} WPM ({ghostProgress}%)</span>
                                </div>
                                <ProgressBar value={ghostProgress} color="#a855f7" className="h-2" />
                            </div>
                        </div>

                        {/* Telemetry Stats Bar */}
                        <div className="grid grid-cols-3 gap-2 text-center text-xs">
                            <div className="p-2 rounded-xl bg-surface-2 border border-line">
                                <div className="text-subtle text-[11px]">Time</div>
                                <div className="font-mono font-bold text-base mt-0.5 tabular-nums">
                                    {(elapsedMs / 1000).toFixed(1)}s
                                </div>
                            </div>
                            <div className="p-2 rounded-xl bg-surface-2 border border-line">
                                <div className="text-subtle text-[11px]">Your Pace</div>
                                <div className="font-mono font-bold text-base text-accent mt-0.5 tabular-nums">
                                    {currentWpm} WPM
                                </div>
                            </div>
                            <div className="p-2 rounded-xl bg-surface-2 border border-line">
                                <div className="text-subtle text-[11px]">Ghost Target</div>
                                <div className="font-mono font-bold text-base text-purple-400 mt-0.5 tabular-nums">
                                    {selectedTrack?.ghost_wpm} WPM
                                </div>
                            </div>
                        </div>

                        {/* Code Display with Inline Character Diff */}
                        <div className="relative rounded-2xl bg-surface-2 p-4 font-mono text-xs leading-relaxed border border-line overflow-hidden">
                            <div className="text-subtle select-none whitespace-pre-wrap">
                                {targetCode.split('').map((char, i) => {
                                    let color = 'text-subtle/70';
                                    if (i < typed.length) {
                                        color = typed[i] === char ? 'text-ok font-bold' : 'text-danger bg-danger/20 font-bold';
                                    }
                                    return (
                                        <span key={i} className={color}>
                                            {char}
                                        </span>
                                    );
                                })}
                            </div>

                            {/* Hidden / Transparent Typing Input */}
                            <textarea
                                ref={inputRef}
                                value={typed}
                                onChange={handleType}
                                disabled={!racing || finished}
                                className="absolute inset-0 opacity-0 cursor-text resize-none"
                                spellCheck={false}
                                autoCapitalize="off"
                                autoCorrect="off"
                            />
                        </div>

                        {!racing && !finished && (
                            <div className="text-center py-2">
                                <Button variant="primary" icon={Play} size="lg" onClick={startRace}>
                                    Ready? Start Time Trial
                                </Button>
                            </div>
                        )}

                        {/* Race Result Banner */}
                        {finished && result && (
                            <div className={cx(
                                'p-4 rounded-2xl border text-center animate-rise space-y-2',
                                result.ghost_beaten
                                    ? 'bg-ok/10 border-ok/30 text-ok'
                                    : 'bg-surface-2 border-line text-muted'
                            )}>
                                <div className="text-xl font-extrabold flex items-center justify-center gap-2">
                                    {result.ghost_beaten ? (
                                        <>🏆 Ghost Defeated!</>
                                    ) : (
                                        <>⚡ Ghost Won!</>
                                    )}
                                </div>
                                <p className="text-xs">
                                    You finished in <b>{(result.time_ms / 1000).toFixed(1)}s</b> at <b>{result.wpm} WPM</b> with <b>{result.accuracy}%</b> accuracy!
                                </p>
                                <div className="flex items-center justify-center gap-2 pt-1">
                                    <span className="badge text-accent bg-accent/15 border border-accent/20">+{result.xp_earned} XP Earned</span>
                                    <Button size="sm" variant="primary" icon={RotateCcw} onClick={startRace}>
                                        Race Again
                                    </Button>
                                </div>
                            </div>
                        )}
                    </Card>
                </div>
            </div>
        </div>
    );
}
