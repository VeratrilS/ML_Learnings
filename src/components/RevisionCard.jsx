import { useState } from 'react';
import { Repeat2, ExternalLink, RotateCcw, Frown, ThumbsUp, Zap, Brain } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Card, CardHeader, DifficultyBadge, Empty, Skeleton, cx, useToast } from './ui';

const GRADES = [
    { grade: 'again', label: 'Again', icon: RotateCcw, cls: 'btn-secondary', title: "Couldn't do it: see it again tomorrow" },
    { grade: 'hard', label: 'Hard', icon: Frown, cls: 'btn-secondary', title: 'Solved it, but it was a struggle' },
    { grade: 'good', label: 'Good', icon: ThumbsUp, cls: 'btn-primary', title: 'Solved it cleanly' },
    { grade: 'easy', label: 'Easy', icon: Zap, cls: 'btn-secondary', title: 'Trivial now: push it further out' },
];

function recallTone(r) {
    if (r < 0.7) return 'text-danger bg-danger/10';
    if (r < 0.85) return 'text-accent bg-accent-soft';
    return 'text-ok bg-ok/10';
}

function seeYou(next) {
    if (!next) return 'Mastered. Retired from reviews.';
    const days = Math.max(1, Math.round((new Date(next) - Date.now()) / 86400000));
    return days === 1 ? 'See you tomorrow' : `See you in ${days} days`;
}

function stabilityLabel(days) {
    if (days == null) return null;
    if (days < 1) return 'memory < 1 day';
    if (days < 60) return `memory ~${Math.round(days)}d`;
    return `memory ~${Math.round(days / 30)}mo`;
}

export default function RevisionCard() {
    const { data: res, loading, setData } = useApi('/reviews', { select: (d) => d });
    const [busy, setBusy] = useState(null);
    const toast = useToast();
    const data = res?.data;

    const review = async (log, grade) => {
        setBusy(log.id);
        try {
            const r = await api(`/reviews/${log.id}`, { method: 'POST', body: { grade } });
            setData((cur) => cur && {
                ...cur,
                data: cur.data.filter((l) => l.id !== log.id),
                due_count: Math.max(0, (cur.due_count ?? cur.data.length) - 1),
            });
            toast(seeYou(r.data.next_review_at));
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setBusy(null);
        }
    };

    const due = res ? res.due_count ?? data.length : 0;
    const week = res?.week_count ?? 0;
    const subtitle = !res
        ? 'Loading…'
        : due
            ? `${due} due · ${week} this week`
            : week ? `Nothing due · ${week} this week` : 'Scheduled when recall drops to 90%';

    return (
        <Card className="overflow-hidden">
            <div className="card-pad pb-0">
                <CardHeader title="Revision" subtitle={subtitle} icon={Repeat2} className="mb-2" />
            </div>
            {loading && !res ? (
                <div className="p-4 space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-10" />)}</div>
            ) : data?.length ? (
                <ul className="divide-y divide-line border-t border-line">
                    {data.slice(0, 5).map((l) => (
                        <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 sm:px-4 py-3">
                            <div className="flex items-center gap-1 min-w-0 flex-1 basis-56">
                                <button onClick={() => navigate(`problems/${l.id}`)} className="min-w-0 flex-1 text-left">
                                    <div className="text-sm font-medium truncate">{l.title}</div>
                                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-0.5 text-xs text-subtle">
                                        <DifficultyBadge value={l.difficulty} />
                                        {l.recall != null && (
                                            <span className={cx('badge tabular-nums', recallTone(l.recall))} title="Estimated chance you can still solve it">
                                                {Math.round(l.recall * 100)}% recall
                                            </span>
                                        )}
                                        <span className="truncate">
                                            {l.review_stage ? `${l.review_stage} review${l.review_stage === 1 ? '' : 's'}` : 'first review'}
                                            {stabilityLabel(l.stability_days) && ` · ${stabilityLabel(l.stability_days)}`}
                                        </span>
                                    </div>
                                </button>
                                <a href={l.link} target="_blank" rel="noreferrer" className="btn btn-ghost btn-icon btn-sm shrink-0" aria-label="Open on LeetCode" title="Open on LeetCode">
                                    <ExternalLink className="h-4 w-4" />
                                </a>
                            </div>
                            <div className="grid grid-cols-4 gap-1 w-full sm:w-auto sm:shrink-0">
                                {GRADES.map(({ grade, label, icon: Icon, cls, title }) => (
                                    <button
                                        key={grade}
                                        className={cx('btn btn-sm gap-1 px-1.5 sm:px-2.5 text-[12px] sm:text-[13px]', cls)}
                                        disabled={busy === l.id}
                                        onClick={() => review(l, grade)}
                                        title={title}
                                        aria-label={`${label}: ${title}`}
                                    >
                                        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden /> {label}
                                    </button>
                                ))}
                            </div>
                        </li>
                    ))}
                </ul>
            ) : (
                <Empty icon={Brain} title="No reviews due">Solved problems come back right before you'd forget them, so they stick for interviews.</Empty>
            )}
        </Card>
    );
}
