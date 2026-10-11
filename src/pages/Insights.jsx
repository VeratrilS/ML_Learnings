import { useState } from 'react';
import {
    ArrowRight, BookOpen, Brain, ChevronDown, Code2, Dumbbell, GraduationCap, Minus, Plus,
    RefreshCw, Sparkles, Swords, Target, TriangleAlert,
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Empty, ProgressBar, Skeleton, cx, useToast } from '../components/ui';

// Keep in sync with the palette on the Study page
const COLORS = {
    violet: '#7c5cff', teal: '#0d9488', rose: '#e11d48', amber: '#d97706',
    blue: '#2563eb', green: '#16a34a', pink: '#db2777', orange: '#e8590c',
};
const hexOf = (s) => COLORS[s?.color] || (/^#[0-9a-f]{3,8}$/i.test(s?.color || '') ? s.color : 'var(--accent)');

const pct = (x) => Math.round((x || 0) * 100);
const parseDay = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const fmtDay = (s) => (s ? parseDay(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '—');
const dayDiff = (a, b) => Math.round((parseDay(b) - parseDay(a)) / 86400000);

function fmtHours(h) {
    const m = Math.round(((h || 0) * 60) / 5) * 5;
    if (m <= 0) return '0m';
    const hh = Math.floor(m / 60);
    const mm = m % 60;
    return hh ? (mm ? `${hh}h ${mm}m` : `${hh}h`) : `${mm}m`;
}

function pTone(p) {
    if (p == null) return 'text-subtle';
    if (p >= 0.8) return 'text-ok';
    if (p >= 0.5) return 'text-accent';
    return 'text-danger';
}

function daysPhrase(d) {
    if (d == null) return 'No exam date';
    if (d < 0) return 'Exam done';
    if (d === 0) return 'Exam today';
    if (d === 1) return 'Exam tomorrow';
    return `Exam in ${d} days`;
}

function SectionTitle({ icon: Icon, title, subtitle }) {
    return (
        <div className="flex items-end gap-2.5 px-0.5">
            <Icon className="h-4 w-4 text-accent mb-1 shrink-0" aria-hidden />
            <div className="min-w-0">
                <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
                {subtitle && <p className="text-xs text-subtle">{subtitle}</p>}
            </div>
        </div>
    );
}

// ---------------- (a) Exam readiness ----------------
function Burndown({ subject }) {
    const pts = subject.burndown || [];
    if (pts.length < 2) return null;
    const W = 300;
    const H = 96;
    const pad = { l: 26, r: 10, t: 10, b: 18 };
    const first = pts[0].date;
    const last = pts[pts.length - 1].date;
    const endDay = subject.exam_date && subject.days_left >= 0
        ? dayDiff(first, subject.exam_date)
        : dayDiff(first, last) + Math.max(7, subject.p50_date ? dayDiff(last, subject.p50_date) : 7);
    const maxY = Math.max(1, ...pts.map((p) => p.remaining));
    const x = (day) => pad.l + (day / Math.max(1, endDay)) * (W - pad.l - pad.r);
    const y = (v) => pad.t + (1 - v / maxY) * (H - pad.t - pad.b);
    const actual = pts.map((p) => `${x(dayDiff(first, p.date)).toFixed(1)},${y(p.remaining).toFixed(1)}`).join(' ');
    const todayX = x(dayDiff(first, last));
    const nowLeft = pts[pts.length - 1].remaining;
    const p50 = subject.p50_date ? Math.min(endDay, dayDiff(first, subject.p50_date)) : null;
    const hex = hexOf(subject);
    const label = `Burn-down for ${subject.name}: ${pts[0].remaining} topics left on ${fmtDay(first)}, ${nowLeft} left today`
        + (subject.exam_date ? `, exam on ${fmtDay(subject.exam_date)}.` : '.');

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block" role="img" aria-label={label}>
            {/* axes */}
            <line x1={pad.l} y1={y(0)} x2={W - pad.r} y2={y(0)} stroke="var(--line-strong)" strokeWidth="1" />
            <line x1={pad.l} y1={pad.t} x2={pad.l} y2={y(0)} stroke="var(--line)" strokeWidth="1" />
            <text x={pad.l - 5} y={y(maxY) + 3} textAnchor="end" fontSize="9" fill="var(--subtle)">{maxY}</text>
            <text x={pad.l - 5} y={y(0) + 3} textAnchor="end" fontSize="9" fill="var(--subtle)">0</text>
            <text x={pad.l} y={H - 4} fontSize="9" fill="var(--subtle)">{fmtDay(first)}</text>
            {/* ideal line: from the first point straight to zero on exam day */}
            <line x1={x(0)} y1={y(pts[0].remaining)} x2={x(endDay)} y2={y(0)}
                stroke="var(--subtle)" strokeWidth="1" strokeDasharray="3 3" />
            {/* forecast: today -> P50 finish */}
            {p50 != null && nowLeft > 0 && (
                <line x1={todayX} y1={y(nowLeft)} x2={x(p50)} y2={y(0)}
                    stroke={hex} strokeOpacity="0.45" strokeWidth="1.5" strokeDasharray="1 3" strokeLinecap="round" />
            )}
            {/* actual */}
            <polyline points={actual} fill="none" stroke={hex} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx={todayX} cy={y(nowLeft)} r="3" fill={hex} />
            <text x={Math.min(todayX, W - pad.r - 30) + 5} y={Math.max(pad.t + 8, y(nowLeft) - 6)} fontSize="9" fontWeight="600" fill="var(--fg)">
                {nowLeft} left
            </text>
            {subject.exam_date && subject.days_left >= 0 && (
                <>
                    <line x1={x(endDay)} y1={pad.t} x2={x(endDay)} y2={y(0)} stroke="var(--danger)" strokeOpacity="0.5" strokeWidth="1" />
                    <text x={x(endDay)} y={H - 4} textAnchor="end" fontSize="9" fill="var(--subtle)">exam {fmtDay(subject.exam_date)}</text>
                </>
            )}
        </svg>
    );
}

function Meter({ label, value, color }) {
    return (
        <div>
            <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-muted">{label}</span>
                <span className="font-semibold tabular-nums">{value == null ? '—' : `${pct(value)}%`}</span>
            </div>
            <ProgressBar value={pct(value)} color={color} className="h-1.5" />
        </div>
    );
}

function SubjectCard({ s }) {
    const hex = hexOf(s);
    return (
        <Card className="card-pad flex flex-col gap-4 min-w-0">
            <div className="flex items-start gap-2.5 min-w-0">
                <span className="h-2.5 w-2.5 rounded-full mt-1.5 shrink-0" style={{ background: hex }} aria-hidden />
                <div className="min-w-0 flex-1">
                    <h3 className="text-[15px] font-semibold tracking-tight truncate" title={s.name}>{s.short || s.name}</h3>
                    <p className="text-xs text-subtle truncate">
                        {daysPhrase(s.days_left)}{s.exam_date ? ` · ${fmtDay(s.exam_date)}` : ''} · {s.pending} of {s.total} left
                    </p>
                </div>
                {s.hours_today > 0 && (
                    <span className="badge bg-accent-soft text-accent tabular-nums">{fmtHours(s.hours_today)} today</span>
                )}
            </div>

            <div className="space-y-2.5">
                <Meter label="Ready now" value={s.readiness_now} color={hex} />
                <Meter label="At exam, if you stop now" value={s.readiness_exam} color="var(--subtle)" />
            </div>

            <div className="flex items-end justify-between gap-3">
                <div>
                    <div className="eyebrow">Finish on time</div>
                    <div className={cx('text-[28px] font-bold tracking-tight tabular-nums leading-none mt-1', pTone(s.p_finish))}>
                        {s.p_finish == null ? '—' : `${pct(s.p_finish)}%`}
                    </div>
                </div>
                <div className="text-right text-xs text-muted tabular-nums">
                    <div>P50 <span className="font-semibold text-fg">{fmtDay(s.p50_date)}</span></div>
                    <div>P90 <span className="font-semibold text-fg">{s.p90_date ? fmtDay(s.p90_date) : '> 6 mo'}</span></div>
                </div>
            </div>

            <Burndown subject={s} />

            {s.throughput_prior && s.pending > 0 && (
                <p className="text-[11px] text-subtle -mt-2">Forecast uses a starter pace (1.5 topics/day) until you have 5 days of history.</p>
            )}

            {s.study_next?.length > 0 && (
                <div>
                    <div className="eyebrow mb-1">Study next</div>
                    <ul className="divide-y divide-line">
                        {s.study_next.map((t) => (
                            <li key={t.topic_id} className="flex items-start gap-3 py-1.5 text-[13px]">
                                <div className="min-w-0 flex-1">
                                    <div className="leading-snug break-words">{t.title}</div>
                                    {t.unit && <div className="text-[11px] text-subtle truncate">{t.unit}</div>}
                                </div>
                                <span className="text-xs text-muted tabular-nums shrink-0">{t.minutes}m</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </Card>
    );
}

function HoursStepper({ value, onChange, saving }) {
    return (
        <div className="inline-flex items-center rounded-xl border border-line bg-surface-2 p-0.5" role="group" aria-label="Daily study hours">
            <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="Fewer hours" disabled={saving || value <= 1}
                onClick={() => onChange(value - 1)}>
                <Minus className="h-4 w-4" />
            </button>
            <span className="w-14 text-center text-sm font-semibold tabular-nums" aria-live="polite">{value}h/day</span>
            <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="More hours" disabled={saving || value >= 16}
                onClick={() => onChange(value + 1)}>
                <Plus className="h-4 w-4" />
            </button>
        </div>
    );
}

function SplitBar({ subjects, plan }) {
    const segs = [
        ...subjects.filter((s) => s.hours_today > 0).map((s) => ({ key: s.id, label: s.short || s.name, h: s.hours_today, color: hexOf(s) })),
        ...(plan.dsa_hours > 0 ? [{ key: 'dsa', label: 'DSA', h: plan.dsa_hours, color: 'var(--muted)' }] : []),
        ...(plan.free_hours > 0 ? [{ key: 'free', label: 'Free / revise', h: plan.free_hours, color: 'var(--surface-3)' }] : []),
    ];
    const total = segs.reduce((n, s) => n + s.h, 0) || 1;
    return (
        <div>
            <div className="flex h-3 rounded-full overflow-hidden bg-surface-3 gap-px" role="img"
                aria-label={segs.map((s) => `${s.label} ${fmtHours(s.h)}`).join(', ')}>
                {segs.map((s) => <div key={s.key} style={{ width: `${(100 * s.h) / total}%`, background: s.color }} />)}
            </div>
            <ul className="flex flex-wrap gap-x-4 gap-y-1.5 mt-2.5 text-xs">
                {segs.map((s) => (
                    <li key={s.key} className="flex items-center gap-1.5 min-w-0">
                        <span className="h-2 w-2 rounded-full shrink-0" style={{ background: s.color }} aria-hidden />
                        <span className="text-muted truncate">{s.label}</span>
                        <span className="font-semibold tabular-nums">{fmtHours(s.h)}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

function StudySection() {
    const study = useApi('/insights/study', { select: (d) => d });
    const toast = useToast();
    const [saving, setSaving] = useState(false);
    const [hoursOverride, setHoursOverride] = useState(null);
    const data = study.data;
    const plan = data?.plan || {};
    const hours = hoursOverride ?? Math.round(plan.hours || 3);
    const upcoming = (data?.subjects || []).filter((s) => s.days_left != null && s.days_left >= 0);

    const setHours = async (n) => {
        setHoursOverride(n);
        setSaving(true);
        try {
            await api('/settings', { method: 'POST', body: { daily_study_hours: String(n) } });
            await study.reload({ silent: true });
        } catch (e) {
            toast(e.message, 'error');
            setHoursOverride(null);
        } finally {
            setSaving(false);
        }
    };

    if (study.loading && !data) {
        return (
            <div className="grid gap-4 sm:grid-cols-2">
                <Skeleton className="h-32 sm:col-span-2" />
                <Skeleton className="h-80" />
                <Skeleton className="h-80" />
            </div>
        );
    }
    if (study.error && !data) return <Card className="card-pad"><p className="text-sm text-danger">{study.error}</p></Card>;
    if (!data?.subjects?.length) {
        return (
            <Card className="card-pad">
                <Empty icon={BookOpen} title="Add exam dates + syllabus to get your plan"
                    action={<Button size="sm" variant="primary" icon={ArrowRight} onClick={() => navigate('study')}>Open study plan</Button>}>
                    {data?.empty_reason}
                </Empty>
            </Card>
        );
    }

    const nearest = upcoming[0];
    return (
        <div className="space-y-4">
            <Card className="card-pad">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                    <div className="min-w-0">
                        <h3 className="text-[15px] font-semibold tracking-tight">Today&apos;s split</h3>
                        <p className="text-xs text-subtle">Hours go where the work-per-day-left is highest.</p>
                    </div>
                    <HoursStepper value={hours} onChange={setHours} saving={saving} />
                </div>
                {upcoming.length ? <SplitBar subjects={upcoming} plan={plan} /> : (
                    <p className="text-sm text-muted">{data.empty_reason}</p>
                )}
                {plan.feasible === false && (
                    <div className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-2.5 mt-4 text-[13px] text-danger" role="status">
                        <TriangleAlert className="h-4 w-4 mt-px shrink-0" aria-hidden />
                        <span>
                            At {hours}h/day you&apos;re about <b>{fmtHours(plan.shortfall_hours)}</b> short
                            {nearest ? ` (tightest around ${nearest.short || nearest.name})` : ''}. Add an hour a day, or aim for
                            confidence 2 instead of 3 on low-weight topics.
                        </span>
                    </div>
                )}
            </Card>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {data.subjects.map((s) => <SubjectCard key={s.id} s={s} />)}
            </div>
        </div>
    );
}

// ---------------- (b) LeetCode skill map ----------------
function SkillsSection() {
    const skills = useApi('/insights/skills', { select: (d) => d });
    const [showAll, setShowAll] = useState(false);
    const d = skills.data;

    if (skills.loading && !d) return <Card className="card-pad"><Skeleton className="h-6 w-40 mb-4" /><Skeleton className="h-56" /></Card>;
    if (skills.error && !d) return <Card className="card-pad"><p className="text-sm text-danger">{skills.error}</p></Card>;

    const tracked = d.topics.filter((t) => t.n > 0);
    const rows = showAll || !tracked.length ? d.topics : tracked;
    const ratings = rows.map((t) => t.rating).concat(d.global_rating);
    const lo = Math.min(...ratings) - 60;
    const hi = Math.max(...ratings) + 60;
    const w = (r) => `${Math.max(2, Math.min(100, (100 * (r - lo)) / (hi - lo)))}%`;
    const weakest = tracked[0]?.topic;
    const rec = d.recommended;

    return (
        <Card className="card-pad">
            <CardHeader
                title="LeetCode skill map"
                subtitle={d.contest_rating
                    ? `Anchored on contest rating ${d.contest_rating} · ${d.n_events} graded problems`
                    : `No contest rating found, starting at ${d.global_rating} · ${d.n_events} graded problems`}
                icon={Brain}
            />

            {rec && (
                <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-line bg-accent-soft/60 p-3 mb-4">
                    <div className="min-w-0 flex-1">
                        <div className="eyebrow text-accent">Practice next</div>
                        <div className="text-sm font-semibold mt-0.5">{rec.topic}</div>
                        <div className="text-xs text-muted">{pct(rec.p_solve_medium)}% chance on a Medium today, and it shows up a lot.</div>
                    </div>
                    <Button size="sm" variant="primary" icon={Dumbbell} onClick={() => navigate('problems')}>Practice this</Button>
                </div>
            )}

            {!tracked.length && (
                <p className="text-[13px] text-subtle mb-3">Solve a few emailed problems and topic ratings start to separate. Showing the prior for now.</p>
            )}

            <ul className="space-y-2.5" aria-label="Rating by topic, weakest first">
                {rows.map((t) => {
                    const isWeak = t.topic === weakest;
                    const color = t.n === 0 ? 'var(--line-strong)' : t.delta <= -15 ? 'var(--danger)' : t.delta >= 15 ? 'var(--ok)' : 'var(--muted)';
                    return (
                        <li key={t.topic} className={cx('rounded-lg -mx-2 px-2 py-1', isWeak && 'bg-danger/5 ring-1 ring-danger/25')}>
                            <div className="flex items-center gap-2 text-[13px] min-w-0">
                                <span className={cx('truncate min-w-0 flex-1', t.n === 0 ? 'text-subtle' : 'font-medium')}>{t.topic}</span>
                                {isWeak && <span className="badge text-danger bg-danger/10 shrink-0">weakest</span>}
                                <span className="text-xs text-subtle tabular-nums shrink-0" title="Problems graded in this topic">n={t.n}</span>
                                <span className="text-xs font-semibold tabular-nums w-11 text-right shrink-0">{t.rating}</span>
                            </div>
                            <div className="flex items-center gap-2 mt-1">
                                <div className="relative h-1.5 flex-1 rounded-full bg-surface-3">
                                    <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: w(t.rating), background: color }} />
                                    <div className="absolute -top-0.5 -bottom-0.5 w-px bg-fg/40" style={{ left: w(d.global_rating) }} aria-hidden />
                                </div>
                                <span className="text-[11px] text-muted tabular-nums w-20 text-right shrink-0" title="Chance to solve a Medium">
                                    {pct(t.p_solve_medium)}% Medium
                                </span>
                            </div>
                        </li>
                    );
                })}
            </ul>
            <div className="flex items-center justify-between gap-2 mt-3 text-[11px] text-subtle">
                <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-px bg-fg/40" aria-hidden /> overall {d.global_rating}</span>
                {tracked.length > 0 && tracked.length < d.topics.length && (
                    <button type="button" className="text-accent hover:underline font-medium" onClick={() => setShowAll((v) => !v)}>
                        {showAll ? 'Only practised topics' : `Show all ${d.topics.length} topics`}
                    </button>
                )}
            </div>
        </Card>
    );
}

// ---------------- (c) Codeforces ----------------
function CfSection() {
    const cf = useApi('/insights/cf', { select: (d) => d });
    const d = cf.data;

    const generate = () => {
        try {
            const prev = JSON.parse(localStorage.getItem('cf.filters') || '{}') || {};
            localStorage.setItem('cf.filters', JSON.stringify({ ...prev, min: d.suggested_min, max: d.suggested_max }));
        } catch { /* storage unavailable: the CF page falls back to its own range */ }
        navigate('cf');
    };

    if (cf.loading && !d) return <Card className="card-pad"><Skeleton className="h-6 w-40 mb-4" /><Skeleton className="h-28" /></Card>;
    if (cf.error && !d) return <Card className="card-pad"><p className="text-sm text-danger">{cf.error}</p></Card>;

    const weak = d.weakest_tags?.length ? d.weakest_tags : (d.tags || []).slice(0, 5).map((t) => t.tag);
    return (
        <Card className="card-pad">
            <CardHeader title="Codeforces" subtitle={d.handle ? `@${d.handle} · practice rating from every attempt` : 'Practice rating'} icon={Swords}
                action={<Button size="sm" variant="ghost" icon={RefreshCw} onClick={() => cf.reload()} aria-label="Refresh Codeforces" />} />
            {d.error && <p className="text-[13px] text-danger mb-3">{d.error}</p>}
            <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-line bg-surface-2/60 p-3">
                    <div className="eyebrow">Calibrated</div>
                    <div className="text-[28px] font-bold tracking-tight tabular-nums leading-none mt-1.5">{d.rating ?? '—'}</div>
                    <div className="text-xs text-subtle mt-1.5 tabular-nums">{d.n_solved} solved / {d.n_attempted} tried</div>
                </div>
                <div className="rounded-xl border border-line bg-surface-2/60 p-3">
                    <div className="eyebrow">Practice range</div>
                    <div className="text-xl font-bold tracking-tight tabular-nums leading-none mt-2.5">{d.suggested_min}–{d.suggested_max}</div>
                    <div className="text-xs text-subtle mt-2">a little above your level</div>
                </div>
            </div>
            {d.n_attempted === 0 && !d.error && (
                <p className="text-[13px] text-subtle mt-3">No rated attempts yet, so this is the 1200 starting guess. Each solve or miss moves it.</p>
            )}
            {weak.length > 0 && (
                <div className="mt-4">
                    <div className="eyebrow mb-2">Weakest tags</div>
                    <div className="flex flex-wrap gap-1.5">
                        {(d.tags || []).filter((t) => weak.includes(t.tag)).map((t) => (
                            <span key={t.tag} className="chip cursor-default hover:text-muted hover:border-line">
                                {t.tag} <span className="tabular-nums text-subtle">{t.rating}</span>
                            </span>
                        ))}
                    </div>
                </div>
            )}
            <Button className="w-full mt-4" variant="primary" icon={Target} onClick={generate}>Generate a set at this range</Button>
        </Card>
    );
}

// ---------------- (d) How this works ----------------
const MODELS = [
    ['Forgetting curve', 'Each topic has a memory "stability" set by your confidence (2, 6 or 15 days; finished topics last 1.5× longer). Recall fades as (1 + days / 9S)⁻¹, so readiness is your average recall on exam day.'],
    ['Hour allocator', 'Work left is weighted by confidence. Hours go to subjects in proportion to work left per day until their exam, and an earliest-deadline-first check tells you if your daily hours can cover it all.'],
    ['Monte Carlo forecast', 'We replay 2,000 futures by resampling how many topics you actually finished per day over the last 3 weeks. The share that finish before exam day is your on-time chance; P50 and P90 are the typical and the safe finish dates.'],
    ['Elo skill map', 'Each emailed problem is a match: a quick solve beats its difficulty, a late or missing one loses. Topic ratings start at your contest rating and only drift away with evidence.'],
    ['Codeforces MLE', 'We find the rating that best explains which rated problems you solved or missed (a logistic curve), starting from 1200 when there is no data. Tags get their own rating, pulled toward the overall one.'],
];

function HowItWorks() {
    return (
        <Card className="overflow-hidden">
            <details className="group">
                <summary className="flex items-center justify-between gap-3 cursor-pointer list-none card-pad row-hover [&::-webkit-details-marker]:hidden">
                    <span className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight">
                        <Sparkles className="h-4 w-4 text-accent" aria-hidden /> How this works
                    </span>
                    <ChevronDown className="h-4 w-4 text-subtle transition-transform group-open:rotate-180" aria-hidden />
                </summary>
                <dl className="px-4 sm:px-5 pb-5 space-y-3.5">
                    {MODELS.map(([k, v]) => (
                        <div key={k}>
                            <dt className="text-[13px] font-semibold">{k}</dt>
                            <dd className="text-[13px] text-muted leading-relaxed mt-0.5">{v}</dd>
                        </div>
                    ))}
                </dl>
            </details>
        </Card>
    );
}

export default function Insights() {
    return (
        <div className="space-y-6 sm:space-y-8 min-w-0">
            <header className="animate-rise">
                <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Insights</h1>
                <p className="text-sm text-muted mt-1">Your numbers, modelled.</p>
            </header>

            <section className="space-y-3">
                <SectionTitle icon={GraduationCap} title="Exam readiness" subtitle="Forgetting curve + finish forecast per subject" />
                <StudySection />
            </section>

            <div className="grid gap-6 lg:grid-cols-2 items-start">
                <section className="space-y-3 min-w-0">
                    <SectionTitle icon={Code2} title="LeetCode" subtitle="Per-topic Elo, weakest first" />
                    <SkillsSection />
                </section>
                <section className="space-y-3 min-w-0">
                    <SectionTitle icon={Swords} title="Codeforces" subtitle="Calibrated from your submissions" />
                    <CfSection />
                </section>
            </div>

            <HowItWorks />
        </div>
    );
}
