import { GraduationCap, ArrowRight } from 'lucide-react';
import { Card, CardHeader } from './ui';
import { useApi } from '../lib/hooks';

export default function HotSeatCard() {
    const { data } = useApi('/hotseat/history');
    const stats = data?.stats || { total_defenses: 0, passed: 0, avg_composure: 0, total_xp: 0, best_verdict: 'None' };

    const passRate = stats.total_defenses > 0
        ? Math.round((stats.passed / stats.total_defenses) * 100)
        : 0;

    return (
        <Card className="card-pad hover:border-amber-500/40 transition-colors animate-rise">
            <CardHeader
                title="The Hot Seat"
                subtitle="Oral Defense & Viva Tribunal"
                icon={GraduationCap}
                action={
                    <span className="badge text-amber-500 bg-amber-500/10 border border-amber-500/20 font-bold font-mono">
                        {stats.best_verdict !== 'None' ? stats.best_verdict : 'Tribunal Ready'}
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 py-3 border-y border-line my-3 text-center">
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Defenses</div>
                    <div className="text-lg font-extrabold text-fg tabular-nums mt-0.5">{stats.total_defenses}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Pass Rate</div>
                    <div className="text-lg font-extrabold text-emerald-500 tabular-nums mt-0.5">{passRate}%</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Earned XP</div>
                    <div className="text-lg font-extrabold text-accent tabular-nums mt-0.5">+{stats.total_xp}</div>
                </div>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <p className="text-xs text-subtle truncate">
                    Defend algorithms, architecture, and invariants against 3 demanding AI professors.
                </p>
                <a href="#/hotseat" className="btn btn-primary btn-sm shrink-0 gap-1">
                    Defend <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
