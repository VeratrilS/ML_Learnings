import { ArrowRight, CheckCircle2, Flame, Layers } from 'lucide-react';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader, ProgressBar, Skeleton, cx } from './ui';

// Same path as the Cards page's default view, so the two share one request and snapshot.
const PATH = '/cards/today?limit=20';

export default function CardsCard() {
    const { data, loading, error, reload } = useApi(PATH, { select: (d) => ({ counts: d.counts, subjects: d.subjects }) });
    const counts = data?.counts;
    const subjects = data?.subjects || [];
    const left = (counts?.due || 0) + (counts?.new || 0);

    return (
        <Card className="card-pad">
            <CardHeader
                title="Flashcards"
                subtitle="OS · DBMS · CN · OOP · SQL"
                icon={Layers}
                action={counts?.streak > 0 && (
                    <span className="badge text-accent bg-accent-soft tabular-nums" title="Days in a row with a review">
                        <Flame className="h-3 w-3" />{counts.streak}d
                    </span>
                )}
            />

            {loading && !data ? (
                <div className="space-y-3">
                    <Skeleton className="h-14" />
                    <Skeleton className="h-20" />
                    <Skeleton className="h-9" />
                </div>
            ) : error && !data ? (
                <div className="text-sm text-muted flex items-center justify-between gap-3">
                    <span className="min-w-0 truncate">{error}</span>
                    <Button size="sm" onClick={() => reload()}>Retry</Button>
                </div>
            ) : (
                <>
                    <div className="flex items-end justify-between gap-4">
                        <div className="min-w-0">
                            {left ? (
                                <>
                                    <div className="text-3xl font-bold tracking-tight tabular-nums">{left}</div>
                                    <p className="text-xs text-muted mt-0.5 tabular-nums">
                                        <span className={cx(counts.due > 0 && 'text-danger font-medium')}>{counts.due} due</span> · {counts.new} new
                                    </p>
                                </>
                            ) : (
                                <div className="flex items-center gap-2 text-ok">
                                    <CheckCircle2 className="h-5 w-5" />
                                    <span className="text-sm font-semibold">All caught up</span>
                                </div>
                            )}
                        </div>
                        <div className="text-right shrink-0">
                            <div className="text-lg font-semibold tabular-nums">{counts?.done_today ?? 0}</div>
                            <p className="eyebrow">done today</p>
                        </div>
                    </div>

                    {subjects.length > 0 && (
                        <ul className="mt-4 space-y-2">
                            {subjects.map((s) => (
                                <li key={s.subject} className="grid grid-cols-[2.75rem_1fr_auto] items-center gap-2.5 text-xs">
                                    <span className="font-semibold text-muted">{s.subject}</span>
                                    <ProgressBar value={s.mastery} color={s.mastery >= 80 ? 'var(--ok)' : 'var(--accent)'} />
                                    <span className="w-14 text-right tabular-nums text-subtle">
                                        {s.due > 0 ? <span className="text-danger">{s.due} due</span> : `${s.mastery}%`}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}

                    <Button
                        variant={left ? 'primary' : 'secondary'}
                        className="w-full mt-4"
                        icon={ArrowRight}
                        onClick={() => navigate('cards')}
                    >
                        {left ? 'Start review' : 'Browse cards'}
                    </Button>
                </>
            )}
        </Card>
    );
}
