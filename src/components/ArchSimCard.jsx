import { Network, ArrowRight, Activity, Flame } from 'lucide-react';
import { Card, CardHeader } from './ui';

export default function ArchSimCard() {
    return (
        <Card className="card-pad hover:border-accent/40 transition-colors animate-rise">
            <CardHeader
                title="Architecture Stress Lab"
                subtitle="Distributed System Simulator"
                icon={Network}
                action={
                    <span className="badge text-blue-400 bg-blue-500/10 border border-blue-500/20 font-bold">
                        100K RPS
                    </span>
                }
            />

            <div className="p-3 rounded-xl bg-surface-2/60 border border-line my-3 space-y-1.5 text-xs">
                <div className="flex items-center gap-1.5 text-accent font-semibold">
                    <Activity className="h-3.5 w-3.5" /> CDN · Load Balancer · Redis · DB Replicas
                </div>
                <p className="text-subtle leading-relaxed">
                    Test P99 latency thresholds and inject Black Friday flash sales and database primary outages.
                </p>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <span className="text-[11px] text-subtle flex items-center gap-1">
                    <Flame className="h-3 w-3 text-rose-400" /> Chaos Monkey Included
                </span>
                <a href="#/archsim" className="btn btn-primary btn-sm shrink-0 gap-1 font-semibold">
                    Simulate <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
