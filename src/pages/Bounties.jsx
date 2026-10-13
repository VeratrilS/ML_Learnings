import { useState } from 'react';
import {
    Sparkles, Dices, CheckCircle2, ExternalLink, Bot, Check, Trophy
} from 'lucide-react';
import { api } from '../lib/api';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, Spinner, cx } from '../components/ui';
import { play } from '../lib/sfx';

const RARITY_COLORS = {
    Common: 'border-slate-500/40 text-slate-300 bg-slate-500/10 shadow-slate-500/10',
    Rare: 'border-blue-500/40 text-blue-400 bg-blue-500/10 shadow-blue-500/15',
    Epic: 'border-purple-500/50 text-purple-400 bg-purple-500/15 shadow-purple-500/20',
    Legendary: 'border-amber-500/60 text-amber-400 bg-amber-500/20 shadow-amber-500/30',
};

export default function Bounties() {
    const { data, reload } = useApi('/bounties/today');
    const [rolling, setRolling] = useState(false);
    const [pulledCard, setPulledCard] = useState(null);
    const [claimingId, setClaimingId] = useState(null);

    const bounties = data?.bounties || [];
    const gacha = data?.gacha;
    const currentPull = pulledCard || gacha?.today_pull;

    const spinGacha = async () => {
        setRolling(true);
        play('bell');
        try {
            const res = await api('/bounties/gacha/pull', { method: 'POST' });
            if (res.data?.pull) {
                setTimeout(() => {
                    play('combo');
                    setPulledCard(res.data.pull);
                    setRolling(false);
                    reload({ silent: true });
                }, 1000);
            }
        } catch (e) {
            console.error(e);
            setRolling(false);
        }
    };

    const claimBounty = async (bountyId) => {
        setClaimingId(bountyId);
        play('combo');
        try {
            await api('/bounties/claim', {
                method: 'POST',
                body: { bounty_id: bountyId },
            });
            reload({ silent: true });
        } catch (e) {
            console.error(e);
        } finally {
            setClaimingId(null);
        }
    };

    return (
        <div className="space-y-6 animate-rise">
            <header>
                <div className="eyebrow flex items-center gap-1.5 text-purple-400">
                    <Sparkles className="h-4 w-4" /> Daily Contracts & Gacha
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight">
                    DSA Gacha & Bounty Contracts
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    High-stakes daily bounty contracts and mystery problem rolls with rarity tiers. Solve your contracts and draw your daily lucky card.
                </p>
            </header>

            {/* Mystery Gacha Section */}
            <Card className="card-pad border-purple-500/20 bg-gradient-to-br from-surface via-surface to-purple-500/10 relative overflow-hidden">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
                    <div className="space-y-2 text-center sm:text-left">
                        <div className="flex items-center justify-center sm:justify-start gap-2">
                            <Dices className="h-5 w-5 text-purple-400" />
                            <h2 className="text-lg font-bold tracking-tight">Daily Mystery DSA Pull</h2>
                        </div>
                        <p className="text-xs text-muted max-w-md">
                            One free gacha pull every IST day. Draw from our 200+ curated vault with weighted rarity tiers: Common (30%), Rare (45%), Epic (18%), and Legendary (7%).
                        </p>
                        <div className="flex flex-wrap justify-center sm:justify-start gap-1.5 text-[10px] font-mono font-semibold pt-1">
                            <span className="px-2 py-0.5 rounded border border-slate-500/30 text-slate-400">⚪ COMMON</span>
                            <span className="px-2 py-0.5 rounded border border-blue-500/30 text-blue-400">🔵 RARE</span>
                            <span className="px-2 py-0.5 rounded border border-purple-500/30 text-purple-400">🟣 EPIC</span>
                            <span className="px-2 py-0.5 rounded border border-amber-500/30 text-amber-400">🟡 LEGENDARY</span>
                        </div>
                    </div>

                    <div className="shrink-0">
                        {currentPull ? (
                            <div className={cx(
                                'p-4 rounded-2xl border text-center min-w-[220px] transition-all shadow-lg',
                                RARITY_COLORS[currentPull.rarity] || RARITY_COLORS.Common
                            )}>
                                <span className="text-xs uppercase font-mono tracking-widest font-bold block mb-1">
                                    ★ {currentPull.rarity} PULL ★
                                </span>
                                <div className="text-base font-bold tracking-tight truncate max-w-[200px] mx-auto">
                                    {currentPull.title}
                                </div>
                                <div className="text-[11px] text-subtle truncate mt-0.5">
                                    {currentPull.topic}
                                </div>
                                <div className="flex items-center justify-center gap-2 mt-3 pt-2 border-t border-line/40">
                                    {currentPull.link && (
                                        <a
                                            href={currentPull.link}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="btn btn-secondary btn-sm text-[11px] h-7"
                                        >
                                            <ExternalLink className="h-3 w-3" /> Solve
                                        </a>
                                    )}
                                    <button
                                        onClick={() => navigate('agents')}
                                        className="btn btn-primary btn-sm text-[11px] h-7"
                                    >
                                        <Bot className="h-3 w-3" /> Swarm
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <Button
                                variant="primary"
                                size="lg"
                                loading={rolling}
                                icon={rolling ? Spinner : Dices}
                                onClick={spinGacha}
                                className="px-6 shadow-md bg-purple-600 hover:bg-purple-500 text-white"
                            >
                                {rolling ? 'Spinning Vault…' : 'Pull Today’s Gacha'}
                            </Button>
                        )}
                    </div>
                </div>
            </Card>

            {/* Daily Bounty Contracts */}
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <h2 className="text-base font-bold tracking-tight flex items-center gap-2">
                        <Trophy className="h-4 w-4 text-accent" /> Active Daily Contracts ({data?.completed_count || 0}/{data?.total_count || 4})
                    </h2>
                    <span className="text-xs text-subtle font-mono">Refreshes Midnight IST</span>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                    {bounties.map((b) => (
                        <Card
                            key={b.id}
                            className={cx(
                                'card-pad flex flex-col justify-between border transition-all',
                                b.claimed ? 'bg-surface-2/40 opacity-75' : 'hover:border-line-strong'
                            )}
                        >
                            <div>
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <span className={cx('badge text-[11px] font-bold', b.color)}>
                                        {b.badge}
                                    </span>
                                    <span className="text-xs font-mono font-bold text-accent">
                                        +{b.xp} XP
                                    </span>
                                </div>
                                <h3 className="font-bold text-sm tracking-tight">{b.title}</h3>
                                <p className="text-xs text-muted mt-1 leading-relaxed">{b.desc}</p>
                            </div>

                            <div className="flex items-center justify-between pt-3 mt-4 border-t border-line">
                                <span className="text-[11px] text-subtle">
                                    {b.claimed ? 'Completed' : 'Available Today'}
                                </span>
                                {b.claimed ? (
                                    <span className="badge text-ok bg-ok/15 gap-1 font-semibold text-xs">
                                        <CheckCircle2 className="h-3.5 w-3.5" /> Claimed
                                    </span>
                                ) : (
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        loading={claimingId === b.id}
                                        icon={Check}
                                        onClick={() => claimBounty(b.id)}
                                    >
                                        Claim +{b.xp} XP
                                    </Button>
                                )}
                            </div>
                        </Card>
                    ))}
                </div>
            </div>
        </div>
    );
}
