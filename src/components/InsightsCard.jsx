import { ArrowRight, BookOpen, Code2, Gauge, Sparkles, TriangleAlert } from 'lucide-react';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Empty, ProgressBar, Skeleton, cx } from './ui';

// Keep in sync with the palette on the Study page
const COLORS = {
    violet: '#7c5cff', teal: '#0d9488', rose: '#e11d48', amber: '#d97706',
    blue: '#2563eb', green: '#16a34a', pink: '#db2777', orange: '#e8590c',
};
const hexOf = (s) => COLORS[s?.color] || (/^#[0-9a-f]{3,8}$/i.test(s?.color || '') ? s.color : 'var(--accent)');

function fmtHours(h) {
    const m = Math.round(((h || 0) * 60) / 5) * 5;
    if (m <= 0) return '0m';
    const hh = Math.floor(m / 60);
    const mm = m % 60;
    return hh ? (mm ? `${hh}h ${mm}m` : `${hh}h`) : `${mm}m`;
}

function pTone(p) {
    if (p == null) return 'text-subtle bg-surface-2';
    if (p >= 0.8) return 'text-ok bg-ok/10';
    if (p >= 0.5) return 'text-accent bg-accent-soft';
    return 'text-danger bg-danger/10';
}

const pct = (x) => Math.round((x || 0) * 100);

function daysShort(d) {
    if (d == null) return '';
    if (d === 0) return 'today';
    if (d === 1) return 'tomorrow';
    return `${d}d`;
}

function LoadingCard() {
    return (
        <Card className="card-pad">
            <Skeleton className="h-8 w-48 mb-5" />
            <div className="space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-9" />)}</div>
            <Skeleton className="h-20 w-full mt-5" />
        </Card>
    );
}

export default function InsightsCard() {
    const { data, loading, error } = useApi('/insights/summary', { select: (d) => d });

    if (loading && !data) return <LoadingCard />;
    if (error && !data) {
        return (
            <Card className="card-pad">
                <CardHeader title="Today's study split" icon={Gauge} />
                <p className="text-sm text-danger">{error}</p>
            </Card>
        );
    }

    const plan = data?.plan || {};
    const subjects = data?.subjects || [];
    const next = data?.study_next || [];

    if (!subjects.length) {
        return (
            <Card className="card-pad">
                <CardHeader title="Today's study split" icon={Gauge} />
                <Empty icon={BookOpen} title="Add exam dates + syllabus to get your plan"
                    action={<Button size="sm" variant="primary" icon={ArrowRight} onClick={() => navigate('study')}>Set up study plan</Button>}>
                    {data?.empty_reason || 'Once each subject has topics and an exam date, you get a daily hour split and finish odds.'}
                </Empty>
            </Card>
        );
    }

    const total = (plan.study_hours || 0) + (plan.dsa_hours || 0);

    return (
        <Card className="card-pad">
            <CardHeader
                title="Today's study split"
                subtitle={`${fmtHours(total)} planned of ${fmtHours(plan.hours)} / day`}
                icon={Gauge}
                action={<Button size="sm" variant="ghost" onClick={() => navigate('insights')} aria-label="Open insights">Details</Button>}
            />

            {plan.feasible === false && (
                <div className="flex items-start gap-2 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 mb-4 text-[13px] text-danger">
                    <TriangleAlert className="h-4 w-4 mt-px shrink-0" aria-hidden />
                    <span>About {fmtHours(plan.shortfall_hours)} short before the exams at this pace.</span>
                </div>
            )}

            <ul className="space-y-3.5">
                {subjects.map((s) => (
                    <li key={s.id}>
                        <div className="flex items-center gap-2 text-[13px] min-w-0">
                            <span className="h-2 w-2 rounded-full shrink-0" style={{ background: hexOf(s) }} aria-hidden />
                            <span className="font-medium truncate min-w-0" title={s.name}>{s.short || s.name}</span>
                            <span className="text-xs text-subtle tabular-nums shrink-0">{daysShort(s.days_left)}</span>
                            <span className="flex-1" />
                            <span className="text-xs font-semibold tabular-nums shrink-0">{fmtHours(s.hours_today)}</span>
                            <span className={cx('badge tabular-nums shrink-0', pTone(s.p_finish))} title="Chance to finish the syllabus before the exam">
                                {s.p_finish == null ? '—' : `${pct(s.p_finish)}%`}
                            </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1.5">
                            <ProgressBar value={pct(s.readiness_now)} color={hexOf(s)} className="h-1 flex-1" />
                            <span className="text-[11px] text-subtle tabular-nums w-16 text-right shrink-0">{pct(s.readiness_now)}% ready</span>
                        </div>
                    </li>
                ))}
                <li className="flex items-center gap-2 text-[13px]">
                    <Code2 className="h-3.5 w-3.5 text-subtle shrink-0" aria-hidden />
                    <span className="font-medium">DSA practice</span>
                    <span className="flex-1" />
                    <span className="text-xs font-semibold tabular-nums">{fmtHours(plan.dsa_hours)}</span>
                </li>
            </ul>

            <div className="flex items-center justify-between border-t border-line mt-3.5 pt-3 text-[13px]">
                <span className="text-muted">Total today</span>
                <span className="font-semibold tabular-nums">{fmtHours(total)}</span>
            </div>

            {next.length > 0 && (
                <div className="mt-4">
                    <div className="eyebrow flex items-center gap-1.5 mb-1.5"><Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden /> Study next</div>
                    <ul className="-mx-2">
                        {next.map((t) => (
                            <li key={t.topic_id} className="flex items-start gap-2.5 rounded-lg px-2 py-1.5">
                                <span className="h-1.5 w-1.5 rounded-full shrink-0 mt-[7px]" style={{ background: hexOf(t) }} aria-hidden />
                                <div className="min-w-0 flex-1">
                                    <div className="text-[13.5px] leading-snug break-words">{t.title}</div>
                                    <div className="text-[11px] text-subtle truncate">
                                        {[t.short, t.unit?.split(' · ')[0]].filter(Boolean).join(' · ')}
                                    </div>
                                </div>
                                <span className="text-xs text-muted tabular-nums shrink-0 mt-px">{t.minutes}m</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            <Button className="w-full mt-3" icon={ArrowRight} onClick={() => navigate('insights')}>Open insights</Button>
        </Card>
    );
}
