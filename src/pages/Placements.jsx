import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    Briefcase, Building2, CalendarClock, Plus, Pencil, Trash2, ExternalLink, Trophy, Target, Kanban,
    ChevronRight, ChevronDown, MapPin, StickyNote, ArrowRight, Archive, RefreshCw, Flag,
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi, useLocalStorage, timeAgo } from '../lib/hooks';
import { Button, Card, CardHeader, Empty, Segmented, Sheet, Skeleton, useToast, cx } from '../components/ui';

// ---------------- constants ----------------
const BOARD = ['wishlist', 'applied', 'oa', 'interview', 'hr', 'offer'];
const CLOSED = ['rejected', 'withdrawn'];
const STAGE = {
    wishlist: { label: 'Wishlist', dot: 'bg-subtle', hint: 'Shortlisted companies you plan to apply to.' },
    applied: { label: 'Applied', dot: 'bg-muted', hint: 'Applied and waiting to hear back.' },
    oa: { label: 'OA', dot: 'bg-accent', hint: 'Online assessments to clear.' },
    interview: { label: 'Interview', dot: 'bg-accent', hint: 'Technical rounds in progress.' },
    hr: { label: 'HR', dot: 'bg-accent', hint: 'HR or managerial round.' },
    offer: { label: 'Offer', dot: 'bg-ok', hint: 'Offers in hand.' },
    rejected: { label: 'Rejected', dot: 'bg-danger' },
    withdrawn: { label: 'Withdrawn', dot: 'bg-subtle' },
};
const SOURCES = [
    { value: 'on-campus', label: 'On-campus' },
    { value: 'off-campus', label: 'Off-campus' },
    { value: 'referral', label: 'Referral' },
];
const SOURCE_CHIP = {
    'on-campus': ['Campus', 'text-accent bg-accent-soft'],
    'off-campus': ['Off-campus', 'text-muted bg-surface-2 border border-line'],
    referral: ['Referral', 'text-ok bg-ok/10'],
};
const FILTERS = [{ value: 'all', label: 'All' }, { value: 'on-campus', label: 'Campus' }, { value: 'off-campus', label: 'Off' }, { value: 'referral', label: 'Referral' }];

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

// ---------------- formatting ----------------
function span(ms) {
    const a = Math.abs(ms);
    if (a < HOUR) return `${Math.max(1, Math.round(a / MIN))}m`;
    if (a < 36 * HOUR) return `${Math.round(a / HOUR)}h`;
    return `${Math.round(a / DAY)}d`;
}
const countdown = (ms) => (Math.abs(ms) < MIN ? 'now' : ms > 0 ? `in ${span(ms)}` : `${span(ms)} ago`);

function daysUntil(ymd) {
    const [y, m, d] = String(ymd).split('-').map(Number);
    const target = new Date(y, (m || 1) - 1, d || 1);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((target - today) / DAY);
}
function deadlineText(n) {
    if (n < 0) return 'Deadline passed';
    if (n === 0) return 'Due today';
    if (n === 1) return 'Due tomorrow';
    return `Due in ${n}d`;
}
const fmtCtc = (v) => (v == null || v === '' ? null : `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })} LPA`);
const fmtWhen = (t) => new Date(t).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
const fmtDate = (ymd) => {
    const [y, m, d] = String(ymd).split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
};
function toLocalInput(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function useNow(intervalMs = 60_000) {
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), intervalMs);
        return () => clearInterval(id);
    }, [intervalMs]);
    return now;
}

// ---------------- derived data ----------------
function summarize(apps) {
    const counts = Object.fromEntries([...BOARD, ...CLOSED].map((s) => [s, 0]));
    for (const a of apps) counts[a.stage] = (counts[a.stage] || 0) + 1;
    const offers = apps.filter((a) => a.stage === 'offer');
    const priced = offers.filter((a) => a.ctc_lpa != null).sort((a, b) => b.ctc_lpa - a.ctc_lpa);
    return {
        counts,
        active: counts.applied + counts.oa + counts.interview + counts.hr,
        oa: counts.oa,
        interviews: counts.interview + counts.hr,
        offers: offers.length,
        best: priced[0] || null,
    };
}

function buildUpcoming(apps, now, days = 14) {
    const items = [];
    for (const a of apps) {
        if (CLOSED.includes(a.stage)) continue;
        if (a.next_event_at) {
            const t = new Date(a.next_event_at).getTime();
            if (t >= now - 2 * HOUR && t <= now + days * DAY) {
                items.push({ key: `e${a.id}`, kind: 'event', app: a, t, label: a.next_event_label || 'Next round' });
            }
        }
        if (a.deadline && a.stage !== 'offer') {
            const n = daysUntil(a.deadline);
            if (n >= 0 && n <= days) {
                const [y, m, d] = a.deadline.split('-').map(Number);
                items.push({ key: `d${a.id}`, kind: 'deadline', app: a, t: new Date(y, m - 1, d, 23, 59).getTime(), n, label: 'Deadline' });
            }
        }
    }
    return items.sort((x, y) => x.t - y.t);
}

// ---------------- small pieces ----------------
function Monogram({ name, className }) {
    const letter = (name || '?').trim().charAt(0).toUpperCase() || '?';
    return (
        <div aria-hidden className={cx('grid place-items-center h-9 w-9 rounded-[10px] bg-surface-2 border border-line text-[13px] font-bold text-muted shrink-0 select-none', className)}>
            {letter}
        </div>
    );
}

function SourceChip({ source }) {
    const [label, cls] = SOURCE_CHIP[source] || SOURCE_CHIP['off-campus'];
    return <span className={cx('badge', cls)}>{label}</span>;
}

function StageDot({ stage, className }) {
    return <span aria-hidden className={cx('inline-block h-2 w-2 rounded-full shrink-0', STAGE[stage]?.dot || 'bg-subtle', className)} />;
}

function DeadlineBadge({ deadline }) {
    if (!deadline) return null;
    const n = daysUntil(deadline);
    const urgent = n <= 2;
    return (
        <span className={cx('badge', urgent ? 'text-danger bg-danger/10' : 'text-muted bg-surface-2')} title={`Deadline ${fmtDate(deadline)}`}>
            <Flag className="h-3 w-3" aria-hidden />
            {deadlineText(n)}
        </span>
    );
}

function NextEvent({ app, now }) {
    if (!app.next_event_at) return null;
    const ms = new Date(app.next_event_at).getTime() - now;
    if (ms < -12 * HOUR) return null;
    const soon = ms < DAY;
    return (
        <div className={cx('flex items-center gap-1.5 text-xs min-w-0', soon ? 'text-accent font-semibold' : 'text-muted')} title={fmtWhen(app.next_event_at)}>
            <CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="truncate">{app.next_event_label || 'Next round'}</span>
            <span className="shrink-0 tabular-nums">{countdown(ms)}</span>
        </div>
    );
}

function StagePicker({ value, onChange, disabled }) {
    return (
        <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-5 px-5 sm:-mx-6 sm:px-6 pb-0.5" role="radiogroup" aria-label="Stage">
            {[...BOARD, ...CLOSED].map((s, i) => (
                <button
                    key={s}
                    type="button"
                    role="radio"
                    aria-checked={value === s}
                    disabled={disabled}
                    onClick={() => onChange(s)}
                    className={cx('chip shrink-0', value === s && 'chip-on', i === BOARD.length && 'ml-2')}
                >
                    <StageDot stage={s} />
                    {STAGE[s].label}
                </button>
            ))}
        </div>
    );
}

// ---------------- board ----------------
function AppCard({ app, now, onOpen, onAdvance, draggable, onDragStart, onDragEnd, dragging }) {
    const idx = BOARD.indexOf(app.stage);
    const next = idx >= 0 && idx < BOARD.length - 1 ? BOARD[idx + 1] : null;
    const ctc = fmtCtc(app.ctc_lpa);
    return (
        <article
            role="button"
            tabIndex={0}
            draggable={draggable}
            onDragStart={(e) => { e.dataTransfer.setData('text/plain', String(app.id)); e.dataTransfer.effectAllowed = 'move'; onDragStart(app.id); }}
            onDragEnd={onDragEnd}
            onClick={() => onOpen(app)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(app); } }}
            className={cx(
                'group card p-3 cursor-pointer select-none transition-[border-color,transform,opacity] duration-150',
                'hover:border-line-strong focus-visible:outline-2 focus-visible:outline-accent active:scale-[0.99]',
                draggable && 'cursor-grab active:cursor-grabbing',
                dragging && 'opacity-40',
            )}
            aria-label={`${app.company}${app.role ? `, ${app.role}` : ''}. ${STAGE[app.stage]?.label}. Open details`}
        >
            <div className="flex items-start gap-2.5">
                <Monogram name={app.company} />
                <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold leading-tight truncate">{app.company}</p>
                    <p className="text-xs text-muted truncate mt-0.5">{app.role || 'Role TBD'}</p>
                </div>
                {next && (
                    <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); onAdvance(app, next); }}
                        className="btn btn-ghost btn-sm btn-icon h-7 w-7 -mr-1 -mt-0.5 shrink-0 opacity-70 group-hover:opacity-100"
                        aria-label={`Move ${app.company} to ${STAGE[next].label}`}
                        title={`Move to ${STAGE[next].label}`}
                    >
                        <ChevronRight className="h-4 w-4" aria-hidden />
                    </button>
                )}
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <SourceChip source={app.source} />
                {ctc && <span className={cx('badge tabular-nums', app.stage === 'offer' ? 'text-ok bg-ok/10' : 'text-fg bg-surface-2')}>{ctc}</span>}
                {app.stage !== 'offer' && <DeadlineBadge deadline={app.deadline} />}
            </div>
            {app.next_event_at && (
                <div className="mt-2">
                    <NextEvent app={app} now={now} />
                </div>
            )}
        </article>
    );
}

function Column({ stage, apps, now, finePointer, dragId, setDragId, onDropTo, onOpen, onAdvance, onAdd }) {
    const [over, setOver] = useState(false);
    const depth = useRef(0);
    return (
        <section
            aria-label={`${STAGE[stage].label}, ${apps.length}`}
            onDragEnter={(e) => { if (dragId == null) return; e.preventDefault(); depth.current += 1; setOver(true); }}
            onDragOver={(e) => { if (dragId == null) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
            onDragLeave={() => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setOver(false); }}
            onDrop={(e) => {
                e.preventDefault();
                depth.current = 0;
                setOver(false);
                const id = Number(e.dataTransfer.getData('text/plain') || dragId);
                if (id) onDropTo(id, stage);
                setDragId(null);
            }}
            className={cx(
                'snap-start shrink-0 w-[80vw] max-w-[300px] sm:w-[260px] xl:w-auto xl:max-w-none min-w-0',
                'flex flex-col rounded-2xl border p-2 transition-colors',
                over ? 'border-accent bg-accent-soft' : 'border-line bg-surface-2/60',
            )}
        >
            <header className="flex items-center gap-2 px-1.5 pt-1 pb-2">
                <StageDot stage={stage} />
                <h3 className="text-[13px] font-semibold tracking-tight">{STAGE[stage].label}</h3>
                <span className="text-xs text-subtle tabular-nums">{apps.length}</span>
                <button
                    type="button"
                    onClick={() => onAdd(stage)}
                    className="btn btn-ghost btn-sm btn-icon h-7 w-7 ml-auto"
                    aria-label={`Add to ${STAGE[stage].label}`}
                    title={`Add to ${STAGE[stage].label}`}
                >
                    <Plus className="h-3.5 w-3.5" aria-hidden />
                </button>
            </header>
            <div className="flex flex-col gap-2 min-h-[5.5rem] flex-1">
                {apps.map((a) => (
                    <AppCard
                        key={a.id}
                        app={a}
                        now={now}
                        onOpen={onOpen}
                        onAdvance={onAdvance}
                        draggable={finePointer}
                        dragging={dragId === a.id}
                        onDragStart={setDragId}
                        onDragEnd={() => setDragId(null)}
                    />
                ))}
                {!apps.length && (
                    <div className={cx('flex-1 grid place-items-center rounded-xl border border-dashed px-3 py-5 text-center text-xs', over ? 'border-accent text-accent' : 'border-line-strong text-subtle')}>
                        {dragId != null ? 'Drop here' : STAGE[stage].hint}
                    </div>
                )}
            </div>
        </section>
    );
}

function ClosedTray({ apps, open, setOpen, dragId, setDragId, onDropTo, onOpen }) {
    const [over, setOver] = useState(false);
    return (
        <Card
            className={cx('overflow-hidden transition-colors', over && 'border-accent bg-accent-soft')}
            onDragOver={(e) => { if (dragId == null) return; e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
                e.preventDefault();
                setOver(false);
                const id = Number(e.dataTransfer.getData('text/plain') || dragId);
                if (id) onDropTo(id, 'rejected');
                setDragId(null);
            }}
        >
            <button
                type="button"
                onClick={() => setOpen(!open)}
                aria-expanded={open}
                className="w-full flex items-center gap-3 px-4 py-3 text-left row-hover"
            >
                <Archive className="h-4 w-4 text-subtle shrink-0" aria-hidden />
                <span className="text-sm font-medium">Closed</span>
                <span className="text-xs text-subtle tabular-nums">{apps.length}</span>
                <span className="text-xs text-subtle truncate hidden sm:inline">
                    {dragId != null ? 'Drop here to mark rejected' : 'Rejected and withdrawn'}
                </span>
                <ChevronDown className={cx('h-4 w-4 text-subtle ml-auto shrink-0 transition-transform', open && 'rotate-180')} aria-hidden />
            </button>
            {open && (
                apps.length ? (
                    <ul className="border-t border-line divide-y divide-line">
                        {apps.map((a) => (
                            <li key={a.id}>
                                <button type="button" onClick={() => onOpen(a)} className="w-full flex items-center gap-3 px-4 py-2.5 text-left row-hover">
                                    <Monogram name={a.company} className="h-8 w-8 opacity-70" />
                                    <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium truncate">{a.company}</p>
                                        <p className="text-xs text-subtle truncate">{a.role || 'Role TBD'}</p>
                                    </div>
                                    <span className={cx('badge', a.stage === 'rejected' ? 'text-danger bg-danger/10' : 'text-muted bg-surface-2')}>{STAGE[a.stage].label}</span>
                                    <span className="text-xs text-subtle shrink-0 hidden sm:inline">{timeAgo(a.stage_changed_at)}</span>
                                </button>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className="border-t border-line px-4 py-4 text-[13px] text-subtle">Nothing closed yet. Rejections are part of the process, so log them and move on.</p>
                )
            )}
        </Card>
    );
}

// ---------------- summary + upcoming ----------------
function Stat({ value, label, tone }) {
    return (
        <div className="px-3 py-3 sm:px-4 sm:py-4 min-w-0">
            <div className={cx('text-[22px] sm:text-2xl font-bold tabular-nums tracking-tight leading-none', tone)}>{value}</div>
            <div className="text-[11px] sm:text-xs text-subtle truncate mt-1.5">{label}</div>
        </div>
    );
}

function SummaryStrip({ s }) {
    return (
        <Card className="overflow-hidden animate-rise">
            <div className="flex flex-col sm:flex-row">
                <div className="grid grid-cols-4 flex-1 divide-x divide-line">
                    <Stat value={s.active} label="Active" />
                    <Stat value={s.oa} label="OAs pending" tone={s.oa ? 'text-accent' : ''} />
                    <Stat value={s.interviews} label="Interviews" tone={s.interviews ? 'text-accent' : ''} />
                    <Stat value={s.offers} label="Offers" tone={s.offers ? 'text-ok' : ''} />
                </div>
                <div className="hero-accent flex items-center gap-3 px-4 py-3 sm:py-4 border-t sm:border-t-0 sm:border-l border-line sm:min-w-[13rem]">
                    <div className={cx('grid place-items-center h-9 w-9 rounded-xl border border-line bg-surface shrink-0', s.best ? 'text-ok' : 'text-subtle')}>
                        <Trophy className="h-4 w-4" aria-hidden />
                    </div>
                    <div className="min-w-0">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle">Best CTC</div>
                        {s.best ? (
                            <div className="text-[15px] font-bold tabular-nums truncate">
                                {fmtCtc(s.best.ctc_lpa)} <span className="text-xs font-medium text-muted">· {s.best.company}</span>
                            </div>
                        ) : (
                            <div className="text-[13px] text-muted truncate">No offers yet. Keep going.</div>
                        )}
                    </div>
                </div>
            </div>
        </Card>
    );
}

function UpcomingList({ items, now, onOpen }) {
    const [all, setAll] = useState(false);
    const shown = all ? items : items.slice(0, 4);
    return (
        <Card className="overflow-hidden">
            <div className="card-pad pb-0">
                <CardHeader title="Upcoming" subtitle="Rounds and deadlines in the next 14 days" icon={CalendarClock} />
            </div>
            {items.length ? (
                <ul className="border-t border-line divide-y divide-line">
                    {shown.map((it) => {
                        const ms = it.t - now;
                        const urgent = it.kind === 'deadline' ? it.n <= 2 : ms < DAY;
                        return (
                            <li key={it.key}>
                                <button type="button" onClick={() => onOpen(it.app)} className="w-full flex items-center gap-3 px-4 py-3 text-left row-hover">
                                    <div className={cx('grid place-items-center h-9 w-9 rounded-[10px] border border-line shrink-0', urgent ? (it.kind === 'deadline' ? 'text-danger bg-danger/10' : 'text-accent bg-accent-soft') : 'text-muted bg-surface-2')}>
                                        {it.kind === 'deadline' ? <Flag className="h-4 w-4" aria-hidden /> : <CalendarClock className="h-4 w-4" aria-hidden />}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium truncate">
                                            {it.app.company} <span className="text-muted font-normal">· {it.label}</span>
                                        </p>
                                        <p className="text-xs text-subtle truncate">
                                            {it.kind === 'deadline' ? fmtDate(it.app.deadline) : fmtWhen(it.t)}
                                            {it.app.role ? ` · ${it.app.role}` : ''}
                                        </p>
                                    </div>
                                    <span className={cx('text-xs font-semibold tabular-nums shrink-0', urgent ? (it.kind === 'deadline' ? 'text-danger' : 'text-accent') : 'text-muted')}>
                                        {it.kind === 'deadline' ? deadlineText(it.n) : countdown(ms)}
                                    </span>
                                </button>
                            </li>
                        );
                    })}
                </ul>
            ) : (
                <p className="border-t border-line px-4 sm:px-5 py-4 text-[13px] text-subtle">
                    Nothing scheduled. Add an OA or interview time to a company and it shows up here with a countdown.
                </p>
            )}
            {items.length > 4 && (
                <div className="border-t border-line px-3 py-2 bg-surface-2/40 flex">
                    <button type="button" className="btn btn-ghost btn-sm ml-auto" onClick={() => setAll((v) => !v)} aria-expanded={all}>
                        {all ? 'Show less' : `Show all (${items.length})`}
                        <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', all && 'rotate-180')} aria-hidden />
                    </button>
                </div>
            )}
        </Card>
    );
}

// ---------------- sheet: form + timeline ----------------
const toForm = (a, stage) => ({
    company: a?.company || '',
    role: a?.role || '',
    source: a?.source || 'on-campus',
    stage: a?.stage || stage || 'applied',
    ctc_lpa: a?.ctc_lpa ?? '',
    location: a?.location || '',
    link: a?.link || '',
    deadline: a?.deadline || '',
    next_event_label: a?.next_event_label || '',
    next_event_at: toLocalInput(a?.next_event_at),
    notes: a?.notes || '',
});

function toBody(f) {
    return {
        company: f.company.trim(),
        role: f.role.trim(),
        source: f.source,
        ctc_lpa: f.ctc_lpa === '' || f.ctc_lpa == null ? null : Number(f.ctc_lpa),
        location: f.location.trim() || null,
        link: f.link.trim() || null,
        deadline: f.deadline || null,
        next_event_label: f.next_event_label.trim() || null,
        next_event_at: f.next_event_at ? new Date(f.next_event_at).toISOString() : null,
        notes: f.notes,
    };
}

function Field({ label, children, className }) {
    return (
        <label className={cx('block min-w-0', className)}>
            <span className="label">{label}</span>
            {children}
        </label>
    );
}

function AppForm({ initial, isNew, saving, onSubmit, onCancel }) {
    const [f, setF] = useState(initial);
    const [base, setBase] = useState(initial); // last saved values, for the dirty check
    const [error, setError] = useState('');
    const set = (k) => (e) => setF((x) => ({ ...x, [k]: e?.target ? e.target.value : e }));
    const dirty = useMemo(() => JSON.stringify(f) !== JSON.stringify(base), [f, base]);

    const submit = async (e) => {
        e.preventDefault();
        if (!f.company.trim()) { setError('Company is required.'); return; }
        if (f.ctc_lpa !== '' && (Number.isNaN(Number(f.ctc_lpa)) || Number(f.ctc_lpa) < 0)) { setError('CTC must be a positive number (LPA).'); return; }
        setError('');
        const snapshot = f;
        const ok = await onSubmit(isNew ? { ...toBody(f), stage: f.stage } : toBody(f));
        if (ok) setBase(snapshot);
    };

    return (
        <form onSubmit={submit} className="space-y-4" noValidate>
            {isNew && (
                <div>
                    <span className="label">Stage</span>
                    <StagePicker value={f.stage} onChange={set('stage')} />
                </div>
            )}
            <div className="grid sm:grid-cols-2 gap-3">
                <Field label="Company *">
                    <input className="input" value={f.company} onChange={set('company')} placeholder="e.g. Atlassian" maxLength={120} autoFocus={isNew} aria-invalid={!!error && !f.company.trim()} />
                </Field>
                <Field label="Role">
                    <input className="input" value={f.role} onChange={set('role')} placeholder="SDE 1, SDE Intern + FTE" maxLength={160} />
                </Field>
            </div>
            <div>
                <span className="label">Source</span>
                <Segmented options={SOURCES} value={f.source} onChange={set('source')} className="w-full [&>button]:flex-1" />
            </div>
            <div className="grid grid-cols-2 gap-3">
                <Field label="CTC (LPA)">
                    <input className="input tabular-nums" type="number" inputMode="decimal" min="0" step="0.1" value={f.ctc_lpa} onChange={set('ctc_lpa')} placeholder="e.g. 18" />
                </Field>
                <Field label="Location">
                    <input className="input" value={f.location} onChange={set('location')} placeholder="Bengaluru" maxLength={120} />
                </Field>
            </div>
            <Field label="Job / portal link">
                <input className="input" type="url" inputMode="url" value={f.link} onChange={set('link')} placeholder="https://careers..." maxLength={500} />
            </Field>
            <div className="rounded-xl border border-line bg-surface-2/50 p-3 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                    <Field label="Next round">
                        <input className="input" value={f.next_event_label} onChange={set('next_event_label')} placeholder="OA on HackerRank" maxLength={160} />
                    </Field>
                    <Field label="When">
                        <input className="input" type="datetime-local" value={f.next_event_at} onChange={set('next_event_at')} />
                    </Field>
                </div>
                <Field label="Application deadline">
                    <input className="input" type="date" value={f.deadline} onChange={set('deadline')} />
                </Field>
            </div>
            <Field label="Notes">
                <textarea className="input h-auto min-h-24 py-2.5 leading-relaxed resize-y" value={f.notes} onChange={set('notes')} placeholder="Eligibility, CGPA cutoff, bond, prep topics, interviewer names..." rows={3} />
            </Field>
            {error && <p className="text-[13px] text-danger" role="alert">{error}</p>}
            <div className="flex items-center gap-2 pt-1">
                {onCancel && <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>}
                <Button type="submit" variant="primary" loading={saving} disabled={!isNew && !dirty} className="ml-auto" icon={isNew ? Plus : Pencil}>
                    {isNew ? 'Add application' : 'Save changes'}
                </Button>
            </div>
        </form>
    );
}

const EVENT_ICON = { stage: ArrowRight, note: StickyNote, round: Target };

function Timeline({ app, onAdd }) {
    const [kind, setKind] = useState('round');
    const [text, setText] = useState('');
    const [busy, setBusy] = useState(false);
    const events = app.events || [];

    const submit = async (e) => {
        e.preventDefault();
        const t = text.trim();
        if (!t) return;
        setBusy(true);
        const ok = await onAdd(app, { kind, text: t });
        setBusy(false);
        if (ok) setText('');
    };

    return (
        <div>
            <div className="flex items-center justify-between gap-3 mb-3">
                <h3 className="eyebrow">Timeline</h3>
                <Segmented options={[{ value: 'round', label: 'Round' }, { value: 'note', label: 'Note' }]} value={kind} onChange={setKind} />
            </div>
            <form onSubmit={submit} className="flex gap-2 mb-4">
                <input
                    className="input"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={kind === 'round' ? 'Round 1 - DSA: graphs + DP, went well' : 'Recruiter said results by Friday'}
                    maxLength={1000}
                    aria-label={kind === 'round' ? 'Add a round' : 'Add a note'}
                />
                <Button type="submit" variant="secondary" loading={busy} disabled={!text.trim()} icon={Plus} className="shrink-0">Add</Button>
            </form>
            {events.length ? (
                <ol className="relative ml-1">
                    {events.map((ev, i) => {
                        const Icon = EVENT_ICON[ev.kind] || StickyNote;
                        return (
                            <li key={ev.id} className="relative flex gap-3 pb-4 last:pb-0">
                                {i < events.length - 1 && <span aria-hidden className="absolute left-[13px] top-7 bottom-0 w-px bg-line" />}
                                <div className={cx('grid place-items-center h-7 w-7 rounded-full border border-line shrink-0', ev.kind === 'round' ? 'bg-accent-soft text-accent' : ev.kind === 'stage' ? 'bg-surface-2 text-muted' : 'bg-surface text-subtle')}>
                                    <Icon className="h-3.5 w-3.5" aria-hidden />
                                </div>
                                <div className="min-w-0 flex-1 pt-0.5">
                                    <p className={cx('text-sm leading-snug break-words whitespace-pre-wrap', ev.kind === 'stage' ? 'text-muted' : 'text-fg')}>{ev.text}</p>
                                    <p className="text-[11px] text-subtle mt-0.5" title={ev.at ? new Date(ev.at).toLocaleString() : ''}>
                                        {ev.kind === 'round' ? 'Round · ' : ev.kind === 'note' ? 'Note · ' : ''}{timeAgo(ev.at)}
                                    </p>
                                </div>
                            </li>
                        );
                    })}
                </ol>
            ) : (
                <p className="text-[13px] text-subtle">Log each round as it happens. Future you will want the questions before the next interview.</p>
            )}
        </div>
    );
}

function DetailSheet({ app, onClose, onMove, onSave, onDelete, onAddEvent }) {
    const [saving, setSaving] = useState(false);
    const [confirm, setConfirm] = useState(false);
    const [initial] = useState(() => toForm(app));

    useEffect(() => {
        if (!confirm) return;
        const id = setTimeout(() => setConfirm(false), 4000);
        return () => clearTimeout(id);
    }, [confirm]);

    return (
        <div className="p-5 sm:p-6 pt-3 sm:pt-6 space-y-6">
            <div className="flex items-start gap-3 pr-10">
                <Monogram name={app.company} className="h-11 w-11 text-base rounded-xl" />
                <div className="min-w-0">
                    <h2 className="text-lg font-semibold tracking-tight leading-tight truncate">{app.company}</h2>
                    <p className="text-[13px] text-muted truncate">{app.role || 'Role TBD'}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <SourceChip source={app.source} />
                        {fmtCtc(app.ctc_lpa) && <span className="badge text-fg bg-surface-2 tabular-nums">{fmtCtc(app.ctc_lpa)}</span>}
                        {app.location && <span className="badge text-muted bg-surface-2"><MapPin className="h-3 w-3" aria-hidden />{app.location}</span>}
                        {app.link && (
                            <a href={app.link} target="_blank" rel="noreferrer" className="badge text-accent bg-accent-soft hover:underline">
                                Open link <ExternalLink className="h-3 w-3" aria-hidden />
                            </a>
                        )}
                    </div>
                </div>
            </div>

            <div>
                <div className="flex items-center justify-between mb-2">
                    <span className="label mb-0">Move to</span>
                    <span className="text-[11px] text-subtle">in {STAGE[app.stage]?.label} since {timeAgo(app.stage_changed_at)}</span>
                </div>
                <StagePicker value={app.stage} onChange={(s) => onMove(app, s)} />
            </div>

            <Timeline app={app} onAdd={onAddEvent} />

            <div className="border-t border-line pt-5">
                <h3 className="eyebrow mb-3">Details</h3>
                <AppForm
                    key={app.id}
                    initial={initial}
                    saving={saving}
                    onSubmit={async (body) => { setSaving(true); const ok = await onSave(app, body); setSaving(false); return ok; }}
                />
            </div>

            <div className="border-t border-line pt-4 flex items-center gap-3">
                <p className="text-xs text-subtle flex-1 min-w-0">Added {timeAgo(app.created_at)}</p>
                <Button
                    variant="danger"
                    size="sm"
                    icon={Trash2}
                    onClick={() => { if (confirm) { onDelete(app); onClose(); } else setConfirm(true); }}
                >
                    {confirm ? 'Tap again to delete' : 'Delete'}
                </Button>
            </div>
        </div>
    );
}

// ---------------- empty + loading ----------------
function Welcome({ onAdd }) {
    const steps = [
        [Briefcase, 'Shortlist', 'Drop every company you might apply to in Wishlist.'],
        [CalendarClock, 'Schedule', 'Add OA and interview times. Countdowns keep you honest.'],
        [Trophy, 'Convert', 'Move cards forward round by round until the offer lands.'],
    ];
    return (
        <Card className="card-pad hero-accent animate-rise">
            <Empty
                icon={Kanban}
                title="Track every company from wishlist to offer"
                action={<Button variant="primary" icon={Plus} onClick={() => onAdd('wishlist')}>Add your first company</Button>}
            >
                On-campus drives, off-campus applications and referrals in one board, with deadlines and rounds that never slip.
            </Empty>
            <div className="grid sm:grid-cols-3 gap-2.5 mt-1">
                {steps.map(([Icon, title, body], i) => (
                    <div key={title} className="rounded-xl border border-line bg-surface p-3.5 animate-rise" style={{ animationDelay: `${80 + i * 60}ms` }}>
                        <div className="flex items-center gap-2 mb-1">
                            <Icon className="h-4 w-4 text-accent" aria-hidden />
                            <span className="text-[13px] font-semibold">{i + 1}. {title}</span>
                        </div>
                        <p className="text-xs text-subtle leading-relaxed">{body}</p>
                    </div>
                ))}
            </div>
        </Card>
    );
}

function BoardSkeleton() {
    return (
        <div className="space-y-5" aria-busy="true">
            <Skeleton className="h-[76px] rounded-2xl" />
            <div className="flex gap-3 overflow-hidden xl:grid xl:grid-cols-6">
                {BOARD.map((s) => (
                    <div key={s} className="shrink-0 w-[80vw] max-w-[300px] sm:w-[260px] xl:w-auto rounded-2xl border border-line bg-surface-2/60 p-2 space-y-2">
                        <Skeleton className="h-5 w-20 m-1.5" />
                        <Skeleton className="h-20 rounded-2xl bg-surface-3" />
                        <Skeleton className="h-20 rounded-2xl bg-surface-3" />
                    </div>
                ))}
            </div>
        </div>
    );
}

// ---------------- page ----------------
export default function Placements() {
    const list = useApi('/placements');
    const toast = useToast();
    const now = useNow();
    const [sheet, setSheet] = useState(null); // { mode: 'new', stage } | { mode: 'edit', id }
    const [creating, setCreating] = useState(false);
    const [dragId, setDragId] = useState(null);
    const [closedOpen, setClosedOpen] = useLocalStorage('placements:closed-open', false);
    const [storedFilter, setFilter] = useLocalStorage('placements:source', 'all');
    const filter = FILTERS.some((x) => x.value === storedFilter) ? storedFilter : 'all';
    const finePointer = useMemo(() => typeof window !== 'undefined' && !!window.matchMedia?.('(pointer: fine)').matches, []);

    const apps = useMemo(() => list.data || [], [list.data]);
    const { setData, reload } = list;
    const summary = useMemo(() => summarize(apps), [apps]);
    const upcoming = useMemo(() => buildUpcoming(apps, now), [apps, now]);
    const visible = useMemo(() => (filter === 'all' ? apps : apps.filter((a) => a.source === filter)), [apps, filter]);
    const byStage = useMemo(() => {
        const m = Object.fromEntries([...BOARD, ...CLOSED].map((s) => [s, []]));
        for (const a of visible) (m[a.stage] || m.wishlist).push(a);
        const ts = (a) => (a.next_event_at ? new Date(a.next_event_at).getTime() : Infinity);
        for (const s of BOARD) m[s].sort((a, b) => ts(a) - ts(b) || (b.updated_at || '').localeCompare(a.updated_at || ''));
        return m;
    }, [visible]);
    const closed = useMemo(() => [...byStage.rejected, ...byStage.withdrawn].sort((a, b) => (b.stage_changed_at || '').localeCompare(a.stage_changed_at || '')), [byStage]);

    const current = sheet?.mode === 'edit' ? apps.find((a) => a.id === sheet.id) : null;
    const closeSheet = useCallback(() => setSheet(null), []);
    const openApp = useCallback((a) => setSheet({ mode: 'edit', id: a.id }), []);
    const openNew = useCallback((stage = 'applied') => setSheet({ mode: 'new', stage }), []);

    const replace = useCallback((row) => setData((d) => (d || []).map((a) => (a.id === row.id ? row : a))), [setData]);

    const update = useCallback(async (app, body, { optimistic = body, success } = {}) => {
        setData((d) => (d || []).map((a) => (a.id === app.id ? { ...a, ...optimistic } : a)));
        try {
            const res = await api(`/placements/${app.id}`, { method: 'PUT', body });
            replace(res.data);
            if (success) toast(success);
            return true;
        } catch (e) {
            toast(e.message, 'error');
            reload({ silent: true });
            return false;
        }
    }, [setData, replace, reload, toast]);

    const move = useCallback((app, stage) => {
        if (!app || app.stage === stage) return;
        const label = STAGE[stage].label;
        update(app, { stage }, {
            optimistic: { stage, stage_changed_at: new Date().toISOString() },
            success: stage === 'offer' ? `Offer from ${app.company}. Congratulations!` : `${app.company} moved to ${label}`,
        });
    }, [update]);

    const moveById = useCallback((id, stage) => move(apps.find((a) => a.id === id), stage), [apps, move]);

    const create = async (body) => {
        setCreating(true);
        try {
            const res = await api('/placements', { method: 'POST', body });
            setData((d) => [res.data, ...(d || [])]);
            toast(`Added ${res.data.company} to ${STAGE[res.data.stage]?.label || 'pipeline'}`);
            if (filter !== 'all' && res.data.source !== filter) setFilter('all');
            setSheet(null);
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setCreating(false);
        }
    };

    const remove = async (app) => {
        setData((d) => (d || []).filter((a) => a.id !== app.id));
        try {
            await api(`/placements/${app.id}`, { method: 'DELETE' });
            toast(`Deleted ${app.company}`);
        } catch (e) {
            toast(e.message, 'error');
            reload({ silent: true });
        }
    };

    const addEvent = async (app, body) => {
        const temp = { id: `tmp-${Date.now()}`, application_id: app.id, ...body, at: new Date().toISOString() };
        setData((d) => (d || []).map((a) => (a.id === app.id ? { ...a, events: [temp, ...(a.events || [])] } : a)));
        try {
            const res = await api(`/placements/${app.id}/events`, { method: 'POST', body });
            replace(res.application);
            return true;
        } catch (e) {
            toast(e.message, 'error');
            reload({ silent: true });
            return false;
        }
    };

    const hasApps = apps.length > 0;

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="animate-rise flex items-end justify-between gap-3">
                <div className="min-w-0">
                    <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Placements</h1>
                    <p className="text-sm text-muted mt-1">Every company, from wishlist to offer. Campus drives and off-campus in one board.</p>
                </div>
                {hasApps && (
                    <Button variant="primary" icon={Plus} onClick={() => openNew('applied')} className="shrink-0" aria-label="Add application">
                        <span className="hidden sm:inline">Add application</span>
                        <span className="sm:hidden">Add</span>
                    </Button>
                )}
            </header>

            {list.loading && !list.data ? (
                <BoardSkeleton />
            ) : list.error && !list.data ? (
                <Card>
                    <Empty icon={Building2} title="Couldn't load your pipeline" action={<Button size="sm" icon={RefreshCw} onClick={() => reload()}>Retry</Button>}>
                        {list.error}
                    </Empty>
                </Card>
            ) : !hasApps ? (
                <Welcome onAdd={openNew} />
            ) : (
                <>
                    <SummaryStrip s={summary} />

                    {upcoming.length > 0 && <UpcomingList items={upcoming} now={now} onOpen={openApp} />}

                    <div>
                        <div className="flex items-center justify-between gap-3 mb-3">
                            <div className="flex items-center gap-2 min-w-0">
                                <Kanban className="h-4 w-4 text-subtle shrink-0" aria-hidden />
                                <h2 className="text-[15px] font-semibold tracking-tight">Pipeline</h2>
                                <span className="text-xs text-subtle hidden sm:inline truncate">
                                    {finePointer ? 'Drag cards between columns, or open one to move it' : 'Tap a card to move it or log a round'}
                                </span>
                            </div>
                            <Segmented options={FILTERS} value={filter} onChange={setFilter} className="shrink-0" />
                        </div>
                        <div className="-mx-4 sm:-mx-6 lg:mx-0">
                            <div className="flex gap-3 overflow-x-auto snap-x snap-mandatory scroll-px-4 sm:scroll-px-6 lg:scroll-px-0 px-4 sm:px-6 lg:px-0 pb-2 no-scrollbar xl:grid xl:grid-cols-6 xl:overflow-visible xl:snap-none">
                                {BOARD.map((s) => (
                                    <Column
                                        key={s}
                                        stage={s}
                                        apps={byStage[s]}
                                        now={now}
                                        finePointer={finePointer}
                                        dragId={dragId}
                                        setDragId={setDragId}
                                        onDropTo={moveById}
                                        onOpen={openApp}
                                        onAdvance={move}
                                        onAdd={openNew}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>

                    <ClosedTray
                        apps={closed}
                        open={closedOpen}
                        setOpen={setClosedOpen}
                        dragId={dragId}
                        setDragId={setDragId}
                        onDropTo={moveById}
                        onOpen={openApp}
                    />
                </>
            )}

            <Sheet open={!!sheet && (sheet.mode === 'new' || !!current)} onClose={closeSheet}>
                {sheet?.mode === 'new' && (
                    <div className="p-5 sm:p-6 pt-3 sm:pt-6">
                        <div className="flex items-center gap-3 mb-5 pr-10">
                            <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0">
                                <Briefcase className="h-5 w-5" aria-hidden />
                            </div>
                            <div className="min-w-0">
                                <h2 className="text-lg font-semibold tracking-tight">Add application</h2>
                                <p className="text-[13px] text-subtle truncate">Only the company is required. Fill the rest as you learn more.</p>
                            </div>
                        </div>
                        <AppForm key={`new-${sheet.stage}`} initial={toForm(null, sheet.stage)} isNew saving={creating} onSubmit={create} onCancel={closeSheet} />
                    </div>
                )}
                {sheet?.mode === 'edit' && current && (
                    <DetailSheet
                        key={current.id}
                        app={current}
                        onClose={closeSheet}
                        onMove={move}
                        onSave={(app, body) => update(app, body, { success: 'Saved' })}
                        onDelete={remove}
                        onAddEvent={addEvent}
                    />
                )}
            </Sheet>
        </div>
    );
}
