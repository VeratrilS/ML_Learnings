import { Bug, ArrowRight, ShieldAlert, Award } from 'lucide-react';
import { Card, CardHeader } from './ui';
import { useApi } from '../lib/hooks';

export default function BugHuntCard() {
    const { data } = useApi('/bughunt/stats');
    const stats = data?.stats || { total_attempts: 0, solved_cases: 0, total_cases: 5, total_xp: 0, rank: 'Trainee Detective' };

    return (
        <Card className="card-pad hover:border-rose-500/40 transition-colors animate-rise">
            <CardHeader
                title="Bug Hunt"
                subtitle="Forensic Code Autopsies"
                icon={Bug}
                action={
                    <span className="badge text-rose-500 bg-rose-500/10 border border-rose-500/20 font-bold font-mono">
                        {stats.solved_cases}/{stats.total_cases} Solved
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 py-3 border-y border-line my-3 text-center">
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Rank</div>
                    <div className="text-xs font-black text-amber-500 truncate mt-0.5">{stats.rank}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Attempts</div>
                    <div className="text-lg font-extrabold text-fg tabular-nums mt-0.5">{stats.total_attempts}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Bounty XP</div>
                    <div className="text-lg font-extrabold text-accent tabular-nums mt-0.5">+{stats.total_xp}</div>
                </div>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <p className="text-xs text-subtle truncate">
                    Forensic autopsy of notorious real-world FAANG production crashes.
                </p>
                <a href="#/bughunt" className="btn btn-primary btn-sm shrink-0 gap-1">
                    Hunt <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
