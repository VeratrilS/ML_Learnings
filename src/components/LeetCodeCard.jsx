import { Code2, ExternalLink, Flame, Trophy } from 'lucide-react';
import { useApi, navigate } from '../lib/hooks';
import { Card, CardHeader, Skeleton } from './ui';

const DIFFS = [
    ['easy', 'Easy', 'var(--easy)'],
    ['medium', 'Med', 'var(--medium)'],
    ['hard', 'Hard', 'var(--hard)'],
];

// Three-arc ring showing the Easy / Medium / Hard split of solved problems
function SplitRing({ p, size = 104, stroke = 8 }) {
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const gap = 6;
    let offset = 0;
    const total = p.total || 1;
    return (
        <svg width={size} height={size} className="-rotate-90 shrink-0">
            <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
            {DIFFS.map(([key, , color]) => {
                const len = Math.max(0, (p[key] / total) * c - gap);
                const el = (
                    <circle key={key} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
                        strokeLinecap="round" strokeDasharray={`${len} ${c}`} strokeDashoffset={-offset} />
                );
                offset += (p[key] / total) * c;
                return el;
            })}
        </svg>
    );
}

export default function LeetCodeCard() {
    const { data: p, loading, error } = useApi('/leetcode/profile');

    if (loading && !p) return <Card className="card-pad"><Skeleton className="h-4 w-32 mb-4" /><Skeleton className="h-24" /></Card>;
    if (error || !p) {
        return (
            <Card className="card-pad">
                <CardHeader title="LeetCode" icon={Code2} />
                <p className="text-sm text-subtle">{error || 'Add your LeetCode username in Settings.'}</p>
                {!error && <button className="btn btn-secondary btn-sm mt-3" onClick={() => navigate('settings')}>Open Settings</button>}
            </Card>
        );
    }

    return (
        <Card className="card-pad">
            <CardHeader
                title="LeetCode"
                subtitle={`@${p.username}`}
                icon={Code2}
                action={
                    <a href={`https://leetcode.com/u/${p.username}/`} target="_blank" rel="noreferrer" className="btn btn-ghost btn-icon btn-sm" aria-label="Open profile">
                        <ExternalLink className="h-4 w-4" />
                    </a>
                }
            />
            <div className="flex items-center gap-5">
                <div className="relative">
                    <SplitRing p={p} />
                    <div className="absolute inset-0 grid place-items-center text-center">
                        <div>
                            <div className="text-2xl font-bold tabular-nums leading-none">{p.total}</div>
                            <div className="text-[10.5px] text-subtle font-semibold uppercase tracking-wider mt-1">solved</div>
                        </div>
                    </div>
                </div>
                <div className="flex-1 space-y-2 min-w-0">
                    {DIFFS.map(([key, label, color]) => (
                        <div key={key} className="flex items-center justify-between gap-2 text-sm">
                            <span className="font-semibold" style={{ color }}>{label}</span>
                            <span className="tabular-nums">
                                <span className="font-semibold">{p[key]}</span>
                                {p.available?.[key] && <span className="text-subtle text-xs">/{p.available[key]}</span>}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-4">
                <div className="rounded-xl bg-surface-2 border border-line px-3 py-2">
                    <div className="flex items-center gap-1 text-[11px] text-subtle font-medium"><Trophy className="h-3 w-3" /> Contest</div>
                    <div className="font-semibold tabular-nums">{p.contest_rating ?? '-'}
                        {p.top_percentage != null && <span className="text-xs text-subtle font-medium"> · top {p.top_percentage}%</span>}
                    </div>
                </div>
                <div className="rounded-xl bg-surface-2 border border-line px-3 py-2">
                    <div className="flex items-center gap-1 text-[11px] text-subtle font-medium"><Flame className="h-3 w-3" /> LC streak</div>
                    <div className="font-semibold tabular-nums">{p.streak ?? 0}d <span className="text-xs text-subtle font-medium">· {p.active_days ?? 0} active</span></div>
                </div>
            </div>
        </Card>
    );
}
