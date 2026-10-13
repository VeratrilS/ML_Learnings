import { Hammer, ArrowRight } from 'lucide-react';
import { Card, CardHeader } from './ui';
import { useApi } from '../lib/hooks';

export default function ForgeCard() {
    const { data } = useApi('/forge/inventory');
    const level = data?.forge_level || 1;
    const power = data?.total_power || 0;
    const count = data?.artifacts_count || 0;

    return (
        <Card className="card-pad hover:border-amber-500/40 transition-colors animate-rise">
            <CardHeader
                title="Commit Forge"
                subtitle="Code Alchemy & RPG Gear"
                icon={Hammer}
                action={
                    <span className="badge text-amber-500 bg-amber-500/10 border border-amber-500/20 font-bold font-mono">
                        LVL {level}
                    </span>
                }
            />

            <div className="grid grid-cols-3 gap-2 py-3 border-y border-line my-3 text-center">
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Artifacts</div>
                    <div className="text-lg font-extrabold text-fg tabular-nums mt-0.5">{count}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Gear Power</div>
                    <div className="text-lg font-extrabold text-amber-500 tabular-nums mt-0.5">{power}</div>
                </div>
                <div className="p-2 rounded-xl bg-surface-2/60">
                    <div className="text-[11px] text-subtle font-medium">Mastery</div>
                    <div className="text-lg font-extrabold text-accent tabular-nums mt-0.5">{level * 10}%</div>
                </div>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <p className="text-xs text-subtle truncate">
                    Transmute code snippets & commits into collectible RPG weapons and relics.
                </p>
                <a href="#/forge" className="btn btn-primary btn-sm shrink-0 gap-1">
                    Forge <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
