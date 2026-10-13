import { RotateCcw, Brain, ArrowRight } from 'lucide-react';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader } from './ui';

export default function DrillmasterCard() {
    const { data } = useApi('/drillmaster/deck');
    const dueCount = data?.due_count || 0;
    const total = data?.total_cards || 0;
    const masteryRate = data?.mastery_rate || 0;

    return (
        <Card className="card-pad border-cyan-500/20 bg-gradient-to-br from-surface to-cyan-500/10">
            <CardHeader
                title="SM-2 Drillmaster"
                subtitle="SuperMemo Active Recall Engine"
                icon={RotateCcw}
                action={
                    <span className="badge text-cyan-400 bg-cyan-500/15 font-mono text-[11px] font-bold">
                        {dueCount} DUE TODAY
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 p-2.5 rounded-xl bg-surface-2/60 border border-line mb-3 text-center">
                <div>
                    <div className="text-xl font-bold tabular-nums text-cyan-400">{dueCount}</div>
                    <div className="text-[10px] text-subtle font-medium">Due Now</div>
                </div>
                <div>
                    <div className="text-xl font-bold tabular-nums">{masteryRate}%</div>
                    <div className="text-[10px] text-subtle font-medium">Mastery</div>
                </div>
                <div>
                    <div className="text-xl font-bold tabular-nums">{total}</div>
                    <div className="text-[10px] text-subtle font-medium">Deck Size</div>
                </div>
            </div>

            <div className="flex items-center gap-2">
                <Button
                    variant="primary"
                    size="sm"
                    icon={Brain}
                    onClick={() => navigate('drillmaster')}
                    className="flex-1 shadow-sm"
                >
                    {dueCount > 0 ? `Review ${dueCount} Cards` : 'Open Drillmaster'}
                </Button>
                <Button
                    variant="secondary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('drillmaster')}
                >
                    Deck
                </Button>
            </div>
        </Card>
    );
}
