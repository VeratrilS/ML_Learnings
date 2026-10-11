import { useState } from 'react';
import { Repeat2, ExternalLink, ThumbsUp, RotateCcw, Brain } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Card, CardHeader, DifficultyBadge, Empty, Skeleton, useToast } from './ui';

const STAGES = ['1d', '3d', '7d', '21d', '60d'];

export default function RevisionCard() {
    const { data, loading, setData } = useApi('/reviews');
    const [busy, setBusy] = useState(null);
    const toast = useToast();

    const review = async (log, result) => {
        setBusy(log.id);
        try {
            const r = await api(`/reviews/${log.id}`, { method: 'POST', body: { result } });
            setData((list) => list.filter((l) => l.id !== log.id));
            const next = r.data.next_review_at;
            toast(next ? `Next review in ${Math.round((new Date(next) - Date.now()) / 86400000)} days` : 'Mastered. Retired from reviews.');
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    return (
        <Card className="overflow-hidden">
            <div className="card-pad pb-0">
                <CardHeader
                    title="Revision"
                    subtitle={data ? (data.length ? `${data.length} due · re-solve without looking` : 'Spaced repetition: 1 → 3 → 7 → 21 → 60 days') : 'Loading…'}
                    icon={Repeat2}
                    className="mb-2"
                />
            </div>
            {loading && !data ? (
                <div className="p-4 space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-10" />)}</div>
            ) : data?.length ? (
                <ul className="divide-y divide-line border-t border-line">
                    {data.slice(0, 5).map((l) => (
                        <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 sm:px-4 py-3">
                            <button onClick={() => navigate(`problems/${l.id}`)} className="min-w-0 flex-1 text-left">
                                <div className="text-sm font-medium truncate">{l.title}</div>
                                <div className="flex items-center gap-2 mt-0.5 text-xs text-subtle">
                                    <DifficultyBadge value={l.difficulty} />
                                    <span>review {Math.min(l.review_stage + 1, STAGES.length)} of {STAGES.length}</span>
                                </div>
                            </button>
                            <div className="flex items-center gap-1 shrink-0">
                                <a href={l.link} target="_blank" rel="noreferrer" className="btn btn-ghost btn-icon btn-sm" aria-label="Open on LeetCode" title="Open on LeetCode">
                                    <ExternalLink className="h-4 w-4" />
                                </a>
                                <button className="btn btn-secondary btn-sm" disabled={busy === l.id} onClick={() => review(l, 'hard')} title="Struggled: review again tomorrow">
                                    <RotateCcw className="h-3.5 w-3.5" /> Again
                                </button>
                                <button className="btn btn-primary btn-sm" disabled={busy === l.id} onClick={() => review(l, 'easy')} title="Solved it cleanly">
                                    <ThumbsUp className="h-3.5 w-3.5" /> Got it
                                </button>
                            </div>
                        </li>
                    ))}
                </ul>
            ) : (
                <Empty icon={Brain} title="No reviews due">Solved problems come back here so they stick for interviews.</Empty>
            )}
        </Card>
    );
}
