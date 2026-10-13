import { Swords, ArrowRight } from 'lucide-react';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader } from './ui';

export default function ArenaCard() {
    const { data } = useApi('/arena/stats');
    const wins = data?.wins || 0;
    const streak = data?.current_streak || 0;
    const winRate = data?.win_rate || 0;

    return (
        <Card className="card-pad border-rose-500/20 bg-gradient-to-br from-surface to-rose-500/10">
            <CardHeader
                title="Code Duel Arena"
                subtitle="1v1 Rapid-Fire Technical Battles"
                icon={Swords}
                action={
                    streak > 0 && (
                        <span className="badge text-rose-400 bg-rose-500/15 font-mono text-[11px] font-bold">
                            {streak} WIN STREAK
                        </span>
                    )
                }
            />

            <div className="grid grid-cols-3 gap-2 p-2.5 rounded-xl bg-surface-2/60 border border-line mb-3 text-center">
                <div>
                    <div className="text-xl font-bold tabular-nums text-ok">{wins}</div>
                    <div className="text-[10px] text-subtle font-medium">Victories</div>
                </div>
                <div>
                    <div className="text-xl font-bold tabular-nums">{winRate}%</div>
                    <div className="text-[10px] text-subtle font-medium">Win Rate</div>
                </div>
                <div>
                    <div className="text-xl font-bold tabular-nums text-rose-400">{streak}</div>
                    <div className="text-[10px] text-subtle font-medium">Streak</div>
                </div>
            </div>

            <div className="flex items-center gap-2">
                <Button
                    variant="primary"
                    size="sm"
                    icon={Swords}
                    onClick={() => navigate('arena')}
                    className="flex-1 shadow-sm"
                >
                    Duel AI Bot
                </Button>
                <Button
                    variant="secondary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('arena')}
                >
                    Arena
                </Button>
            </div>
        </Card>
    );
}
