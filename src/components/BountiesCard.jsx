import { Sparkles, Dices, ArrowRight, CheckCircle2 } from 'lucide-react';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader } from './ui';

export default function BountiesCard() {
    const { data } = useApi('/bounties/today');
    const bounties = data?.bounties || [];
    const completed = data?.completed_count || 0;
    const total = data?.total_count || 4;
    const gacha = data?.gacha;

    return (
        <Card className="card-pad border-purple-500/20 bg-gradient-to-br from-surface to-purple-500/10">
            <CardHeader
                title="Daily Bounties & Gacha"
                subtitle="High-Stakes Contracts & Mystery Rolls"
                icon={Sparkles}
                action={
                    <span className="badge text-purple-400 bg-purple-500/15 font-mono text-[11px]">
                        {completed}/{total} COMPLETED
                    </span>
                }
            />

            <div className="space-y-1.5 mb-3">
                {bounties.slice(0, 2).map((b) => (
                    <div key={b.id} className="flex items-center justify-between p-2 rounded-lg bg-surface-2/60 border border-line text-xs">
                        <div className="flex items-center gap-1.5 truncate">
                            {b.claimed ? (
                                <CheckCircle2 className="h-3.5 w-3.5 text-ok shrink-0" />
                            ) : (
                                <span className="h-2 w-2 rounded-full bg-accent shrink-0" />
                            )}
                            <span className={b.claimed ? 'line-through text-subtle truncate' : 'font-medium truncate'}>
                                {b.title}
                            </span>
                        </div>
                        <span className="badge font-mono text-[10px] shrink-0 font-bold">+{b.xp} XP</span>
                    </div>
                ))}
            </div>

            <div className="flex items-center gap-2">
                <Button
                    variant="primary"
                    size="sm"
                    icon={Dices}
                    onClick={() => navigate('bounties')}
                    className="flex-1 shadow-sm"
                >
                    {gacha?.has_pulled_today ? 'View Today’s Roll' : 'Daily Gacha Spin'}
                </Button>
                <Button
                    variant="secondary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('bounties')}
                >
                    Board
                </Button>
            </div>
        </Card>
    );
}
