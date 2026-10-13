import { Coins, Flame, ArrowRight } from 'lucide-react';
import { Card, CardHeader } from './ui';
import { useApi } from '../lib/hooks';

export default function ComplexityCard() {
    const { data } = useApi('/complexity/challenges');
    const player = data?.player || { chips: 500, current_streak: 0, best_streak: 0, total_guesses: 0, correct_guesses: 0, xp_earned: 0 };

    const winRate = player.total_guesses > 0
        ? Math.round((player.correct_guesses / player.total_guesses) * 100)
        : 0;

    return (
        <Card className="card-pad hover:border-amber-500/40 transition-colors animate-rise">
            <CardHeader
                title="Complexity Casino"
                subtitle="Big-O Shootout & Betting"
                icon={Coins}
                action={
                    <span className="badge text-amber-400 bg-amber-500/10 border border-amber-500/20 font-bold font-mono">
                        🪙 {player.chips}
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 py-3 border-y border-line my-3 text-center">
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Bankroll</div>
                    <div className="text-lg font-extrabold text-amber-400 tabular-nums mt-0.5">🪙 {player.chips}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Streak</div>
                    <div className="text-lg font-extrabold text-rose-500 tabular-nums mt-0.5 flex items-center justify-center gap-0.5">
                        <Flame className="w-4 h-4" /> {player.current_streak}
                    </div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Win Rate</div>
                    <div className="text-lg font-extrabold text-accent tabular-nums mt-0.5">{winRate}%</div>
                </div>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <p className="text-xs text-subtle truncate">
                    Bet chips on rapid-fire time and space complexities.
                </p>
                <a href="#/complexity" className="btn btn-primary btn-sm shrink-0 gap-1">
                    Play <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
