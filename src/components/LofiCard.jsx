import { Headphones, ArrowRight, Clock } from 'lucide-react';
import { Card, CardHeader } from './ui';
import { useApi } from '../lib/hooks';

export default function LofiCard() {
    const { data } = useApi('/lofi/stats');
    const stats = data?.stats || { total_minutes: 0, total_hours: 0, sessions_count: 0, total_xp: 0 };

    return (
        <Card className="card-pad hover:border-indigo-500/40 transition-colors animate-rise">
            <CardHeader
                title="Neural Lo-Fi"
                subtitle="Generative Focus Soundscapes"
                icon={Headphones}
                action={
                    <span className="badge text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 font-bold font-mono">
                        {stats.total_hours}h Flow
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 py-3 border-y border-line my-3 text-center">
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Focus Hours</div>
                    <div className="text-lg font-extrabold text-indigo-400 tabular-nums mt-0.5">{stats.total_hours}h</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Sessions</div>
                    <div className="text-lg font-extrabold text-fg tabular-nums mt-0.5">{stats.sessions_count}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Earned XP</div>
                    <div className="text-lg font-extrabold text-accent tabular-nums mt-0.5">+{stats.total_xp}</div>
                </div>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <p className="text-xs text-subtle truncate">
                    Binaural alpha waves, cyberpunk drones, and rain pink noise for deep work.
                </p>
                <a href="#/lofi" className="btn btn-primary btn-sm shrink-0 gap-1">
                    Listen <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
