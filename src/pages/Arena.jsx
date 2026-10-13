import { useEffect, useState } from 'react';
import {
    Swords, RotateCcw, Play, Zap
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, cx } from '../components/ui';
import { play } from '../lib/sfx';

export default function Arena() {
    const oppApi = useApi('/arena/opponents');
    const statsApi = useApi('/arena/stats');

    const [selectedBot, setSelectedBot] = useState('speedy_py');
    const [matchState, setMatchState] = useState('idle'); // idle | fighting | finished
    const [questions, setQuestions] = useState([]);
    const [currentQIndex, setCurrentQIndex] = useState(0);
    const [userAnswers, setUserAnswers] = useState({});
    const [secondsLeft, setSecondsLeft] = useState(20);
    const [playerHp, setPlayerHp] = useState(100);
    const [botHp, setBotHp] = useState(100);
    const [matchResult, setMatchResult] = useState(null);
    const [activeBot, setActiveBot] = useState(null);

    const opponents = oppApi.data || [];

    // Round countdown
    useEffect(() => {
        let t = null;
        if (matchState === 'fighting' && secondsLeft > 0) {
            t = setInterval(() => {
                setSecondsLeft((s) => {
                    if (s <= 1) {
                        // Time out for this question
                        onSelectOption(-1);
                        return 20;
                    }
                    return s - 1;
                });
            }, 1000);
        }
        return () => clearInterval(t);
    }, [matchState, secondsLeft, currentQIndex]);

    const startMatch = async () => {
        play('bell');
        try {
            const res = await api('/arena/match/start', {
                method: 'POST',
                body: { bot_id: selectedBot },
            });
            if (res.data?.questions) {
                setQuestions(res.data.questions);
                setActiveBot(res.data.bot);
                setCurrentQIndex(0);
                setUserAnswers({});
                setPlayerHp(100);
                setBotHp(100);
                setSecondsLeft(20);
                setMatchResult(null);
                setMatchState('fighting');
            }
        } catch (e) {
            console.error(e);
        }
    };

    const onSelectOption = (optionIndex) => {
        play('jab');
        const q = questions[currentQIndex];
        const nextAnswers = { ...userAnswers, [q.id]: optionIndex };
        setUserAnswers(nextAnswers);

        // Immediate visual damage simulation
        if (optionIndex !== -1) {
            setBotHp((h) => Math.max(0, h - 20));
        } else {
            setPlayerHp((h) => Math.max(0, h - 25));
        }

        if (currentQIndex + 1 < questions.length) {
            setCurrentQIndex((i) => i + 1);
            setSecondsLeft(20);
        } else {
            finishMatch(nextAnswers);
        }
    };

    const finishMatch = async (finalAnswers) => {
        try {
            const res = await api('/arena/match/submit', {
                method: 'POST',
                body: { bot_id: selectedBot, answers: finalAnswers },
            });
            if (res.data) {
                setMatchResult(res.data);
                setMatchState('finished');
                if (res.data.won) {
                    play('combo');
                }
                statsApi.reload({ silent: true });
            }
        } catch (e) {
            console.error(e);
        }
    };

    const q = questions[currentQIndex];

    return (
        <div className="space-y-6 animate-rise">
            <header>
                <div className="eyebrow flex items-center gap-1.5 text-rose-500">
                    <Swords className="h-4 w-4" /> Code Duel Arena
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight">
                    1v1 Rapid-Fire Technical Battles
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Test your intuition, time complexity estimation, and distributed systems reflexes against AI rivals in high-speed 20-second rounds.
                </p>
            </header>

            {/* Combat Records */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-ok tabular-nums">{statsApi.data?.wins || 0}</div>
                    <div className="text-xs text-subtle mt-0.5">Victories</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-subtle tabular-nums">{statsApi.data?.losses || 0}</div>
                    <div className="text-xs text-subtle mt-0.5">Defeats</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold tabular-nums">{statsApi.data?.win_rate || 0}%</div>
                    <div className="text-xs text-subtle mt-0.5">Win Rate</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-rose-500 tabular-nums">{statsApi.data?.current_streak || 0}</div>
                    <div className="text-xs text-subtle mt-0.5">Win Streak</div>
                </Card>
            </div>

            {matchState === 'idle' && (
                <div className="space-y-4">
                    <h2 className="text-base font-bold tracking-tight">Select Opponent</h2>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
                        {opponents.map((bot) => (
                            <button
                                key={bot.id}
                                onClick={() => setSelectedBot(bot.id)}
                                className={cx(
                                    'card card-pad text-left flex flex-col justify-between transition-all border',
                                    selectedBot === bot.id
                                        ? 'border-rose-500 shadow-sm ring-1 ring-rose-500 bg-rose-500/5'
                                        : 'hover:border-line-strong'
                                )}
                            >
                                <div>
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-3xl">{bot.avatar}</span>
                                        <span className="badge text-xs font-mono font-bold text-rose-400">{bot.tier}</span>
                                    </div>
                                    <h3 className="font-bold text-sm">{bot.name}</h3>
                                    <p className="text-xs text-muted italic mt-1.5 leading-snug">"{bot.quote}"</p>
                                </div>
                                <div className="mt-4 pt-3 border-t border-line flex items-center justify-between text-xs font-mono">
                                    <span className="text-subtle">Accuracy: {Math.round(bot.accuracy * 100)}%</span>
                                    <span className="text-accent font-bold">+{bot.xp_win} XP</span>
                                </div>
                            </button>
                        ))}
                    </div>

                    <div className="flex justify-center pt-2">
                        <Button variant="primary" size="lg" icon={Play} onClick={startMatch} className="px-10 shadow-md">
                            Enter the Arena
                        </Button>
                    </div>
                </div>
            )}

            {matchState === 'fighting' && q && (
                <Card className="card-pad space-y-6 border-rose-500/30">
                    {/* Live Health Bars */}
                    <div className="grid grid-cols-2 gap-4 pb-4 border-b border-line">
                        <div>
                            <div className="flex justify-between items-center text-xs font-bold mb-1">
                                <span>YOU</span>
                                <span className="tabular-nums text-ok">{playerHp}%</span>
                            </div>
                            <div className="h-3 w-full rounded-full bg-surface-3 overflow-hidden">
                                <div className="h-full bg-ok transition-all duration-300" style={{ width: `${playerHp}%` }} />
                            </div>
                        </div>

                        <div>
                            <div className="flex justify-between items-center text-xs font-bold mb-1">
                                <span className="flex items-center gap-1">
                                    <span>{activeBot?.avatar}</span>
                                    <span>{activeBot?.name}</span>
                                </span>
                                <span className="tabular-nums text-rose-500">{botHp}%</span>
                            </div>
                            <div className="h-3 w-full rounded-full bg-surface-3 overflow-hidden">
                                <div className="h-full bg-rose-500 transition-all duration-300" style={{ width: `${botHp}%` }} />
                            </div>
                        </div>
                    </div>

                    {/* Question Header & Countdown */}
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-bold text-subtle uppercase">
                            Round {currentQIndex + 1} of {questions.length}
                        </span>
                        <div className={cx(
                            'text-sm font-mono font-bold px-3 py-1 rounded-full border tabular-nums',
                            secondsLeft <= 5 ? 'border-danger text-danger bg-danger/10 animate-pulse' : 'border-line bg-surface-2'
                        )}>
                            ⏱️ {secondsLeft}s
                        </div>
                    </div>

                    <div className="text-base sm:text-lg font-bold tracking-tight leading-relaxed">
                        {q.question}
                    </div>

                    {/* Multiple Choice Options */}
                    <div className="grid gap-2.5 sm:grid-cols-2">
                        {q.options.map((opt, optIdx) => (
                            <button
                                key={optIdx}
                                onClick={() => onSelectOption(optIdx)}
                                className="p-3.5 rounded-xl border border-line bg-surface hover:border-accent hover:bg-accent-soft/30 text-left font-medium text-sm transition-all flex items-start gap-3 active:scale-[0.99]"
                            >
                                <span className="grid place-items-center h-6 w-6 rounded-lg bg-surface-2 text-xs font-mono font-bold shrink-0">
                                    {String.fromCharCode(65 + optIdx)}
                                </span>
                                <span className="leading-snug flex-1">{opt}</span>
                            </button>
                        ))}
                    </div>
                </Card>
            )}

            {matchState === 'finished' && matchResult && (
                <Card className="card-pad text-center py-8 space-y-4 border-line">
                    <div className="text-5xl">{matchResult.won ? '🏆' : '💀'}</div>
                    <div>
                        <h2 className="text-2xl font-bold tracking-tight">
                            {matchResult.won ? 'VICTORY IN THE ARENA!' : 'DEFEATED BY ' + activeBot?.name}
                        </h2>
                        <p className="text-sm text-muted mt-1">
                            Your Score: {matchResult.player_score} / {questions.length} · Opponent Score: {matchResult.bot_score} / {questions.length}
                        </p>
                    </div>

                    <div className="inline-flex items-center gap-2 p-2 px-4 rounded-full border border-ok/30 bg-ok/10 text-ok font-bold text-sm">
                        <Zap className="h-4 w-4" /> +{matchResult.xp_awarded} XP Awarded
                    </div>

                    {/* Explanations List */}
                    <div className="space-y-2 text-left pt-4 max-w-2xl mx-auto border-t border-line">
                        <h3 className="text-xs font-bold text-subtle uppercase">Round Breakdowns:</h3>
                        {matchResult.results.map((r, i) => (
                            <div key={i} className="p-2.5 rounded-xl bg-surface-2/60 border border-line text-xs space-y-1">
                                <div className="flex items-center justify-between font-bold">
                                    <span>Round {i + 1}</span>
                                    <span className={r.player_correct ? 'text-ok' : 'text-danger'}>
                                        {r.player_correct ? '✓ Correct' : '✗ Missed'}
                                    </span>
                                </div>
                                <p className="text-muted leading-relaxed">{r.explanation}</p>
                            </div>
                        ))}
                    </div>

                    <div className="pt-4 flex justify-center gap-3">
                        <Button variant="primary" icon={RotateCcw} onClick={() => setMatchState('idle')}>
                            Battle Again
                        </Button>
                    </div>
                </Card>
            )}
        </div>
    );
}
