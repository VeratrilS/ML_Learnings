import { useEffect, useState } from 'react';
import { Moon, ArrowLeft, ArrowRight, Check, Pencil, Trophy, CircleAlert, ListOrdered } from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, CardHeader, Checkbox, Skeleton, useToast, cx } from './ui';

const IST_OFFSET = 5.5 * 3600 * 1000;
const istHour = () => new Date(Date.now() + IST_OFFSET).getUTCHours();
// The journal day rolls over at 04:00 IST, so "evening" runs 18:00 → 04:00.
const isEveningNow = () => { const h = istHour(); return h >= 18 || h < 4; };

const STEPS = [
    { label: 'Clear the ring', hint: 'Check off what got done. Anything left carries to tomorrow on its own.' },
    { label: 'Corner check', hint: 'How did today actually feel?' },
    { label: 'Review the round', hint: 'One thing that landed, one thing that got in the way.' },
    { label: "Tomorrow's game plan", hint: 'The three things that would make tomorrow a win.' },
];
const MOOD = ['Rough', 'Low', 'Okay', 'Good', 'Great'];
const ENERGY = ['Empty', 'Low', 'Steady', 'Good', 'Full'];
const MAX_TEXT = 500;
const MAX_ITEM = 300;

const blankDraft = () => ({ mood: null, energy: null, win: '', blocker: '', top3: ['', '', ''] });
const draftFrom = (e) => ({
    mood: e?.mood ?? null,
    energy: e?.energy ?? null,
    win: e?.win || '',
    blocker: e?.blocker || '',
    top3: [0, 1, 2].map((i) => e?.top3?.[i] || ''),
});

/**
 * Evening shutdown ritual. `rev` bumps when the plan/journal changed elsewhere;
 * `onPlanChange` / `onSaved` tell the page we changed them.
 */
export default function ShutdownCard({ rev = 0, onPlanChange, onSaved }) {
    const toast = useToast();
    const journal = useApi('/journal/today', { select: (d) => d, deps: [rev] });
    const todos = useApi('/todos', { deps: [rev] });
    const [expanded, setExpanded] = useState(isEveningNow);
    const [editing, setEditing] = useState(false);
    const [step, setStep] = useState(0);
    const [draft, setDraft] = useState(blankDraft);
    const [saving, setSaving] = useState(false);
    const [touched, setTouched] = useState(() => new Set()); // ticked here: keep them visible while the step is open

    const entry = journal.data?.data;
    const closed = !!entry && !editing;

    // NowCard's "Close the day" button opens the ritual.
    useEffect(() => {
        const onOpen = () => setExpanded(true);
        window.addEventListener('shutdown-open', onOpen);
        return () => window.removeEventListener('shutdown-open', onOpen);
    }, []);

    const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
    const setTop = (i, v) => setDraft((d) => ({ ...d, top3: d.top3.map((x, j) => (j === i ? v : x)) }));

    const toggleTodo = async (t, done) => {
        setTouched((s) => new Set(s).add(t.id));
        todos.setData((list) => (list || []).map((x) => (x.id === t.id ? { ...x, done } : x)));
        try {
            await api(`/todos/${t.id}`, { method: 'PUT', body: { done } });
            onPlanChange?.();
        } catch (e) {
            toast(e.message, 'error');
            todos.reload({ silent: true });
        }
    };

    const save = async () => {
        setSaving(true);
        try {
            const res = await api('/journal/today', {
                method: 'PUT',
                body: {
                    mood: draft.mood,
                    energy: draft.energy,
                    win: draft.win.trim(),
                    blocker: draft.blocker.trim(),
                    top3: draft.top3.map((x) => x.trim()).filter(Boolean),
                },
            });
            journal.setData((d) => ({ ...(d || {}), data: res.data }));
            setEditing(false);
            setStep(0);
            toast('Day closed. Rest well.');
            onSaved?.();
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setSaving(false);
        }
    };

    const startEdit = () => {
        setDraft(draftFrom(entry));
        setStep(1);
        setEditing(true);
        setExpanded(true);
    };

    if (journal.loading && !journal.data) {
        return <Card className="card-pad"><Skeleton className="h-8 w-48 mb-4" /><Skeleton className="h-20 w-full" /></Card>;
    }

    if (closed) return <ClosedSummary entry={entry} onEdit={startEdit} />;

    if (!expanded) {
        return (
            <Card className="card-pad">
                <div className="flex items-center gap-3">
                    <div className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line text-muted shrink-0">
                        <Moon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                        <h2 className="text-[15px] font-semibold tracking-tight">Close the day</h2>
                        <p className="text-xs text-subtle truncate">Shutdown ritual · opens properly at 6 PM</p>
                    </div>
                    <Button size="sm" variant="secondary" onClick={() => setExpanded(true)}>Start early</Button>
                </div>
            </Card>
        );
    }

    const open = (todos.data || []).filter((t) => !t.done);
    const doneToday = (todos.data || []).filter((t) => t.done);
    const last = step === STEPS.length - 1;

    return (
        <Card className="card-pad">
            <CardHeader
                title="Close the day"
                subtitle={`Step ${step + 1} of ${STEPS.length} · ${STEPS[step].label}`}
                icon={Moon}
                action={editing && <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setStep(0); }}>Cancel</Button>}
                className="mb-3"
            />

            <div className="grid grid-cols-4 gap-1.5 mb-4" aria-hidden>
                {STEPS.map((s, i) => (
                    <button
                        key={s.label}
                        type="button"
                        tabIndex={-1}
                        onClick={() => setStep(i)}
                        className={cx('h-1.5 rounded-full transition-colors', i <= step ? 'bg-accent' : 'bg-surface-3')}
                        title={s.label}
                    />
                ))}
            </div>

            <p className="text-[13px] text-muted mb-3">{STEPS[step].hint}</p>

            <div key={step} className="animate-rise min-h-[8.5rem]">
                {step === 0 && (
                    todos.loading && !todos.data ? (
                        <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8" />)}</div>
                    ) : open.length === 0 && touched.size === 0 ? (
                        <div className="flex items-center gap-2.5 rounded-xl bg-ok/10 border border-ok/25 px-3 py-2.5 text-sm">
                            <Check className="h-4 w-4 text-ok shrink-0" strokeWidth={3} />
                            <span>{doneToday.length ? `All ${doneToday.length} done. Clean round.` : 'Nothing on the plan to clear.'}</span>
                        </div>
                    ) : (
                        <ul className="rounded-xl border border-line divide-y divide-line overflow-hidden">
                            {(todos.data || []).filter((t) => !t.done || touched.has(t.id)).map((t) => (
                                <li key={t.id} className="flex items-start gap-2.5 px-3 py-2.5">
                                    <Checkbox checked={!!t.done} onChange={(v) => toggleTodo(t, v)} label={`Mark "${t.text}" done`} className="mt-px" />
                                    <span className="text-sm leading-5 min-w-0 break-words [overflow-wrap:anywhere]">{t.text}</span>
                                </li>
                            ))}
                        </ul>
                    )
                )}

                {step === 1 && (
                    <div className="space-y-4">
                        <ScalePicker label="Mood" names={MOOD} value={draft.mood} onChange={(v) => set('mood', v)} />
                        <ScalePicker label="Energy" names={ENERGY} value={draft.energy} onChange={(v) => set('energy', v)} />
                    </div>
                )}

                {step === 2 && (
                    <div className="space-y-3">
                        <div>
                            <label className="label" htmlFor="sd-win">One win</label>
                            <input id="sd-win" className="input" maxLength={MAX_TEXT} value={draft.win}
                                onChange={(e) => set('win', e.target.value)} placeholder="Solved a Hard without hints" enterKeyHint="next" />
                        </div>
                        <div>
                            <label className="label" htmlFor="sd-blocker">One blocker</label>
                            <input id="sd-blocker" className="input" maxLength={MAX_TEXT} value={draft.blocker}
                                onChange={(e) => set('blocker', e.target.value)} placeholder="Lost an hour to my phone" enterKeyHint="done" />
                        </div>
                    </div>
                )}

                {step === 3 && (
                    <div className="space-y-2">
                        {draft.top3.map((v, i) => (
                            <div key={i} className="relative">
                                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 grid place-items-center h-5 w-5 rounded-md bg-accent-soft text-accent text-[11px] font-bold">
                                    {i + 1}
                                </span>
                                <input className="input pl-10" maxLength={MAX_ITEM} value={v} onChange={(e) => setTop(i, e.target.value)}
                                    aria-label={`Tomorrow's priority ${i + 1}`}
                                    placeholder={['Two mediums: graphs', 'System design lesson + notes', 'Revise DBMS unit 4'][i]}
                                    onKeyDown={(e) => { if (e.key === 'Enter' && i === 2 && !saving) save(); }}
                                    enterKeyHint={i === 2 ? 'done' : 'next'} />
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="mt-4 flex items-center justify-between gap-2">
                <Button size="sm" variant="ghost" icon={ArrowLeft} onClick={() => setStep((s) => s - 1)} disabled={step === 0}>Back</Button>
                {last ? (
                    <Button variant="primary" icon={Moon} loading={saving} onClick={save}>Close the day</Button>
                ) : (
                    <Button variant="primary" onClick={() => setStep((s) => s + 1)}>
                        {step === 0 && open.length ? 'Carry the rest' : 'Next'} <ArrowRight className="h-4 w-4" />
                    </Button>
                )}
            </div>
        </Card>
    );
}

function ScalePicker({ label, names, value, onChange }) {
    return (
        <div role="radiogroup" aria-label={label}>
            <div className="flex items-baseline justify-between mb-1.5">
                <span className="text-[13px] font-medium text-muted">{label}</span>
                <span className="text-xs text-subtle">{value ? names[value - 1] : 'Tap one'}</span>
            </div>
            <div className="grid grid-cols-5 gap-1.5">
                {names.map((n, i) => {
                    const v = i + 1;
                    const on = value === v;
                    return (
                        <button
                            key={n}
                            type="button"
                            role="radio"
                            aria-checked={on}
                            aria-label={`${label} ${v}: ${n}`}
                            onClick={() => onChange(on ? null : v)}
                            className={cx(
                                'h-11 rounded-xl border flex flex-col items-center justify-center leading-none transition-colors',
                                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                                on ? 'bg-accent-soft border-accent/40 text-accent' : 'border-line bg-surface-2/50 text-muted hover:text-fg hover:border-line-strong',
                            )}
                        >
                            <span className="text-[15px] font-bold tabular-nums">{v}</span>
                            <span className="mt-1 text-[10px] font-medium opacity-80">{n}</span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

function ClosedSummary({ entry, onEdit }) {
    const hasRatings = entry.mood || entry.energy;
    return (
        <Card className="card-pad">
            <div className="flex items-start gap-3">
                <div className="grid place-items-center h-8 w-8 rounded-lg bg-ok/10 border border-ok/25 text-ok shrink-0">
                    <Check className="h-4 w-4" strokeWidth={3} />
                </div>
                <div className="min-w-0 flex-1">
                    <h2 className="text-[15px] font-semibold tracking-tight">Day closed. Rest well.</h2>
                    <p className="text-xs text-subtle">
                        {hasRatings
                            ? [entry.mood && `Mood ${MOOD[entry.mood - 1].toLowerCase()}`, entry.energy && `energy ${ENERGY[entry.energy - 1].toLowerCase()}`].filter(Boolean).join(' · ')
                            : 'Round logged.'}
                    </p>
                </div>
                <Button size="sm" variant="ghost" icon={Pencil} onClick={onEdit} aria-label="Edit today's shutdown">Edit</Button>
            </div>

            {(entry.win || entry.blocker) && (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                    {entry.win && (
                        <div className="flex items-start gap-2 text-sm min-w-0">
                            <Trophy className="h-4 w-4 text-accent shrink-0 mt-0.5" />
                            <span className="min-w-0 break-words [overflow-wrap:anywhere]">{entry.win}</span>
                        </div>
                    )}
                    {entry.blocker && (
                        <div className="flex items-start gap-2 text-sm min-w-0 text-muted">
                            <CircleAlert className="h-4 w-4 text-subtle shrink-0 mt-0.5" />
                            <span className="min-w-0 break-words [overflow-wrap:anywhere]">{entry.blocker}</span>
                        </div>
                    )}
                </div>
            )}

            {entry.top3?.length > 0 && (
                <div className="mt-4 pt-3 border-t border-line">
                    <div className="eyebrow mb-2 flex items-center gap-1.5"><ListOrdered className="h-3.5 w-3.5" /> Tomorrow's top 3</div>
                    <ol className="space-y-1.5">
                        {entry.top3.map((t, i) => (
                            <li key={i} className="flex items-start gap-2.5 text-sm">
                                <span className="grid place-items-center h-5 w-5 rounded-md bg-accent-soft text-accent text-[11px] font-bold shrink-0 mt-px">{i + 1}</span>
                                <span className="min-w-0 break-words [overflow-wrap:anywhere]">{t}</span>
                            </li>
                        ))}
                    </ol>
                </div>
            )}
        </Card>
    );
}
