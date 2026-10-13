import { Flame, Play, Zap, ArrowRight } from 'lucide-react';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader } from './ui';

export default function SpeedrunCard() {
    const { data } = useApi('/speedrun/stats');
    const combo = data?.current_combo || 1.0;
    const totalMins = data?.total_minutes || 0;
    const todayDamage = data?.today_damage || 0;

    return (
        <Card className="card-pad border-amber-500/20 bg-gradient-to-br from-surface to-amber-500/10">
            <CardHeader
                title="Focus Speedrun"
                subtitle="Time-Trial Arena & Boss Damage"
                icon={Flame}
                action={
                    <span className="badge text-amber-500 bg-amber-500/15 font-mono font-bold">
                        <Zap className="h-3 w-3" /> {combo}x COMBO
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 p-2.5 rounded-xl bg-surface-2/60 border border-line mb-3 text-center">
                <div>
                    <div className="text-xl font-bold tabular-nums text-amber-500">{combo}x</div>
                    <div className="text-[10px] text-subtle font-medium">Multiplier</div>
                </div>
                <div>
                    <div className="text-xl font-bold tabular-nums">{totalMins}m</div>
                    <div className="text-[10px] text-subtle font-medium">Focus Logged</div>
                </div>
                <div>
                    <div className="text-xl font-bold tabular-nums text-rose-500">-{todayDamage}</div>
                    <div className="text-[10px] text-subtle font-medium">Boss Damage</div>
                </div>
            </div>

            <div className="flex items-center gap-2">
                <Button
                    variant="primary"
                    size="sm"
                    icon={Play}
                    onClick={() => navigate('speedrun')}
                    className="flex-1 shadow-sm"
                >
                    Start 25m Speedrun
                </Button>
                <Button
                    variant="secondary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('speedrun')}
                >
                    Arena
                </Button>
            </div>
        </Card>
    );
}
