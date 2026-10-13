import { useState } from 'react';
import {
    Coins, Flame, Trophy, CheckCircle2, XCircle, Sparkles,
    RotateCcw, ArrowRight, Zap, Target
} from 'lucide-react';
import { Button, Card, ProgressBar, Skeleton, useToast, cx } from '../components/ui';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

// WebAudio Sound FX Generator
function playCasinoSfx(type) {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        const now = ctx.currentTime;

        if (type === 'jackpot') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(587.33, now);
            osc.frequency.setValueAtTime(880, now + 0.1);
            osc.frequency.setValueAtTime(1174.66, now + 0.2);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
            osc.start(now);
            osc.stop(now + 0.45);
        } else if (type === 'loss') {
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(250, now);
            osc.frequency.setValueAtTime(160, now + 0.15);
            gain.gain.setValueAtTime(0.1, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
            osc.start(now);
            osc.stop(now + 0.3);
        }
    } catch {
        // audio muted or unsupported
    }
}

export default function Complexity() {
    const toast = useToast();
    const challengesRes = useApi('/complexity/challenges');

    const challenges = challengesRes.data?.challenges || [];
    const player = challengesRes.data?.player || { chips: 500, current_streak: 0, best_streak: 0, total_guesses: 0, correct_guesses: 0, xp_earned: 0 };

    const [currentIndex, setCurrentIndex] = useState(0);
    const [wager, setWager] = useState(25);
    const [guessResult, setGuessResult] = useState(null);
    const [submitting, setSubmitting] = useState(false);

    const currentChallenge = challenges[currentIndex % Math.max(1, challenges.length)];

    const handleGuess = async (choice) => {
        if (!currentChallenge || submitting) return;
        setSubmitting(true);

        try {
            const res = await api('/complexity/guess', {
                method: 'POST',
                body: {
                    challenge_id: currentChallenge.id,
                    guessed_time: choice,
                    wager,
                },
            });
            const data = res.data;
            setGuessResult(data);

            if (data.correct) {
                playCasinoSfx('jackpot');
                toast.success('Jackpot!', `Correct! Won ${data.chips_delta} chips & +${data.xp_awarded} XP!`);
            } else {
                playCasinoSfx('loss');
                toast.error('Busted!', `Incorrect! Actual: ${data.actual_time}. Lost ${Math.abs(data.chips_delta)} chips.`);
            }
            challengesRes.reload();
        } catch (err) {
            toast.error('Guess failed', err.message);
        } finally {
            setSubmitting(false);
        }
    };

    const handleNext = () => {
        setGuessResult(null);
        setCurrentIndex((prev) => prev + 1);
    };

    const multiplier = (1.0 + Math.min(2.0, (player.current_streak) * 0.25)).toFixed(2);

    return (
        <div className="space-y-6 animate-fade-in max-w-4xl mx-auto pb-12">
            {/* Header Casino Hero */}
            <div className="relative overflow-hidden rounded-3xl border border-line bg-surface/80 p-6 md:p-8 backdrop-blur-xl shadow-2xl">
                <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20 mb-3">
                            <Coins className="w-3.5 h-3.5" /> High-Roller Big-O Shootout
                        </div>
                        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-fg flex items-center gap-3">
                            Complexity Casino
                        </h1>
                        <p className="text-sm md:text-base text-subtle mt-2 max-w-xl">
                            Wager chips on rapid-fire time and space complexities. Stack streaks to trigger 3x payout multipliers and Master of Asymptotics XP.
                        </p>
                    </div>

                    {/* Chips & Streak Dashboard */}
                    <div className="grid grid-cols-3 gap-3 bg-surface-2/60 p-3 rounded-2xl border border-line">
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Bankroll</div>
                            <div className="text-lg font-black text-amber-400 tabular-nums">🪙 {player.chips}</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Streak</div>
                            <div className="text-lg font-black text-rose-500 tabular-nums flex items-center justify-center gap-1">
                                <Flame className="w-4 h-4" /> {player.current_streak}
                            </div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Multiplier</div>
                            <div className="text-lg font-black text-accent tabular-nums">{multiplier}x</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Wager Selector & Card Chamber */}
            {currentChallenge ? (
                <div className="space-y-4 animate-rise">
                    {/* Wager Pill Selector */}
                    <div className="flex items-center justify-between gap-4 p-3 rounded-2xl bg-surface border border-line">
                        <span className="text-xs font-bold text-subtle uppercase tracking-wider flex items-center gap-1.5">
                            <Coins className="w-3.5 h-3.5 text-amber-400" /> Select Wager:
                        </span>
                        <div className="flex items-center gap-2">
                            {[10, 25, 50, 100].map((amt) => (
                                <button
                                    key={amt}
                                    type="button"
                                    onClick={() => setWager(amt)}
                                    className={cx(
                                        'px-3 py-1 rounded-xl text-xs font-bold border transition-all',
                                        wager === amt
                                            ? 'bg-amber-500/20 border-amber-500 text-amber-400 shadow-sm'
                                            : 'bg-surface-2 border-line text-subtle hover:text-fg'
                                    )}
                                >
                                    {amt} chips
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Mystery Code Snippet Terminal */}
                    <Card className="p-6 border-line bg-surface space-y-4">
                        <div className="flex items-center justify-between">
                            <span className="text-xs font-mono text-amber-500 font-bold uppercase tracking-wider">
                                Round {(currentIndex % challenges.length) + 1} of {challenges.length} · {currentChallenge.badge}
                            </span>
                            <h3 className="font-extrabold text-base text-fg">{currentChallenge.title}</h3>
                        </div>

                        <div className="rounded-2xl border border-line bg-black/90 p-5 font-mono text-xs text-emerald-400 overflow-x-auto shadow-inner">
                            <pre>{currentChallenge.code}</pre>
                        </div>

                        {/* Big-O Choice Buttons */}
                        {!guessResult ? (
                            <div className="space-y-2 pt-2">
                                <div className="text-xs font-bold text-subtle uppercase tracking-wider">What is the Time Complexity?</div>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                    {currentChallenge.choices.map((choice) => (
                                        <Button
                                            key={choice}
                                            type="button"
                                            disabled={submitting}
                                            onClick={() => handleGuess(choice)}
                                            className="btn-secondary py-3 text-xs font-mono font-bold hover:border-amber-500/50 hover:text-amber-400 transition-all"
                                        >
                                            {choice}
                                        </Button>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            /* Outcome Card with Proof Breakdown */
                            <div className={cx(
                                'p-5 rounded-2xl border space-y-3 animate-rise',
                                guessResult.correct ? 'bg-emerald-500/10 border-emerald-500/40' : 'bg-rose-500/10 border-rose-500/40'
                            )}>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        {guessResult.correct ? (
                                            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                                        ) : (
                                            <XCircle className="w-5 h-5 text-rose-500" />
                                        )}
                                        <h4 className="font-extrabold text-sm text-fg">
                                            {guessResult.correct ? 'Spot On!' : 'Missed!'}
                                        </h4>
                                    </div>
                                    <span className="font-mono text-xs font-bold text-amber-400">
                                        {guessResult.chips_delta >= 0 ? `+${guessResult.chips_delta}` : guessResult.chips_delta} chips
                                    </span>
                                </div>

                                <div className="text-xs text-subtle space-y-1 font-mono">
                                    <div><b>Actual Time:</b> <span className="text-emerald-400 font-bold">{guessResult.actual_time}</span></div>
                                    <div><b>Auxiliary Space:</b> <span className="text-sky-400 font-bold">{guessResult.actual_space}</span></div>
                                    <div className="font-sans text-xs pt-1.5 border-t border-line/40 text-subtle">
                                        <b>Proof:</b> {guessResult.proof}
                                    </div>
                                </div>

                                <Button
                                    className="w-full btn-primary py-2.5 text-xs font-bold mt-2"
                                    onClick={handleNext}
                                >
                                    Next Code Challenge <ArrowRight className="w-3.5 h-3.5" />
                                </Button>
                            </div>
                        )}
                    </Card>
                </div>
            ) : (
                <Skeleton className="h-80 rounded-3xl" />
            )}
        </div>
    );
}
