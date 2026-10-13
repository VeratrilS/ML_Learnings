import { Timer, Play } from 'lucide-react';
import { Card, CardHeader } from './ui';
import { useApi } from '../lib/hooks';

export default function GhostCard() {
    const { data } = useApi('/ghost/profile');
    const stats = data?.stats || { ghost_elo: 1200, ghost_wins: 0, top_wpm: 0, avg_wpm: 0 };

    return (
        <Card className="card-pad hover:border-accent/40 transition-colors animate-rise">
            <CardHeader
                title="Ghost Racer"
                subtitle="Code Time Trial & Muscle Memory"
                icon={Timer}
                action={
                    <span className="badge text-accent bg-accent/10 border border-accent/20 font-mono font-bold">
                        {stats.ghost_elo} ELO
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 py-3 border-y border-line my-3 text-center">
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Ghost Wins</div>
                    <div className="text-lg font-extrabold text-ok tabular-nums mt-0.5">{stats.ghost_wins}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Peak WPM</div>
                    <div className="text-lg font-extrabold text-accent tabular-nums mt-0.5">{stats.top_wpm}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Avg Pace</div>
                    <div className="text-lg font-extrabold text-fg tabular-nums mt-0.5">{stats.avg_wpm}</div>
                </div>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <p className="text-xs text-subtle truncate">
                    Race your personal best ghost in high-speed algorithm typing.
                </p>
                <a href="#/ghost" className="btn btn-primary btn-sm shrink-0 gap-1.5">
                    <Play className="h-3.5 w-3.5 fill-current" /> Race
                </a>
            </div>
        </Card>
    );
}
