import { Compass, TrendingUp, Target, Sparkles, Swords, Zap, ArrowRight, ShieldCheck } from 'lucide-react';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, cx } from '../components/ui';

const TIER_COLORS = {
    Bronze: 'border-amber-700/40 text-amber-500 bg-amber-700/10',
    Silver: 'border-slate-400/40 text-slate-300 bg-slate-400/10',
    Gold: 'border-yellow-500/40 text-yellow-400 bg-yellow-500/10',
    Diamond: 'border-cyan-400/40 text-cyan-300 bg-cyan-400/10',
};

export default function Radar() {
    const { data } = useApi('/radar/elo');
    const simApi = useApi('/radar/predict');

    const topics = data?.topics || [];
    const weakest = data?.weakest_topic;
    const recoveryPlan = data?.recovery_plan || [];
    const simulations = simApi.data || [];

    return (
        <div className="space-y-6 animate-rise">
            <header>
                <div className="eyebrow flex items-center gap-1.5 text-emerald-500">
                    <Compass className="h-4 w-4" /> Skill Radar & Elo Engine
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight">
                    DSA Topic Mastery & Contest Predictor
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Dynamic Elo ratings computed per DSA topic from your real solve history and Arena duel performances. Spot weak links and simulate contest outcomes.
                </p>
            </header>

            {/* Overall Rating Hero */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-emerald-400 tabular-nums">{data?.overall_elo || 1200}</div>
                    <div className="text-xs text-subtle mt-0.5">Overall DSA Elo</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold tabular-nums">{topics.length}</div>
                    <div className="text-xs text-subtle mt-0.5">Tracked Topics</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-cyan-400 tabular-nums">
                        {topics.filter((t) => t.tier === 'Gold' || t.tier === 'Diamond').length}
                    </div>
                    <div className="text-xs text-subtle mt-0.5">Gold+ Topics</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-rose-400 truncate">
                        {weakest ? weakest.short : 'None'}
                    </div>
                    <div className="text-xs text-subtle mt-0.5">Growth Focus</div>
                </Card>
            </div>

            {/* Topic Elo Matrix */}
            <div className="space-y-3">
                <h2 className="text-base font-bold tracking-tight">Topic Elo Matrix</h2>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {topics.map((t) => (
                        <Card key={t.key} className="card-pad flex flex-col justify-between hover:border-line-strong transition-all">
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-2xl">{t.icon}</span>
                                    <span className={cx('badge text-xs font-mono font-bold', TIER_COLORS[t.tier] || TIER_COLORS.Bronze)}>
                                        {t.tier}
                                    </span>
                                </div>
                                <h3 className="font-bold text-sm tracking-tight">{t.key}</h3>
                                <div className="flex items-baseline gap-2 mt-1">
                                    <span className="text-2xl font-bold tabular-nums text-fg">{t.elo}</span>
                                    <span className="text-xs text-subtle font-mono">Elo</span>
                                </div>
                            </div>
                            <div className="mt-4 pt-3 border-t border-line flex items-center justify-between text-xs text-subtle">
                                <span>{t.solved} Problems Solved</span>
                                <span className="font-mono text-emerald-400 font-medium">Rank {t.tier}</span>
                            </div>
                        </Card>
                    ))}
                </div>
            </div>

            {/* Weakest Topic Recovery Path */}
            {weakest && (
                <Card className="card-pad border-emerald-500/20 bg-gradient-to-br from-surface to-emerald-500/5">
                    <CardHeader
                        title={`Targeted Growth Sprint: ${weakest.key}`}
                        subtitle={`Boost your ${weakest.key} Elo from ${weakest.elo} with this 3-step triage drill`}
                        icon={Target}
                    />
                    <div className="space-y-2">
                        {recoveryPlan.map((r) => (
                            <div key={r.step} className="flex items-center justify-between p-3 rounded-xl bg-surface-2/60 border border-line text-xs">
                                <div className="flex items-center gap-3">
                                    <span className="grid place-items-center h-6 w-6 rounded-lg bg-surface font-mono font-bold shrink-0">
                                        {r.step}
                                    </span>
                                    <span className="font-medium text-fg">{r.action}</span>
                                </div>
                                <span className="badge text-emerald-400 font-mono font-bold shrink-0">+{r.xp} XP</span>
                            </div>
                        ))}
                    </div>
                </Card>
            )}

            {/* Contest Performance Simulator */}
            <Card className="card-pad">
                <CardHeader
                    title="Contest Rating Predictor"
                    subtitle="Simulated rating adjustments based on solve counts in 90-minute contests"
                    icon={TrendingUp}
                />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {simulations.map((s) => (
                        <div key={s.solves} className="p-3 rounded-xl bg-surface-2/60 border border-line text-center">
                            <div className="text-base font-bold mb-1">{s.solves} Solves</div>
                            <div className="text-sm font-bold font-mono text-emerald-400">{s.predicted_cf_delta > 0 ? `+${s.predicted_cf_delta}` : s.predicted_cf_delta} CF</div>
                            <div className="text-xs font-mono text-subtle">{s.predicted_lc_delta > 0 ? `+${s.predicted_lc_delta}` : s.predicted_lc_delta} LC</div>
                            <span className="badge text-[10px] uppercase font-bold mt-2">{s.rating_band}</span>
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    );
}
