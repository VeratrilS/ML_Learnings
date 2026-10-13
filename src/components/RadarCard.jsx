import { Compass, TrendingUp, ArrowRight, Target } from 'lucide-react';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader } from './ui';

export default function RadarCard() {
    const { data } = useApi('/radar/elo');
    const overallElo = data?.overall_elo || 1200;
    const weakest = data?.weakest_topic;

    return (
        <Card className="card-pad border-emerald-500/20 bg-gradient-to-br from-surface to-emerald-500/10">
            <CardHeader
                title="Skill Radar & Elo"
                subtitle="DSA Topic Mastery & Diagnostics"
                icon={Compass}
                action={
                    <span className="badge text-emerald-400 bg-emerald-500/15 font-mono text-[11px] font-bold">
                        {overallElo} ELO
                    </span>
                }
            />

            {weakest && (
                <div className="p-2.5 rounded-xl bg-surface-2/60 border border-line mb-3 text-xs flex items-center justify-between">
                    <div>
                        <div className="text-[10px] text-subtle font-bold uppercase">Growth Priority</div>
                        <div className="font-bold text-sm text-emerald-400">{weakest.icon} {weakest.key}</div>
                    </div>
                    <span className="badge font-mono text-[10px]">{weakest.elo} Elo</span>
                </div>
            )}

            <div className="flex items-center gap-2">
                <Button
                    variant="primary"
                    size="sm"
                    icon={TrendingUp}
                    onClick={() => navigate('radar')}
                    className="flex-1 shadow-sm"
                >
                    View Topic Matrix
                </Button>
                <Button
                    variant="secondary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('radar')}
                >
                    Radar
                </Button>
            </div>
        </Card>
    );
}
