import { useEffect, useRef, useState } from 'react';
import {
    GraduationCap, Flame, Shield, Send, Activity, Clock
} from 'lucide-react';
import { Button, Card, ProgressBar, Skeleton, useToast, cx } from '../components/ui';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

// WebAudio Sound FX Generator
function playHotSeatSfx(type) {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        const now = ctx.currentTime;

        if (type === 'gavel') {
            // Low thumping gavel strike
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(140, now);
            osc.frequency.exponentialRampToValueAtTime(40, now + 0.15);
            gain.gain.setValueAtTime(0.25, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
            osc.start(now);
            osc.stop(now + 0.2);
        } else if (type === 'heartbeat') {
            // Tense heartbeat pulse
            osc.type = 'sine';
            osc.frequency.setValueAtTime(80, now);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
            osc.start(now);
            osc.stop(now + 0.12);
        } else if (type === 'honor') {
            // Triumphant faculty fanfare
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(523.25, now);
            osc.frequency.setValueAtTime(659.25, now + 0.12);
            osc.frequency.setValueAtTime(783.99, now + 0.24);
            osc.frequency.setValueAtTime(1046.50, now + 0.36);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.6);
            osc.start(now);
            osc.stop(now + 0.6);
        } else if (type === 'roasted') {
            // Dismissal buzz
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(180, now);
            osc.frequency.setValueAtTime(110, now + 0.2);
            gain.gain.setValueAtTime(0.18, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
            osc.start(now);
            osc.stop(now + 0.4);
        }
    } catch {
        // AudioContext not allowed or muted
    }
}

export default function HotSeat() {
    const toast = useToast();
    const topicsRes = useApi('/hotseat/topics');
    const historyRes = useApi('/hotseat/history');

    const topics = topicsRes.data?.topics || [];
    const professors = topicsRes.data?.professors || [];
    const stats = historyRes.data?.stats || { total_defenses: 0, passed: 0, avg_composure: 0, total_xp: 0, best_verdict: 'None' };

    const [selectedTopic, setSelectedTopic] = useState(null);
    const [difficulty, setDifficulty] = useState('masters');
    const [activeSession, setActiveSession] = useState(null);
    const [answerText, setAnswerText] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [timerSec, setTimerSec] = useState(60);
    const timerRef = useRef(null);
    const answerInputRef = useRef(null);

    // Default select first topic
    useEffect(() => {
        if (!selectedTopic && topics.length > 0) {
            setSelectedTopic(topics[0]);
        }
    }, [topics, selectedTopic]);

    // Timer countdown during active session
    useEffect(() => {
        if (activeSession && activeSession.status === 'active') {
            setTimerSec(difficulty === 'phd' ? 45 : difficulty === 'masters' ? 60 : 75);
            if (timerRef.current) clearInterval(timerRef.current);
            timerRef.current = setInterval(() => {
                setTimerSec((prev) => {
                    if (prev <= 10 && prev > 0) {
                        playHotSeatSfx('heartbeat');
                    }
                    if (prev <= 1) {
                        return 0;
                    }
                    return prev - 1;
                });
            }, 1000);
        } else {
            if (timerRef.current) clearInterval(timerRef.current);
        }
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [activeSession, difficulty]);

    const handleStart = async () => {
        if (!selectedTopic) return;
        setSubmitting(true);
        try {
            const res = await api('/hotseat/session/start', {
                method: 'POST',
                body: { subject: selectedTopic.title, difficulty },
            });
            setActiveSession(res.data.session);
            setAnswerText('');
            playHotSeatSfx('gavel');
            toast.success('Defense Commenced', `The faculty tribunal has called you to the stand on ${selectedTopic.title}.`);
            setTimeout(() => answerInputRef.current?.focus(), 200);
        } catch (err) {
            toast.error('Failed to start defense', err.message);
        } finally {
            setSubmitting(false);
        }
    };

    const handleSubmitRebuttal = async (e) => {
        e?.preventDefault();
        if (!activeSession || submitting || !answerText.trim()) return;

        setSubmitting(true);
        try {
            const res = await api(`/hotseat/session/${activeSession.id}/answer`, {
                method: 'POST',
                body: { answer: answerText.trim() },
            });
            const updated = res.data.session;
            setActiveSession(updated);
            setAnswerText('');

            if (updated.status === 'roasted') {
                playHotSeatSfx('roasted');
                toast.error('Defense Rejected!', 'Your composure collapsed under faculty interrogation.');
                historyRes.reload();
            } else if (updated.status === 'completed') {
                playHotSeatSfx('honor');
                toast.success('Defense Passed!', `Verdict: ${updated.final_verdict} (+${updated.xp_awarded} XP)`);
                historyRes.reload();
            } else {
                playHotSeatSfx('gavel');
                toast.info('Faculty Rebuttal', 'Another professor cuts in with a follow-up challenge.');
                setTimeout(() => answerInputRef.current?.focus(), 200);
            }
        } catch (err) {
            toast.error('Submission failed', err.message);
        } finally {
            setSubmitting(false);
        }
    };

    const currentTurn = activeSession?.turns?.[activeSession.turns.length - 1];
    const currentProf = professors.find((p) => p.id === currentTurn?.professor_id) || professors[0];

    const composureColor = !activeSession ? 'bg-accent' :
        activeSession.composure > 60 ? 'bg-emerald-500' :
        activeSession.composure > 30 ? 'bg-amber-500' : 'bg-rose-500 animate-pulse';

    return (
        <div className="space-y-6 animate-fade-in max-w-5xl mx-auto pb-12">
            {/* Header Hero */}
            <div className="relative overflow-hidden rounded-3xl border border-line bg-surface/80 p-6 md:p-8 backdrop-blur-xl shadow-2xl">
                <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20 mb-3">
                            <Flame className="w-3.5 h-3.5" /> High-Stakes Technical Defense
                        </div>
                        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-fg flex items-center gap-3">
                            The Hot Seat
                        </h1>
                        <p className="text-sm md:text-base text-subtle mt-2 max-w-xl">
                            Face a relentless tribunal of 3 AI professors. Defend architecture, algorithms, and asymptotic bounds under a ticking clock and live Composure meter.
                        </p>
                    </div>

                    {/* Stats pills */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-surface-2/60 p-3 rounded-2xl border border-line">
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Defenses</div>
                            <div className="text-lg font-black text-fg">{stats.total_defenses}</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Passed</div>
                            <div className="text-lg font-black text-emerald-500">{stats.passed}</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Avg Composure</div>
                            <div className="text-lg font-black text-amber-500">{stats.avg_composure}%</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Earned XP</div>
                            <div className="text-lg font-black text-accent">+{stats.total_xp}</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Active Viva Arena or Setup View */}
            {!activeSession || activeSession.status !== 'active' ? (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Topic Selection Column */}
                    <div className="lg:col-span-2 space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-bold text-fg flex items-center gap-2">
                                <GraduationCap className="w-5 h-5 text-amber-500" /> Select Oral Defense Subject
                            </h2>
                            <span className="text-xs text-subtle">{topics.length} subjects available</span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {topics.map((t) => {
                                const isSel = selectedTopic?.id === t.id;
                                return (
                                    <button
                                        key={t.id}
                                        type="button"
                                        onClick={() => setSelectedTopic(t)}
                                        className={cx(
                                            'text-left p-4 rounded-2xl border transition-all relative overflow-hidden',
                                            isSel
                                                ? 'bg-amber-500/10 border-amber-500/50 shadow-lg shadow-amber-500/5'
                                                : 'bg-surface hover:bg-surface-2 border-line'
                                        )}
                                    >
                                        <div className="flex items-center justify-between gap-2 mb-1.5">
                                            <span className="text-xs font-mono text-amber-500 uppercase tracking-wider font-semibold">
                                                {t.domain}
                                            </span>
                                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-2 text-subtle border border-line">
                                                {t.badge}
                                            </span>
                                        </div>
                                        <h3 className="font-bold text-fg text-sm">{t.title}</h3>
                                        <p className="text-xs text-subtle line-clamp-2 mt-1">{t.starter}</p>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Defense Stakes & Configuration */}
                    <div className="space-y-4">
                        <Card className="p-5 border-line bg-surface space-y-5">
                            <h3 className="font-bold text-fg text-sm flex items-center gap-2">
                                <Shield className="w-4 h-4 text-accent" /> Defense Rigor
                            </h3>

                            <div className="grid grid-cols-3 gap-2">
                                {[
                                    { id: 'undergraduate', label: 'B.Tech', desc: '3 Rounds' },
                                    { id: 'masters', label: 'Master\'s', desc: '4 Rounds' },
                                    { id: 'phd', label: 'Doctoral', desc: '5 Rounds' },
                                ].map((d) => (
                                    <button
                                        key={d.id}
                                        type="button"
                                        onClick={() => setDifficulty(d.id)}
                                        className={cx(
                                            'p-2.5 rounded-xl border text-center transition-all',
                                            difficulty === d.id
                                                ? 'bg-accent/15 border-accent text-accent font-bold'
                                                : 'bg-surface-2 border-line text-subtle hover:text-fg'
                                        )}
                                    >
                                        <div className="text-xs">{d.label}</div>
                                        <div className="text-[10px] opacity-75">{d.desc}</div>
                                    </button>
                                ))}
                            </div>

                            {/* Tribunal Panel Preview */}
                            <div className="pt-2 border-t border-line space-y-2.5">
                                <span className="text-[11px] font-semibold text-subtle uppercase tracking-wider">Faculty Tribunal</span>
                                <div className="space-y-2">
                                    {professors.map((p) => (
                                        <div key={p.id} className="p-2.5 rounded-xl bg-surface-2/60 border border-line flex items-center gap-3">
                                            <span className="text-2xl">{p.avatar}</span>
                                            <div className="flex-1 min-w-0">
                                                <div className="font-bold text-fg text-xs flex items-center gap-1.5">
                                                    {p.name}
                                                    <span className="text-[10px] text-amber-500 font-mono">({p.title})</span>
                                                </div>
                                                <div className="text-[11px] text-subtle truncate mt-0.5">{p.vibe}</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <Button
                                className="w-full btn-primary py-3 gap-2 text-sm font-bold shadow-lg shadow-amber-500/10"
                                onClick={handleStart}
                                disabled={submitting || !selectedTopic}
                            >
                                <Flame className="w-4 h-4 text-amber-300" /> Enter The Hot Seat
                            </Button>
                        </Card>

                        {/* Recent Verdict Showcase */}
                        {activeSession && activeSession.status !== 'active' && (
                            <Card className={cx(
                                'p-5 border transition-all text-center',
                                activeSession.status === 'completed' ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-rose-500/40 bg-rose-500/5'
                            )}>
                                <div className="text-3xl mb-2">{activeSession.status === 'completed' ? '🎓' : '🔥'}</div>
                                <h4 className="font-extrabold text-lg text-fg">{activeSession.final_verdict}</h4>
                                <p className="text-xs text-subtle mt-1">{activeSession.feedback_summary}</p>
                                <div className="mt-3 inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold bg-surface border border-line">
                                    XP Awarded: +{activeSession.xp_awarded} XP
                                </div>
                            </Card>
                        )}
                    </div>
                </div>
            ) : (
                /* LIVE DEFENSE INTERROGATION CHAMBER */
                <div className="space-y-5 animate-rise">
                    {/* Top Status Bar: Composure & Timer */}
                    <Card className="p-4 border-line bg-surface/90 backdrop-blur-md flex flex-col md:flex-row items-center justify-between gap-4">
                        <div className="flex items-center gap-3 w-full md:w-auto">
                            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-500 font-black text-lg">
                                {activeSession.current_turn}/{activeSession.questions_total}
                            </div>
                            <div>
                                <div className="text-xs font-bold text-fg uppercase tracking-wide">
                                    Round {activeSession.current_turn} of {activeSession.questions_total}
                                </div>
                                <div className="text-xs text-subtle">{activeSession.subject}</div>
                            </div>
                        </div>

                        {/* Live Composure Gauge */}
                        <div className="flex-1 w-full max-w-md space-y-1.5">
                            <div className="flex items-center justify-between text-xs font-bold">
                                <span className="flex items-center gap-1.5 text-fg">
                                    <Activity className="w-3.5 h-3.5 text-amber-500" /> Candidate Composure
                                </span>
                                <span className={cx(
                                    activeSession.composure > 60 ? 'text-emerald-500' :
                                    activeSession.composure > 30 ? 'text-amber-500' : 'text-rose-500 animate-pulse'
                                )}>
                                    {activeSession.composure}%
                                </span>
                            </div>
                            <div className="h-2.5 rounded-full bg-surface-2 overflow-hidden border border-line">
                                <div
                                    className={cx('h-full transition-all duration-500 rounded-full', composureColor)}
                                    style={{ width: `${activeSession.composure}%` }}
                                />
                            </div>
                        </div>

                        {/* Countdown Timer */}
                        <div className={cx(
                            'flex items-center gap-2 px-3 py-1.5 rounded-xl border font-mono text-sm font-bold',
                            timerSec <= 10 ? 'bg-rose-500/15 border-rose-500/40 text-rose-500 animate-pulse' : 'bg-surface-2 border-line text-fg'
                        )}>
                            <Clock className="w-4 h-4" />
                            <span>{timerSec}s</span>
                        </div>
                    </Card>

                    {/* Active Questioning Professor Stage */}
                    <div className="relative p-6 md:p-8 rounded-3xl border border-amber-500/30 bg-surface/90 shadow-2xl overflow-hidden backdrop-blur-xl">
                        <div className="flex items-start gap-5">
                            <div className="text-5xl p-3 rounded-2xl bg-surface-2 border border-line shadow-inner shrink-0">
                                {currentProf?.avatar || '⚖️'}
                            </div>
                            <div className="space-y-2 flex-1">
                                <div className="flex items-center gap-2">
                                    <h3 className="font-extrabold text-fg text-base md:text-lg">{currentProf?.name}</h3>
                                    <span className="text-xs font-mono text-amber-500 px-2 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/20">
                                        {currentProf?.title}
                                    </span>
                                </div>
                                <p className="text-base md:text-xl font-medium text-fg leading-relaxed bg-surface-2/40 p-4 rounded-2xl border border-line">
                                    "{currentTurn?.question}"
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Candidate Answer Rebuttal Terminal */}
                    <form onSubmit={handleSubmitRebuttal} className="space-y-3">
                        <div className="relative">
                            <textarea
                                ref={answerInputRef}
                                value={answerText}
                                onChange={(e) => setAnswerText(e.target.value)}
                                placeholder="Formulate your defense argument with technical precision, invariants, and edge-case handling..."
                                rows={4}
                                disabled={submitting}
                                className="w-full p-4 rounded-2xl bg-surface border border-line focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 text-fg text-sm placeholder:text-subtle transition-all resize-none font-sans"
                            />
                            <div className="absolute bottom-3 right-3 flex items-center gap-2">
                                <span className="text-[11px] text-subtle font-mono">
                                    {answerText.trim().split(/\s+/).filter(Boolean).length} words
                                </span>
                            </div>
                        </div>

                        <div className="flex items-center justify-between gap-3">
                            <p className="text-xs text-subtle hidden sm:block">
                                Press Submit to face the faculty rebuttal and composure evaluation.
                            </p>
                            <Button
                                type="submit"
                                className="btn-primary ml-auto px-6 py-2.5 gap-2 text-sm font-bold shadow-lg shadow-amber-500/15"
                                disabled={submitting || !answerText.trim()}
                            >
                                <Send className="w-4 h-4" /> {submitting ? 'Faculty Deliberating...' : 'Submit Rebuttal'}
                            </Button>
                        </div>
                    </form>

                    {/* Previous Turns Commentary Log */}
                    {activeSession.turns?.length > 1 && (
                        <div className="pt-4 border-t border-line space-y-3">
                            <span className="text-xs font-bold text-subtle uppercase tracking-wider">Faculty Transcript</span>
                            <div className="space-y-2.5">
                                {activeSession.turns.slice(0, -1).map((t, idx) => (
                                    <div key={idx} className="p-3.5 rounded-2xl bg-surface-2/50 border border-line text-xs space-y-1.5">
                                        <div className="flex items-center justify-between text-subtle font-mono">
                                            <span>Round {t.turn} Rebuttal</span>
                                            <span className={cx('font-bold', t.score >= 75 ? 'text-emerald-500' : 'text-amber-500')}>
                                                Score: {t.score}/100 ({t.composure_delta >= 0 ? `+${t.composure_delta}` : t.composure_delta}% Composure)
                                            </span>
                                        </div>
                                        <p className="text-fg italic">"{t.answer}"</p>
                                        <p className="text-amber-500/90 font-medium pt-1 border-t border-line/40">
                                            Faculty Note: {t.feedback}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
