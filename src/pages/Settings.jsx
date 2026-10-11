import { useEffect, useState } from 'react';
import { Mail, User, Tv, Wrench, ShieldCheck, Lock, Plus, Trash2, Minus, Star, Save, Smartphone, CircleCheck, CircleAlert, Pencil, X } from 'lucide-react';
import { api, setToken } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, CardHeader, Skeleton, Toggle, useToast, cx } from '../components/ui';

const INTERVALS = [[5, '5 minutes'], [10, '10 minutes'], [30, '30 minutes'], [60, '1 hour'], [120, '2 hours'], [240, '4 hours'], [480, '8 hours'], [720, '12 hours'], [1440, '24 hours']];
const DIFFICULTIES = [['mixed', 'Mixed (Easy → Hard)'], ['easy', 'Easy only'], ['easy-medium', 'Easy + Medium'], ['medium', 'Medium only'], ['medium-hard', 'Medium + Hard'], ['hard', 'Hard only']];
const hourLabel = (h) => new Date(2000, 0, 1, h).toLocaleTimeString(undefined, { hour: 'numeric' });

function Row({ title, desc, children }) {
    return (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-6 py-3.5 border-t border-line first:border-t-0 first:pt-0">
            <div className="min-w-0">
                <div className="text-sm font-medium">{title}</div>
                {desc && <div className="text-xs text-subtle mt-0.5">{desc}</div>}
            </div>
            <div className="shrink-0 flex items-center gap-2">{children}</div>
        </div>
    );
}

export default function Settings() {
    const settings = useApi('/settings', { select: (d) => d });
    const toast = useToast();
    const s = settings.data;

    const save = async (patch, msg = 'Saved') => {
        settings.setData((d) => ({ ...d, ...patch }));
        try {
            const res = await api('/settings', { method: 'POST', body: patch });
            settings.setData(res);
            if (msg) toast(msg);
            return true;
        } catch (e) {
            toast(e.message, 'error');
            settings.reload({ silent: true });
            return false;
        }
    };

    return (
        <div className="space-y-5 sm:space-y-6 max-w-3xl">
            <header className="animate-rise">
                <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Settings</h1>
                <p className="text-sm text-muted mt-1">Tune your automations. Everything syncs between phone and laptop.</p>
            </header>

            <Card className="card-pad">
                <CardHeader title="Daily problem email" subtitle={s ? `Delivered to ${s.receiver_email}` : ' '} icon={Mail} />
                {!s ? <Skeleton className="h-40" /> : (
                    <div>
                        <Row title="Send problems automatically" desc={s.leetcode_paused === '1' ? 'Paused. No emails will be sent.' : 'Active via the scheduler.'}>
                            <Toggle checked={s.leetcode_paused !== '1'} onChange={(v) => save({ leetcode_paused: v ? '0' : '1' }, v ? 'Resumed' : 'Paused')} label="Automatic emails" />
                        </Row>
                        <Row title="Frequency" desc="Minimum time between two problems.">
                            <select className="input w-44" value={s.leetcode_interval_minutes} onChange={(e) => save({ leetcode_interval_minutes: e.target.value })}>
                                {INTERVALS.map(([v, l]) => <option key={v} value={v}>Every {l}</option>)}
                            </select>
                        </Row>
                        <Row title="Quiet hours (IST)" desc="No emails during this window. Set both equal to disable.">
                            <select className="input w-[6.5rem]" value={s.quiet_start} onChange={(e) => save({ quiet_start: e.target.value })} aria-label="Quiet hours start">
                                {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
                            </select>
                            <span className="text-subtle text-sm">to</span>
                            <select className="input w-[6.5rem]" value={s.quiet_end} onChange={(e) => save({ quiet_end: e.target.value })} aria-label="Quiet hours end">
                                {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
                            </select>
                        </Row>
                        <Row title="Difficulty" desc="Which problems the picker draws from.">
                            <select className="input w-52" value={s.leetcode_difficulty} onChange={(e) => save({ leetcode_difficulty: e.target.value })}>
                                {DIFFICULTIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                        </Row>
                        <Row title="Daily goal" desc="Problems to solve per day (LeetCode + Codeforces).">
                            <div className="flex items-center gap-1">
                                <button className="btn btn-secondary btn-icon btn-sm" aria-label="Decrease" onClick={() => save({ daily_goal: Math.max(1, Number(s.daily_goal) - 1) }, null)}><Minus className="h-3.5 w-3.5" /></button>
                                <span className="w-10 text-center font-semibold tabular-nums">{s.daily_goal}</span>
                                <button className="btn btn-secondary btn-icon btn-sm" aria-label="Increase" onClick={() => save({ daily_goal: Math.min(20, Number(s.daily_goal) + 1) }, null)}><Plus className="h-3.5 w-3.5" /></button>
                            </div>
                        </Row>
                    </div>
                )}
            </Card>

            <Card className="card-pad">
                <CardHeader title="Accounts" subtitle="Used to auto-mark solved problems and tune Codeforces difficulty" icon={User} />
                {!s ? <Skeleton className="h-24" /> : (
                    <div className="grid sm:grid-cols-2 gap-4">
                        <HandleField label="LeetCode username" value={s.leetcode_username} placeholder="e.g. sairaghava"
                            onSave={async (v) => {
                                if (!(await save({ leetcode_username: v }, null))) return;
                                if (!v) return toast('LeetCode username removed');
                                try {
                                    const p = (await api('/leetcode/profile')).data;
                                    toast(`Connected · ${p.total} solved (${p.easy}E / ${p.medium}M / ${p.hard}H)`);
                                } catch (e) { toast(e.message, 'error'); }
                            }} />
                        <HandleField label="Codeforces handle" value={s.cf_handle} placeholder="e.g. tourist"
                            onSave={async (v) => {
                                if (!(await save({ cf_handle: v }, null))) return;
                                if (!v) return toast('Codeforces handle removed');
                                try {
                                    const m = await api('/cf/meta');
                                    if (m.user?.error) toast(m.user.error, 'error');
                                    else toast(`Connected · ${m.user?.rating ? `rating ${m.user.rating}` : 'unrated'}`);
                                } catch (e) { toast(e.message, 'error'); }
                            }} />
                    </div>
                )}
            </Card>

            <SeriesManager />

            <Card className="card-pad">
                <CardHeader title="Tools" icon={Wrench} />
                <ToolRow title="Incident reporter" desc="Emails a synthetic incident report (runs daily at 2 PM IST)." type="incident" />
            </Card>

            <Card className="card-pad">
                <CardHeader title="System" icon={ShieldCheck} />
                {!s ? <Skeleton className="h-16" /> : (
                    <div className="grid sm:grid-cols-2 gap-3">
                        <Status ok={s.llm_configured} label="Gemini AI" desc={s.llm_configured ? 'Write-ups, PDF notes and quizzes' : 'Set GEMINI_API_KEY'} />
                        <Status ok={s.email_configured} label="Email delivery" desc={s.email_configured ? 'Gmail SMTP connected' : 'Set SENDER_EMAIL / SENDER_PASSWORD'} />
                    </div>
                )}
                <div className="mt-4 rounded-xl bg-surface-2 border border-line p-4 flex gap-3">
                    <Smartphone className="h-5 w-5 text-accent shrink-0 mt-0.5" />
                    <div className="text-sm text-muted space-y-1">
                        <p><span className="text-fg font-medium">Install on your phone:</span> open this site in Chrome → menu → <em>Add to Home screen</em> (Safari: Share → Add to Home Screen).</p>
                        <p><span className="text-fg font-medium">Make it your homepage:</span> browser settings → On startup / Home button → <span className="font-mono text-xs bg-surface px-1.5 py-0.5 rounded border border-line">{window.location.origin}</span></p>
                        <p className="text-xs text-subtle">Keyboard: 1-6 switch sections · Ctrl/⌘ K opens the command palette · N adds a task.</p>
                    </div>
                </div>
                <div className="mt-3 flex justify-end">
                    <Button size="sm" variant="ghost" icon={Lock} onClick={() => { setToken(''); window.location.reload(); }}>Lock this device</Button>
                </div>
            </Card>
        </div>
    );
}

function Status({ ok, label, desc }) {
    const Icon = ok ? CircleCheck : CircleAlert;
    return (
        <div className="flex items-start gap-2.5 rounded-xl border border-line p-3">
            <Icon className={cx('h-4 w-4 mt-0.5 shrink-0', ok ? 'text-ok' : 'text-danger')} />
            <div><div className="text-sm font-medium">{label}</div><div className="text-xs text-subtle">{desc}</div></div>
        </div>
    );
}

function HandleField({ label, value, placeholder, onSave }) {
    const [v, setV] = useState(value || '');
    const [busy, setBusy] = useState(false);
    useEffect(() => setV(value || ''), [value]);
    const dirty = v.trim() !== (value || '');
    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        await onSave(v.trim());
        setBusy(false);
    };
    return (
        <form onSubmit={submit}>
            <label className="label">{label}</label>
            <div className="flex gap-2">
                <input className="input" value={v} onChange={(e) => setV(e.target.value)} placeholder={placeholder} autoCapitalize="off" autoCorrect="off" spellCheck={false} />
                <Button type="submit" variant={dirty ? 'primary' : 'secondary'} loading={busy} disabled={!dirty} icon={Save} className="h-10">Save</Button>
            </div>
        </form>
    );
}

function ToolRow({ title, desc, type }) {
    const [busy, setBusy] = useState(false);
    const toast = useToast();
    const run = async () => {
        setBusy(true);
        try {
            const r = await api('/trigger', { method: 'POST', body: { type } });
            toast(`Sent: ${r.data.title}`);
        } catch (e) { toast(e.message, 'error'); } finally { setBusy(false); }
    };
    return <Row title={title} desc={desc}><Button size="sm" loading={busy} onClick={run} icon={Mail}>Send now</Button></Row>;
}

const EMPTY_SERIES = { title: '', url_template: '', total_episodes: 24, next_episode: 1 };

function SeriesManager() {
    const series = useApi('/watch');
    const toast = useToast();
    const [form, setForm] = useState(null);   // null | {id?, ...fields}
    const [busy, setBusy] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const body = { ...form, total_episodes: Number(form.total_episodes), next_episode: Number(form.next_episode) };
            if (form.id) await api(`/watch/${form.id}`, { method: 'PUT', body });
            else await api('/watch', { method: 'POST', body });
            toast(form.id ? 'Series updated' : 'Series added');
            setForm(null);
            series.reload({ silent: true });
        } catch (err) { toast(err.message, 'error'); } finally { setBusy(false); }
    };

    const act = async (path, method, body, msg) => {
        try {
            await api(path, { method, body });
            if (msg) toast(msg);
            series.reload({ silent: true });
        } catch (e) { toast(e.message, 'error'); }
    };

    return (
        <Card className="card-pad">
            <CardHeader title="Daily episode" subtitle="One episode a day, linked straight from your homepage" icon={Tv}
                action={!form && <Button size="sm" icon={Plus} onClick={() => setForm(EMPTY_SERIES)}>Add series</Button>} />
            {series.loading && !series.data ? <Skeleton className="h-16" /> : (
                <ul className="space-y-2">
                    {series.data?.map((x) => (
                        <li key={x.id} className={cx('rounded-xl border p-3 sm:p-3.5', x.is_active ? 'border-accent/40 bg-accent-soft' : 'border-line')}>
                            <div className="flex items-start gap-3">
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-semibold truncate">{x.title}</span>
                                        {x.is_active && <span className="badge bg-accent text-accent-fg">Active</span>}
                                    </div>
                                    <div className="text-xs text-subtle mt-0.5">
                                        {x.finished ? 'Finished' : `Next: episode ${x.next_episode}`} of {x.total_episodes} · {x.progress}%
                                    </div>
                                    <div className="text-[11px] text-subtle font-mono truncate mt-1">{x.url_template}</div>
                                </div>
                                <div className="flex items-center gap-0.5 shrink-0">
                                    <button className="btn btn-ghost btn-icon btn-sm" title="Previous episode" aria-label="Previous episode"
                                        onClick={() => act(`/watch/${x.id}`, 'PUT', { next_episode: Math.max(1, x.next_episode - 1) })}><Minus className="h-3.5 w-3.5" /></button>
                                    <button className="btn btn-ghost btn-icon btn-sm" title="Skip ahead" aria-label="Next episode"
                                        onClick={() => act(`/watch/${x.id}`, 'PUT', { next_episode: Math.min(x.total_episodes + 1, x.next_episode + 1) })}><Plus className="h-3.5 w-3.5" /></button>
                                    {!x.is_active && (
                                        <button className="btn btn-ghost btn-icon btn-sm" title="Make active" aria-label="Make active"
                                            onClick={() => act(`/watch/${x.id}`, 'PUT', { is_active: true }, `Now watching ${x.title}`)}><Star className="h-3.5 w-3.5" /></button>
                                    )}
                                    <button className="btn btn-ghost btn-icon btn-sm" title="Edit" aria-label="Edit"
                                        onClick={() => setForm({ id: x.id, title: x.title, url_template: x.url_template, total_episodes: x.total_episodes, next_episode: x.next_episode })}><Pencil className="h-3.5 w-3.5" /></button>
                                    <button className="btn btn-danger btn-icon btn-sm" title="Delete" aria-label="Delete"
                                        onClick={() => window.confirm(`Delete ${x.title}?`) && act(`/watch/${x.id}`, 'DELETE', null, 'Deleted')}><Trash2 className="h-3.5 w-3.5" /></button>
                                </div>
                            </div>
                        </li>
                    ))}
                </ul>
            )}

            {form && (
                <form onSubmit={submit} className="mt-4 rounded-xl border border-line bg-surface-2/50 p-4 space-y-3 animate-rise">
                    <div className="flex items-center justify-between">
                        <div className="text-sm font-semibold">{form.id ? 'Edit series' : 'New series'}</div>
                        <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => setForm(null)} aria-label="Cancel"><X className="h-4 w-4" /></button>
                    </div>
                    <div>
                        <label className="label">Title</label>
                        <input className="input" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Hajime no Ippo: Rising" />
                    </div>
                    <div>
                        <label className="label">Episode URL — use <span className="font-mono text-accent">{'{ep}'}</span> for the episode number</label>
                        <input className="input font-mono text-[13px]" required value={form.url_template} onChange={(e) => setForm({ ...form, url_template: e.target.value })}
                            placeholder="https://anikoto.cz/watch/show-slug/ep-{ep}" autoCapitalize="off" spellCheck={false} />
                        <p className="text-xs text-subtle mt-1.5">Tip: paste any episode link, then replace its number with {'{ep}'}.</p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="label">Total episodes</label>
                            <input className="input" type="number" min="1" required value={form.total_episodes} onChange={(e) => setForm({ ...form, total_episodes: e.target.value })} />
                        </div>
                        <div>
                            <label className="label">Next episode</label>
                            <input className="input" type="number" min="1" required value={form.next_episode} onChange={(e) => setForm({ ...form, next_episode: e.target.value })} />
                        </div>
                    </div>
                    <div className="flex justify-end gap-2 pt-1">
                        <Button type="button" variant="ghost" onClick={() => setForm(null)}>Cancel</Button>
                        <Button type="submit" variant="primary" loading={busy}>{form.id ? 'Save' : 'Add & make active'}</Button>
                    </div>
                </form>
            )}
        </Card>
    );
}
