import { Trophy, ArrowRight, Zap } from 'lucide-react';
import { Card, CardHeader } from './ui';
import { useApi } from '../lib/hooks';

export default function CenturyCard() {
    const { data } = useApi('/century/catalog');
    const stats = data?.stats || { total_features: 100, used_features: 0, mastered_features: 0, completion_pct: 0 };

    return (
        <Card className="card-pad hover:border-accent/40 transition-colors animate-rise">
            <CardHeader
                title="Century Command"
                subtitle="100 Engineering Beta Features"
                icon={Trophy}
                action={
                    <span className="badge text-accent bg-accent-soft border border-accent/20 font-bold font-mono">
                        {stats.completion_pct}% Mastered
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 py-3 border-y border-line my-3 text-center">
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Catalog</div>
                    <div className="text-lg font-extrabold text-fg tabular-nums mt-0.5">100</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Activated</div>
                    <div className="text-lg font-extrabold text-accent tabular-nums mt-0.5">{stats.used_features}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Mastered</div>
                    <div className="text-lg font-extrabold text-amber-500 tabular-nums mt-0.5">{stats.mastered_features}</div>
                </div>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <p className="text-xs text-subtle truncate">
                    Explore and command the complete suite of 100 engineering & learning beta tools.
                </p>
                <a href="#/century" className="btn btn-primary btn-sm shrink-0 gap-1">
                    Command <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
