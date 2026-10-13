import { useState } from 'react';
import {
    Hammer, Sparkles, Shield, Flame, Sword, Crown, Zap, ChevronRight,
    Award, Layers, ArrowUpCircle, RefreshCw, Wand2, Plus,
} from 'lucide-react';
import { Button, Card, ProgressBar, Skeleton, useToast, cx } from '../components/ui';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

const RARITY_COLORS = {
    Common: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/20',
    Rare: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    Epic: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    Legendary: 'text-amber-400 bg-amber-500/10 border-amber-500/20 shadow-amber-500/10',
    Mythic: 'text-rose-400 bg-rose-500/10 border-rose-500/20 shadow-rose-500/15',
};

const SLOT_ICONS = {
    Weapon: Sword,
    Shield: Shield,
    Relic: Crown,
    Ring: Sparkles,
};

const PRESETS = [
    {
        name: 'Binary Search Algorithm',
        code: `def binary_search(arr: list[int], target: int) -> int:
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1`,
    },
    {
        name: 'Fast Two-Pointer Traversal',
        code: `def two_sum_sorted(nums: list[int], target: int) -> list[int]:
    i, j = 0, len(nums) - 1
    while i < j:
        s = nums[i] + nums[j]
        if s == target:
            return [i, j]
        elif s < target:
            i += 1
        else:
            j -= 1
    return []`,
    },
    {
        name: 'Dijkstra Priority Queue Engine',
        code: `import heapq

def dijkstra(graph, start):
    distances = {node: float('inf') for node in graph}
    distances[start] = 0
    pq = [(0, start)]
    while pq:
        curr_dist, curr_node = heapq.heappop(pq)
        if curr_dist > distances[curr_node]:
            continue
        for neighbor, weight in graph[curr_node].items():
            dist = curr_dist + weight
            if dist < distances[neighbor]:
                distances[neighbor] = dist
                heapq.heappush(pq, (dist, neighbor))
    return distances`,
    },
];

export default function Forge() {
    const toast = useToast();
    const invRes = useApi('/forge/inventory');
    const data = invRes.data || { forge_level: 1, total_power: 0, artifacts: [] };

    const [code, setCode] = useState('');
    const [name, setName] = useState('');
    const [slot, setSlot] = useState('Weapon');
    const [forging, setForging] = useState(false);
    const [latestArtifact, setLatestArtifact] = useState(null);
    const [upgradingId, setUpgradingId] = useState(null);

    const handleTransmute = async (e) => {
        e?.preventDefault?.();
        if (!code.trim() || code.length < 15) {
            toast('Enter at least 15 characters of code to alchemize.', 'error');
            return;
        }

        setForging(true);
        try {
            const res = await api('/forge/transmute', {
                method: 'POST',
                body: { code: code.trim(), name: name.trim(), slot },
            });

            if (res?.artifact) {
                setLatestArtifact(res.artifact);
                toast(`Forged ${res.artifact.rarity} ${res.artifact.name}! +${res.xp?.awarded || 50} XP`, 'success');
                setCode('');
                setName('');
                invRes.reload({ silent: true });
            }
        } catch (err) {
            toast(err.message || 'Transmutation failed', 'error');
        } finally {
            setForging(false);
        }
    };

    const handleUpgrade = async (id) => {
        setUpgradingId(id);
        try {
            const res = await api(`/forge/upgrade/${id}`, { method: 'POST' });
            if (res?.artifact) {
                toast(`Upgraded ${res.artifact.name} to Level ${res.artifact.level}!`, 'success');
                invRes.reload({ silent: true });
            }
        } catch (err) {
            toast(err.message || 'Upgrade failed', 'error');
        } finally {
            setUpgradingId(null);
        }
    };

    return (
        <div className="space-y-6 animate-rise">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
                <div>
                    <div className="flex items-center gap-2">
                        <span className="badge text-amber-500 bg-amber-500/10 border border-amber-500/20">Beta Lab · Code Alchemy</span>
                        <span className="badge text-accent bg-accent/10 border border-accent/20 font-mono font-bold">
                            Forge Rank {data.forge_level}
                        </span>
                    </div>
                    <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight mt-1.5 flex items-center gap-2.5">
                        <Hammer className="h-7 w-7 text-amber-500" /> Commit Forge
                    </h1>
                    <p className="text-sm text-muted mt-1 max-w-2xl">
                        Alchemize real code, algorithms, and git snippets into collectible RPG equipment with algorithmic stat scaling.
                    </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                    <div className="px-3 py-1.5 rounded-xl bg-surface-2 border border-line flex items-center gap-3 text-xs">
                        <div>
                            <span className="text-subtle">Total Gear:</span> <b className="text-fg font-mono">{data.artifacts?.length || 0}</b>
                        </div>
                        <div className="h-3 w-px bg-line" />
                        <div>
                            <span className="text-subtle">Power:</span> <b className="text-amber-500 font-mono">{data.total_power}</b>
                        </div>
                    </div>
                </div>
            </div>

            {/* The Crucible - Transmutation Form */}
            <Card className="card-pad border-amber-500/30 bg-gradient-to-b from-surface via-surface to-amber-500/[0.02]">
                <form onSubmit={handleTransmute} className="space-y-4">
                    <div className="flex items-center justify-between gap-2 border-b border-line pb-2.5">
                        <div className="flex items-center gap-2">
                            <span className="grid place-items-center h-6 w-6 rounded-md bg-amber-500/15 text-amber-500">
                                <Flame className="h-3.5 w-3.5" />
                            </span>
                            <span className="text-sm font-bold text-fg">The Alchemical Crucible</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <span className="text-[11px] text-subtle hidden sm:inline">Try preset:</span>
                            {PRESETS.map((p, idx) => (
                                <button
                                    key={idx}
                                    type="button"
                                    onClick={() => {
                                        setCode(p.code);
                                        setName(p.name);
                                    }}
                                    className="btn btn-ghost btn-xs text-subtle hover:text-fg"
                                >
                                    #{idx + 1}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="sm:col-span-2">
                            <label className="label" htmlFor="forge-name">Artifact Title (Optional)</label>
                            <input
                                id="forge-name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder="e.g. Scythe of Async Concurrency (leave blank to auto-roll)"
                                className="input text-xs"
                                maxLength={100}
                            />
                        </div>
                        <div>
                            <label className="label">Gear Slot</label>
                            <div className="grid grid-cols-4 gap-1">
                                {Object.keys(SLOT_ICONS).map((s) => {
                                    const Icon = SLOT_ICONS[s];
                                    return (
                                        <button
                                            key={s}
                                            type="button"
                                            onClick={() => setSlot(s)}
                                            className={cx(
                                                'p-2 rounded-xl border text-center transition-all flex flex-col items-center gap-1 text-[11px] font-semibold',
                                                slot === s
                                                    ? 'border-amber-500 bg-amber-500/10 text-amber-500 shadow-xs'
                                                    : 'border-line hover:border-line-strong bg-surface text-subtle hover:text-fg'
                                            )}
                                        >
                                            <Icon className="h-3.5 w-3.5" />
                                            <span>{s}</span>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    <div>
                        <label className="label" htmlFor="forge-code">Code &amp; Algorithm Essence *</label>
                        <textarea
                            id="forge-code"
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            rows={7}
                            placeholder="Paste Python, TypeScript, C++, or SQL algorithm snippet here to forge into RPG gear..."
                            className="input font-mono text-xs leading-relaxed resize-y"
                            required
                        />
                    </div>

                    <div className="flex items-center justify-between gap-3 pt-2">
                        <p className="text-xs text-subtle">
                            Quality, AST depth, typing, and efficiency dictate rarity and RPG stats.
                        </p>
                        <Button
                            type="submit"
                            variant="primary"
                            icon={Flame}
                            loading={forging}
                            className="bg-amber-600 hover:bg-amber-500 text-white border-transparent"
                            disabled={!code.trim() || code.length < 15}
                        >
                            Ignite The Forge
                        </Button>
                    </div>
                </form>
            </Card>

            {/* Latest Crafted Showcase */}
            {latestArtifact && (
                <div className="p-4 rounded-2xl bg-surface border-2 border-amber-500/50 shadow-lg space-y-3 animate-rise">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Sparkles className="h-4 w-4 text-amber-500" />
                            <span className="text-xs font-bold uppercase tracking-wider text-amber-500">Freshly Transmuted Artifact</span>
                        </div>
                        <span className={cx('badge font-bold border text-xs', RARITY_COLORS[latestArtifact.rarity])}>
                            {latestArtifact.rarity}
                        </span>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-y border-line py-3">
                        <div>
                            <h3 className="text-lg font-extrabold text-fg">{latestArtifact.name}</h3>
                            <p className="text-xs italic text-subtle mt-0.5">&ldquo;{latestArtifact.flavor_text}&rdquo;</p>
                        </div>
                        <div className="grid grid-cols-4 gap-2 text-center text-xs shrink-0">
                            <div className="p-2 rounded-xl bg-surface-2"><div className="text-subtle text-[10px]">Power</div><b className="text-rose-500">{latestArtifact.power}</b></div>
                            <div className="p-2 rounded-xl bg-surface-2"><div className="text-subtle text-[10px]">Resil</div><b className="text-blue-500">{latestArtifact.resilience}</b></div>
                            <div className="p-2 rounded-xl bg-surface-2"><div className="text-subtle text-[10px]">Speed</div><b className="text-amber-500">{latestArtifact.speed}</b></div>
                            <div className="p-2 rounded-xl bg-surface-2"><div className="text-subtle text-[10px]">Elegance</div><b className="text-purple-500">{latestArtifact.elegance}</b></div>
                        </div>
                    </div>
                </div>
            )}

            {/* Armory & Inventory Vault */}
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold uppercase tracking-wider text-subtle flex items-center gap-1.5">
                        <Layers className="h-4 w-4" /> Armory Vault ({data.artifacts?.length || 0})
                    </h2>
                </div>

                {data.artifacts?.length === 0 ? (
                    <Card className="card-pad text-center py-12">
                        <Hammer className="h-10 w-10 mx-auto text-subtle mb-3" />
                        <h3 className="text-base font-bold text-fg">Your Armory is Empty</h3>
                        <p className="text-xs text-subtle max-w-sm mx-auto mt-1">
                            Feed your algorithms and problem solutions into the Crucible above to craft your first mythic weapon!
                        </p>
                    </Card>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {data.artifacts.map((a) => {
                            const Icon = SLOT_ICONS[a.slot] || Sword;
                            const isUpgrading = upgradingId === a.id;
                            return (
                                <Card key={a.id} className="card-pad space-y-3 hover:border-line-strong transition-all flex flex-col justify-between">
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between gap-2">
                                            <span className={cx('badge font-bold text-[10px] border', RARITY_COLORS[a.rarity])}>
                                                {a.rarity} · {a.slot}
                                            </span>
                                            <span className="badge text-[10px] bg-surface-2 font-mono font-bold">
                                                LVL {a.level}
                                            </span>
                                        </div>

                                        <div>
                                            <h4 className="text-[14px] font-bold text-fg leading-snug flex items-center gap-1.5">
                                                <Icon className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                                                <span className="truncate">{a.name}</span>
                                            </h4>
                                            <p className="text-[11px] italic text-subtle mt-1 line-clamp-2">
                                                &ldquo;{a.flavor_text}&rdquo;
                                            </p>
                                        </div>

                                        <div className="grid grid-cols-4 gap-1.5 text-center text-[11px] pt-1 border-t border-line">
                                            <div className="p-1 rounded bg-surface-2"><span className="text-[9px] text-subtle block">PWR</span><b className="text-rose-500">{a.power}</b></div>
                                            <div className="p-1 rounded bg-surface-2"><span className="text-[9px] text-subtle block">RES</span><b className="text-blue-500">{a.resilience}</b></div>
                                            <div className="p-1 rounded bg-surface-2"><span className="text-[9px] text-subtle block">SPD</span><b className="text-amber-500">{a.speed}</b></div>
                                            <div className="p-1 rounded bg-surface-2"><span className="text-[9px] text-subtle block">ELG</span><b className="text-purple-500">{a.elegance}</b></div>
                                        </div>
                                    </div>

                                    <div className="pt-2 border-t border-line flex items-center justify-between gap-2">
                                        <span className="text-[10px] text-subtle">
                                            {a.created_at ? new Date(a.created_at).toLocaleDateString() : ''}
                                        </span>
                                        <Button
                                            size="xs"
                                            variant="secondary"
                                            icon={ArrowUpCircle}
                                            loading={isUpgrading}
                                            onClick={() => handleUpgrade(a.id)}
                                        >
                                            Upgrade (+Stats)
                                        </Button>
                                    </div>
                                </Card>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
