import { Flame, Zap, ArrowRight, CheckCircle2 } from 'lucide-react';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader } from './ui';

export default function DempseyCard() {
    const { data } = useApi('/dempsey/status');
    const habits = data?.habits || [];
    const completed = data?.completed_count || 0;
    const feverActive = data?.fever_active;

    return (
        <Card className="card-pad border-orange-500/20 bg-gradient-to-br from-surface to-orange-500/10">
            <CardHeader
                title="Dempsey Roll"
                subtitle="Daily Momentum & 2x XP Fever"
                icon={Flame}
                action={
                    feverActive ? (
                        <span className="badge text-orange-400 bg-orange-500/20 font-mono font-bold animate-pulse">
                            🔥 2X FEVER ACTIVE
                        </span>
                    ) : (
                        <span className="badge text-subtle bg-surface-2 font-mono text-[11px]">
                            {completed}/4 HABITS
                        </span>
                    )
                }
            />

            <div className="grid grid-cols-4 gap-1.5 p-2 rounded-xl bg-surface-2/60 border border-line mb-3 text-center">
                {habits.map((h) => (
                    <div key={h.id} className="p-1.5 rounded-lg bg-surface/60 flex flex-col items-center">
                        <span className="text-base">{h.done ? '🥊' : '⚪'}</span>
                        <span className={h.done ? 'text-[10px] font-bold text-orange-400 truncate w-full mt-0.5' : 'text-[10px] text-subtle truncate w-full mt-0.5'}>
                            {h.label.split(' ')[0]}
                        </span>
                    </div>
                ))}
            </div>

            <div className="flex items-center gap-2">
                <Button
                    variant="primary"
                    size="sm"
                    icon={Zap}
                    onClick={() => navigate('dempsey')}
                    className="flex-1 shadow-sm bg-orange-600 hover:bg-orange-500 text-white"
                >
                    {feverActive ? 'Fever Mode Active!' : completed === 4 ? 'Unleash Dempsey Roll!' : 'Track Momentum'}
                </Button>
                <Button
                    variant="secondary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('dempsey')}
                >
                    View
                </Button>
            </div>
        </Card>
    );
}
