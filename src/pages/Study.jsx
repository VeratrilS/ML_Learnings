import { useMemo, useState } from 'react';
import {
    GraduationCap, BookOpen, CalendarClock, Plus, ClipboardPaste, Trash2, Pencil, Mail, Flame, ChevronDown,
    FlaskConical, ListChecks, Sparkles, Check, Target, Copy, RefreshCw, Loader2, FolderArchive, FileText,
    Link2, BookMarked, Code2, ExternalLink, ChevronUp, FileDown,
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi, useLocalStorage } from '../lib/hooks';
import Markdown from '../components/Markdown';
import {
    Button, Card, Checkbox, Empty, ProgressBar, ProgressRing, Segmented, Sheet, Skeleton, useToast, cx,
} from '../components/ui';

// Per-subject accents (data colours, rendered with inline styles so they work in both themes)
const COLORS = {
    violet: '#7c5cff', teal: '#0d9488', rose: '#e11d48', amber: '#d97706',
    blue: '#2563eb', green: '#16a34a', pink: '#db2777', orange: '#e8590c',
};
const COLOR_KEYS = Object.keys(COLORS);
const hexOf = (s) => COLORS[s?.color] || (/^#[0-9a-f]{3,8}$/i.test(s?.color || '') ? s.color : 'var(--accent)');
const tint = (hex, alpha = '1f') => (hex.startsWith('#') && hex.length === 7 ? `${hex}${alpha}` : 'var(--accent-soft)');

const KINDS = [{ value: 'theory', label: 'Theory' }, { value: 'lab', label: 'Lab' }, { value: 'other', label: 'Other' }];
const CONF_LABEL = { 1: 'Shaky', 2: 'Okay', 3: 'Solid' };
const CONF_BG = { 1: 'bg-danger', 2: 'bg-accent', 3: 'bg-ok' };

const MATERIAL_CATEGORIES = [
    { value: 'lecture_notes', label: 'Lecture Notes', icon: FileText, color: 'text-blue-500 bg-blue-500/10 border-blue-500/20' },
    { value: 'cheatsheet', label: 'Cheatsheet', icon: Sparkles, color: 'text-amber-500 bg-amber-500/10 border-amber-500/20' },
    { value: 'reference', label: 'Reference Link', icon: Link2, color: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20' },
    { value: 'exam_paper', label: 'Exam Paper', icon: BookMarked, color: 'text-purple-500 bg-purple-500/10 border-purple-500/20' },
    { value: 'code', label: 'Code & Labs', icon: Code2, color: 'text-rose-500 bg-rose-500/10 border-rose-500/20' },
    { value: 'other', label: 'Other', icon: FileDown, color: 'text-subtle bg-surface-2 border-line' },
];

const istDay = (d) => d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
const studiedToday = (iso) => !!iso && istDay(new Date(iso)) === istDay(new Date());
const parseDay = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const fmtDate = (s, long) => (s ? parseDay(s).toLocaleDateString(undefined, long
    ? { weekday: 'long', day: 'numeric', month: 'long' }
    : { weekday: 'short', day: 'numeric', month: 'short' }) : '');
const initials = (s) => s.short || s.name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w) && !/^(and|of|the|for|by|in)$/i.test(w)).slice(0, 3).map((w) => w[0].toUpperCase()).join('');
const unitParts = (label) => {
    if (!label) return ['', 'Topics'];
    const i = label.indexOf(' · ');
    return i < 0 ? [label, ''] : [label.slice(0, i), label.slice(i + 3)];
};

function daysText(d, compact) {
    if (d == null) return 'No date';
    if (d < 0) return 'Exam done';
    if (d === 0) return 'Today';
    if (d === 1) return 'Tomorrow';
    return compact ? `${d}d left` : `${d} days left`;
}

function DaysBadge({ days, compact, className }) {
    const tone = days == null || days < 0 ? 'text-muted bg-surface-2'
        : days <= 7 ? 'text-danger bg-danger/10'
            : days <= 14 ? 'text-accent bg-accent-soft' : 'text-muted bg-surface-2';
    return <span className={cx('badge', tone, className)}>{daysText(days, compact)}</span>;
}

// Recomputes done / total / progress after a local edit to a subject's topics.
function withTopics(subject, fn) {
    const units = subject.units.map((u) => ({ ...u, topics: fn(u.topics) })).filter((u) => u.topics.length);
    const all = units.flatMap((u) => u.topics);
    const done = all.filter((t) => t.done).length;
    return { ...subject, units, total: all.length, done, progress: all.length ? Math.round((100 * done) / all.length) : 0 };
}

export default function Study() {
    const res = useApi('/syllabus', { select: (d) => d });
    const toast = useToast();
    const [sheet, setSheet] = useState(null); // {type:'subject', subject?} | {type:'topics', subject}
    const [reminding, setReminding] = useState(false);

    const subjects = useMemo(() => res.data?.data || [], [res.data]);
    const theory = subjects.filter((s) => s.kind === 'theory');
    const others = subjects.filter((s) => s.kind !== 'theory');
    const next = res.data?.next_exam || null;

    const setSubjects = (fn) => res.setData((d) => ({ ...d, data: fn(d.data) }));
    const replaceSubject = (s) => setSubjects((list) => list.map((x) => (x.id === s.id ? s : x)));
    const refresh = () => res.reload({ silent: true });

    const updateTopic = async (topic, body) => {
        const patch = { ...body };
        if ('studied' in patch) {
            patch.last_studied_at = patch.studied ? new Date().toISOString() : null;
            delete patch.studied;
        }
        setSubjects((list) => list.map((s) => (s.id !== topic.subject_id ? s
            : withTopics(s, (ts) => ts.map((t) => (t.id === topic.id ? { ...t, ...patch } : t))))));
        try {
            await api(`/syllabus/topics/${topic.id}`, { method: 'PUT', body });
            if (body.done) toast(`Covered: ${topic.title}`);
        } catch (e) {
            toast(e.message, 'error');
            refresh();
        }
    };

    const deleteTopic = async (topic) => {
        setSubjects((list) => list.map((s) => (s.id !== topic.subject_id ? s
            : withTopics(s, (ts) => ts.filter((t) => t.id !== topic.id)))));
        try {
            await api(`/syllabus/topics/${topic.id}`, { method: 'DELETE' });
        } catch (e) {
            toast(e.message, 'error');
            refresh();
        }
    };

    const onTopicGenerated = (topic, updatedTopic) => {
        setSubjects((list) => list.map((s) => (s.id !== topic.subject_id ? s
            : withTopics(s, (ts) => ts.map((t) => (t.id === topic.id ? { ...t, ...updatedTopic } : t))))));
    };

    const addMaterial = async (subjectId, materialData) => {
        try {
            const res = await api(`/syllabus/subjects/${subjectId}/materials`, { method: 'POST', body: materialData });
            if (res?.data) {
                setSubjects((list) => list.map((s) => {
                    if (s.id !== subjectId) return s;
                    const mats = [res.data, ...(s.materials || [])];
                    return { ...s, materials: mats, materials_count: mats.length };
                }));
                toast(`Added material "${materialData.title}"`, 'success');
                return true;
            }
        } catch (e) {
            toast(e.message || 'Failed to add material', 'error');
            return false;
        }
    };

    const deleteMaterial = async (subjectId, materialId) => {
        try {
            await api(`/syllabus/materials/${materialId}`, { method: 'DELETE' });
            setSubjects((list) => list.map((s) => {
                if (s.id !== subjectId) return s;
                const mats = (s.materials || []).filter((m) => m.id !== materialId);
                return { ...s, materials: mats, materials_count: mats.length };
            }));
            toast('Material removed', 'info');
        } catch (e) {
            toast(e.message || 'Failed to delete material', 'error');
        }
    };

    const remind = async () => {
        setReminding(true);
        try {
            const r = await api('/syllabus/remind?force=1', { method: 'POST' });
            toast(r.message || 'Reminder sent', r.status === 'success' ? 'success' : 'info');
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setReminding(false);
        }
    };

    const loading = res.loading && !res.data;

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 animate-rise">
                <div className="min-w-0">
                    <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">End-sem prep</h1>
                    <p className="text-sm text-muted mt-1">Your syllabus, unit by unit. Tick topics off, rate how well you know them, walk in ready.</p>
                </div>
                <div className="flex flex-wrap gap-2 shrink-0">
                    <Button icon={Mail} loading={reminding} onClick={remind}>Send reminder now</Button>
                    <Button variant="primary" icon={Plus} onClick={() => setSheet({ type: 'subject' })}>Add subject</Button>
                </div>
            </header>

            {res.error && !res.data && (
                <Card className="card-pad text-sm text-danger">{res.error}</Card>
            )}

            {loading ? <HeroSkeleton /> : res.data && <Hero theory={theory} next={next} />}

            {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
                    {[0, 1].map((i) => <Card key={i} className="card-pad"><Skeleton className="h-10 w-2/3" /><Skeleton className="h-2 w-full mt-5" /><Skeleton className="h-32 w-full mt-5" /></Card>)}
                </div>
            ) : res.data && (
                theory.length ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5 items-start">
                        {theory.map((s, i) => (
                            <SubjectCard key={s.id} subject={s} index={i}
                                onUpdateTopic={updateTopic} onDeleteTopic={deleteTopic}
                                onTopicGenerated={onTopicGenerated}
                                onAddMaterial={addMaterial} onDeleteMaterial={deleteMaterial}
                                onEdit={() => setSheet({ type: 'subject', subject: s })}
                                onAddTopics={() => setSheet({ type: 'topics', subject: s })} />
                        ))}
                    </div>
                ) : (
                    <Card>
                        <Empty icon={GraduationCap} title="No theory subjects yet"
                            action={<Button variant="primary" size="sm" icon={Plus} onClick={() => setSheet({ type: 'subject' })}>Add a subject</Button>}>
                            Add each end-sem subject, then paste its syllabus. Units and topics are detected for you.
                        </Empty>
                    </Card>
                )
            )}

            {res.data && others.length > 0 && (
                <OtherCourses courses={others} onUpdateTopic={updateTopic} onDeleteTopic={deleteTopic}
                    onTopicGenerated={onTopicGenerated}
                    onAddMaterial={addMaterial} onDeleteMaterial={deleteMaterial}
                    onEdit={(s) => setSheet({ type: 'subject', subject: s })}
                    onAddTopics={(s) => setSheet({ type: 'topics', subject: s })} />
            )}

            <SubjectSheet open={sheet?.type === 'subject'} subject={sheet?.subject} onClose={() => setSheet(null)}
                onSaved={(s, created) => { if (!created) replaceSubject(s); setSheet(null); refresh(); }}
                onDeleted={() => { setSheet(null); refresh(); }} />
            <AddTopicsSheet open={sheet?.type === 'topics'} subject={sheet?.subject} onClose={() => setSheet(null)}
                onAdded={(s, keepOpen) => { replaceSubject(s); setSheet(keepOpen ? { type: 'topics', subject: s } : null); }} />
        </div>
    );
}

// ---------------- Hero ----------------
function HeroSkeleton() {
    return (
        <Card className="card-pad">
            <div className="flex items-center justify-between gap-6">
                <div className="space-y-3 flex-1"><Skeleton className="h-3 w-24" /><Skeleton className="h-14 w-40" /><Skeleton className="h-4 w-52" /></div>
                <Skeleton className="h-24 w-24 rounded-full" />
            </div>
        </Card>
    );
}

function Hero({ theory, next }) {
    const all = theory.flatMap((s) => s.units.flatMap((u) => u.topics));
    const total = all.length;
    const done = all.filter((t) => t.done).length;
    const pct = total ? Math.round((100 * done) / total) : 0;
    const shaky = all.filter((t) => !t.done && t.confidence === 1).length;
    const today = all.filter((t) => studiedToday(t.last_studied_at)).length;
    const nextSubject = next && theory.find((s) => s.id === next.id);
    const hex = nextSubject ? hexOf(nextSubject) : 'var(--accent)';
    const d = next?.days_left;

    return (
        <Card className="relative overflow-hidden animate-rise">
            <div aria-hidden className="pointer-events-none absolute -top-28 -left-16 h-72 w-72 rounded-full opacity-[0.16] blur-3xl" style={{ background: hex }} />
            <div aria-hidden className="pointer-events-none absolute -bottom-32 -right-10 h-64 w-64 rounded-full bg-accent opacity-[0.08] blur-3xl" />
            <div className="relative card-pad">
                <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                    <div className="min-w-0">
                        <div className="eyebrow flex items-center gap-1.5"><CalendarClock className="h-3.5 w-3.5" /> Next exam</div>
                        {next ? (
                            <>
                                <div className="mt-2 flex items-end gap-3">
                                    {d > 1 ? (
                                        <>
                                            <span className="text-6xl sm:text-7xl font-extrabold tracking-tighter leading-[0.85] tabular-nums" style={{ color: hex }}>{d}</span>
                                            <span className="pb-1 text-base font-semibold text-muted">days to go</span>
                                        </>
                                    ) : (
                                        <span className="text-5xl sm:text-6xl font-extrabold tracking-tighter leading-none" style={{ color: hex }}>{d === 0 ? 'Today' : 'Tomorrow'}</span>
                                    )}
                                </div>
                                <div className="mt-3 text-[17px] font-semibold tracking-tight leading-snug">
                                    {next.subject}
                                    {next.short && <span className="ml-2 badge align-middle" style={{ color: hex, background: tint(hex) }}>{next.short}</span>}
                                </div>
                                <div className="text-sm text-subtle mt-0.5">{fmtDate(next.date, true)}{next.code ? ` · ${next.code}` : ''}</div>
                            </>
                        ) : (
                            <>
                                <div className="mt-2 text-2xl sm:text-3xl font-bold tracking-tight">No exam dates yet</div>
                                <p className="text-sm text-muted mt-1.5 max-w-md">Tap the pencil on a subject to add its exam date. The countdown and reminders follow the nearest one.</p>
                            </>
                        )}
                    </div>

                    <div className="flex items-center gap-4 sm:gap-5 sm:pl-6 sm:border-l sm:border-line">
                        <ProgressRing value={done} max={total || 1} size={104} stroke={9}>
                            <div className="text-center leading-none">
                                <div className="text-2xl font-extrabold tracking-tight tabular-nums">{pct}<span className="text-sm font-bold text-subtle">%</span></div>
                                <div className="text-[10px] font-semibold uppercase tracking-wider text-subtle mt-1">covered</div>
                            </div>
                        </ProgressRing>
                        <div className="space-y-2 text-sm min-w-0">
                            <HeroStat icon={ListChecks} label="topics done" value={`${done}/${total}`} />
                            <HeroStat icon={Target} label="shaky left" value={shaky} tone={shaky ? 'text-danger' : undefined} />
                            <HeroStat icon={Flame} label="studied today" value={today} tone={today ? 'text-accent' : undefined} />
                        </div>
                    </div>
                </div>

                {theory.some((s) => s.exam_date) && (
                    <div className="mt-5 pt-4 border-t border-line flex flex-wrap gap-2">
                        {theory.map((s) => (
                            <span key={s.id} className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 pl-2 pr-1 h-8 text-xs font-medium">
                                <span className="h-2 w-2 rounded-full shrink-0" style={{ background: hexOf(s) }} />
                                <span className="truncate max-w-[9rem]">{s.short || s.name}</span>
                                <span className="text-subtle hidden sm:inline">{s.exam_date ? fmtDate(s.exam_date) : ''}</span>
                                <DaysBadge days={s.days_left} compact className="rounded-full px-2" />
                            </span>
                        ))}
                    </div>
                )}
            </div>
        </Card>
    );
}

function HeroStat({ icon: Icon, label, value, tone }) {
    return (
        <div className="flex items-center gap-2 whitespace-nowrap">
            <Icon className={cx('h-3.5 w-3.5 shrink-0', tone || 'text-subtle')} />
            <span className="font-semibold tabular-nums">{value}</span>
            <span className="text-subtle text-xs">{label}</span>
        </div>
    );
}

// ---------------- Subject card ----------------
function SubjectCard({
    subject: s, index, onUpdateTopic, onDeleteTopic, onTopicGenerated,
    onAddMaterial, onDeleteMaterial, onEdit, onAddTopics,
}) {
    const hex = hexOf(s);
    const [tab, setTab] = useState('topics');
    const [managing, setManaging] = useState(false);
    const [showMaterialSheet, setShowMaterialSheet] = useState(false);
    const shaky = s.units.reduce((n, u) => n + u.topics.filter((t) => !t.done && t.confidence === 1).length, 0);

    return (
        <Card className="relative overflow-hidden animate-rise" style={{ animationDelay: `${index * 50}ms` }}>
            <div aria-hidden className="absolute inset-x-0 top-0 h-1" style={{ background: hex }} />
            <div aria-hidden className="pointer-events-none absolute -top-24 -right-24 h-56 w-56 rounded-full opacity-[0.12] blur-3xl" style={{ background: hex }} />
            <div className="relative card-pad">
                <div className="flex items-start gap-3">
                    <div className="grid place-items-center h-11 w-11 rounded-xl shrink-0 text-[13px] font-extrabold tracking-tight"
                        style={{ color: hex, background: tint(hex), boxShadow: `inset 0 0 0 1px ${tint(hex, '33')}` }}>
                        {initials(s) || <BookOpen className="h-5 w-5" />}
                    </div>
                    <div className="min-w-0 flex-1">
                        <h3 className="text-base font-semibold tracking-tight leading-snug">{s.name}</h3>
                        <p className="text-xs text-subtle mt-0.5 truncate">
                            {[s.code, s.faculty].filter(Boolean).join(' · ') || 'Add course code and faculty'}
                        </p>
                    </div>
                    <button className="btn btn-ghost btn-icon btn-sm -mr-1.5 -mt-1" onClick={onEdit} aria-label={`Edit ${s.name}`} title="Edit subject">
                        <Pencil className="h-3.5 w-3.5" />
                    </button>
                </div>

                <div className="mt-4 flex items-center justify-between gap-3 text-[13px]">
                    {s.exam_date ? (
                        <span className="inline-flex items-center gap-1.5 text-muted min-w-0">
                            <CalendarClock className="h-3.5 w-3.5 shrink-0" />
                            <span className="truncate">Exam {fmtDate(s.exam_date)}</span>
                        </span>
                    ) : (
                        <button onClick={onEdit} className="inline-flex items-center gap-1.5 text-subtle hover:text-accent transition-colors">
                            <CalendarClock className="h-3.5 w-3.5" /> Set exam date
                        </button>
                    )}
                    {s.exam_date && <DaysBadge days={s.days_left} />}
                </div>

                {/* Tab Switcher: Topics vs Materials Vault */}
                <div className="mt-4 flex items-center justify-between border-b border-line pb-1.5">
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            onClick={() => setTab('topics')}
                            className={cx(
                                'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5',
                                tab === 'topics' ? 'bg-surface-2 text-fg shadow-xs border border-line' : 'text-subtle hover:text-fg'
                            )}
                        >
                            <ListChecks className="h-3.5 w-3.5" />
                            <span>Topics ({s.total})</span>
                        </button>
                        <button
                            type="button"
                            onClick={() => setTab('materials')}
                            className={cx(
                                'px-2.5 py-1 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5',
                                tab === 'materials' ? 'bg-surface-2 text-fg shadow-xs border border-line' : 'text-subtle hover:text-fg'
                            )}
                        >
                            <FolderArchive className="h-3.5 w-3.5" />
                            <span>Materials Vault</span>
                            <span className={cx(
                                'text-[10px] px-1.5 py-0.2 rounded-full font-bold',
                                (s.materials?.length || 0) > 0 ? 'bg-accent/15 text-accent' : 'text-muted'
                            )}>
                                {s.materials?.length || 0}
                            </span>
                        </button>
                    </div>
                    {tab === 'materials' && (
                        <Button size="xs" variant="primary" icon={Plus} onClick={() => setShowMaterialSheet(true)}>
                            Add
                        </Button>
                    )}
                </div>

                {tab === 'topics' ? (
                    s.total > 0 ? (
                        <>
                            <div className="mt-3 flex items-end justify-between gap-3">
                                <div className="flex items-baseline gap-1.5">
                                    <span className="text-3xl font-extrabold tracking-tight tabular-nums leading-none">{s.progress}</span>
                                    <span className="text-sm font-bold text-subtle">%</span>
                                </div>
                                <div className="text-xs text-subtle text-right">
                                    {s.done} of {s.total} topics
                                    {shaky > 0 && <span className="text-danger font-medium"> · {shaky} shaky</span>}
                                </div>
                            </div>
                            <ProgressBar value={s.progress} color={s.progress >= 100 ? 'var(--ok)' : hex} className="mt-2.5 h-2" />

                            <div className="mt-4 -mx-1.5">
                                <UnitList subject={s} hex={hex} managing={managing}
                                    onUpdateTopic={onUpdateTopic} onDeleteTopic={onDeleteTopic}
                                    onTopicGenerated={onTopicGenerated} />
                            </div>

                            <div className="mt-3 pt-3 border-t border-line flex items-center gap-1.5">
                                <Button size="sm" icon={ClipboardPaste} onClick={onAddTopics}>Add topics</Button>
                                <Button size="sm" variant="ghost" icon={managing ? Check : Pencil} onClick={() => setManaging((m) => !m)}>
                                    {managing ? 'Done' : 'Manage'}
                                </Button>
                            </div>
                        </>
                    ) : (
                        <PasteInvite hex={hex} onClick={onAddTopics} />
                    )
                ) : (
                    <div className="mt-3">
                        <CourseMaterialsList subject={s}
                            onAdd={() => setShowMaterialSheet(true)}
                            onDelete={(m) => onDeleteMaterial?.(s.id, m.id)} />
                    </div>
                )}
            </div>

            <AddMaterialSheet
                open={showMaterialSheet}
                subject={s}
                onClose={() => setShowMaterialSheet(false)}
                onSave={async (data) => {
                    const ok = await onAddMaterial?.(s.id, data);
                    if (ok) setShowMaterialSheet(false);
                }}
            />
        </Card>
    );
}

function PasteInvite({ hex, onClick }) {
    return (
        <button onClick={onClick}
            className="group mt-4 w-full rounded-2xl border-2 border-dashed border-line hover:border-line-strong bg-surface-2/40 hover:bg-surface-2 transition-colors p-5 text-center">
            <div className="mx-auto grid place-items-center h-11 w-11 rounded-2xl transition-transform group-hover:scale-105" style={{ color: hex, background: tint(hex) }}>
                <ClipboardPaste className="h-5 w-5" />
            </div>
            <div className="mt-3 text-sm font-semibold">Paste the syllabus</div>
            <p className="mt-1 text-xs text-subtle leading-relaxed max-w-xs mx-auto">
                Open the course&apos;s <span className="text-muted font-medium">Syllabus</span> → copy → paste here. Units and topics are detected automatically.
            </p>
            <span className="btn btn-primary btn-sm mt-4 pointer-events-none"><Plus className="h-4 w-4" /> Paste syllabus</span>
        </button>
    );
}

function UnitList({ subject: s, hex, managing, onUpdateTopic, onDeleteTopic, onTopicGenerated, compact }) {
    const firstOpen = s.units.find((u) => u.topics.some((t) => !t.done))?.unit ?? s.units[0]?.unit ?? null;
    const [openMap, setOpenMap] = useLocalStorage(`study:units:${s.id}`, {});
    const key = (u) => u ?? '__none__';
    const isOpen = (u) => (key(u) in openMap ? openMap[key(u)] : u === firstOpen);
    const single = s.units.length === 1;

    return (
        <div className="space-y-1">
            {s.units.map((u) => {
                const done = u.topics.filter((t) => t.done).length;
                const open = single || isOpen(u.unit);
                const [tag, title] = unitParts(u.unit);
                const complete = done === u.topics.length;
                return (
                    <div key={key(u.unit)} className={cx('rounded-xl transition-colors', open && !single && 'bg-surface-2/50')}>
                        {!single && (
                            <button onClick={() => setOpenMap((m) => ({ ...m, [key(u.unit)]: !open }))}
                                className="w-full flex items-center gap-2.5 px-2 py-2 rounded-xl text-left hover:bg-surface-2 transition-colors"
                                aria-expanded={open}>
                                <ChevronDown className={cx('h-4 w-4 text-subtle shrink-0 transition-transform', !open && '-rotate-90')} />
                                <span className="min-w-0 flex-1 flex items-baseline gap-2">
                                    {tag && <span className="text-[11px] font-bold uppercase tracking-wide shrink-0" style={{ color: hex }}>{tag}</span>}
                                    {title && <span className="text-[13px] font-medium truncate">{title}</span>}
                                </span>
                                {complete
                                    ? <span className="badge text-ok bg-ok/10 shrink-0"><Check className="h-3 w-3" strokeWidth={3} /> Done</span>
                                    : <span className="text-[11px] text-subtle tabular-nums shrink-0">{done}/{u.topics.length}</span>}
                            </button>
                        )}
                        {open && (
                            <ul className={cx('pb-1', !single && 'pl-1.5')}>
                                {u.topics.map((t) => (
                                    <TopicRow key={t.id} topic={t} managing={managing} compact={compact}
                                        onUpdate={(body) => onUpdateTopic(t, body)} onDelete={() => onDeleteTopic(t)}
                                        onTopicGenerated={onTopicGenerated} />
                                ))}
                            </ul>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

function TopicRow({ topic: t, managing, onUpdate, onDelete, onTopicGenerated }) {
    const today = studiedToday(t.last_studied_at);
    const [openNotes, setOpenNotes] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editText, setEditText] = useState(t.notes || '');
    const [copied, setCopied] = useState(false);
    const toast = useToast();

    const handleToggleNotes = async (e) => {
        e?.stopPropagation?.();
        if (t.notes) {
            setOpenNotes((prev) => !prev);
            return;
        }
        setOpenNotes(true);
        setGenerating(true);
        try {
            const res = await api(`/syllabus/topics/${t.id}/generate`, { method: 'POST' });
            if (res?.data) {
                onTopicGenerated?.(t, res.data);
                setEditText(res.data.notes || '');
                toast(`Generated study notes for "${t.title}"`, 'success');
            }
        } catch (err) {
            toast(err.message || 'Generation failed', 'error');
        } finally {
            setGenerating(false);
        }
    };

    const handleRegen = async (e) => {
        e?.stopPropagation?.();
        setGenerating(true);
        try {
            const res = await api(`/syllabus/topics/${t.id}/generate`, { method: 'POST' });
            if (res?.data) {
                onTopicGenerated?.(t, res.data);
                setEditText(res.data.notes || '');
                toast(`Refreshed notes for "${t.title}"`, 'success');
            }
        } catch (err) {
            toast(err.message || 'Generation failed', 'error');
        } finally {
            setGenerating(false);
        }
    };

    const handleSaveEdit = async () => {
        try {
            const res = await api(`/syllabus/topics/${t.id}/notes`, { method: 'PUT', body: { notes: editText } });
            if (res?.data) {
                onTopicGenerated?.(t, res.data);
                setIsEditing(false);
                toast('Notes saved', 'success');
            }
        } catch (err) {
            toast(err.message || 'Failed to save notes', 'error');
        }
    };

    const handleCopy = () => {
        if (!t.notes) return;
        navigator.clipboard.writeText(t.notes);
        setCopied(true);
        toast('Notes copied to clipboard!', 'info');
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <li className="rounded-lg transition-colors">
            <div className="group flex items-center gap-2 rounded-lg px-2 py-1.5 row-hover">
                <Checkbox checked={t.done} onChange={(v) => onUpdate({ done: v })} label={`Mark ${t.title} ${t.done ? 'not done' : 'done'}`} />
                <span className={cx('min-w-0 flex-1 text-[13.5px] leading-snug break-words', t.done ? 'text-subtle line-through decoration-line-strong' : 'text-fg')}>
                    {t.title}
                </span>
                {managing ? (
                    <button className="btn btn-danger btn-icon btn-sm h-7 w-7 shrink-0" onClick={onDelete} aria-label={`Delete ${t.title}`} title="Delete topic">
                        <Trash2 className="h-3.5 w-3.5" />
                    </button>
                ) : (
                    <div className="flex items-center gap-0.5 shrink-0">
                        {/* Topic AI Generator Symbol */}
                        <button
                            type="button"
                            onClick={handleToggleNotes}
                            disabled={generating}
                            className={cx(
                                'grid place-items-center h-7 w-7 rounded-lg transition-all relative',
                                generating && 'text-accent',
                                t.notes
                                    ? 'text-accent bg-accent/15 hover:bg-accent/25'
                                    : 'text-subtle/80 hover:text-accent hover:bg-surface-2'
                            )}
                            title={t.notes ? (openNotes ? 'Hide AI Notes' : 'View AI Notes (Ready)') : 'Generate AI study notes'}
                            aria-label="Generate AI notes"
                        >
                            {generating ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
                            ) : (
                                <Sparkles className={cx('h-3.5 w-3.5', t.notes && 'fill-accent/40 text-accent')} />
                            )}
                            {t.notes && !generating && (
                                <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-accent ring-1 ring-surface" />
                            )}
                        </button>

                        <ConfidenceDots value={t.confidence} onChange={(c) => onUpdate({ confidence: c })} />
                        <button onClick={() => onUpdate({ studied: !today })}
                            className={cx('grid place-items-center h-7 w-7 rounded-lg transition-colors',
                                today ? 'text-accent bg-accent-soft' : 'text-subtle/70 hover:text-accent hover:bg-surface-2')}
                            aria-pressed={today} aria-label={today ? 'Studied today (tap to undo)' : 'Mark studied today'}
                            title={today ? 'Studied today' : 'Studied today?'}>
                            <Flame className={cx('h-3.5 w-3.5', today && 'fill-current')} />
                        </button>
                    </div>
                )}
            </div>

            {/* Expandable Topic Notes Panel */}
            {openNotes && (
                <div className="mx-2 mb-2 p-3.5 rounded-xl bg-surface border border-line-strong shadow-sm space-y-2.5 animate-rise">
                    <div className="flex items-center justify-between gap-2 border-b border-line pb-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                            <span className="grid place-items-center h-5 w-5 rounded-md bg-accent/15 text-accent shrink-0">
                                <Sparkles className="h-3 w-3" />
                            </span>
                            <span className="text-[12px] font-semibold text-fg tracking-tight truncate">AI Exam Blueprint</span>
                            {t.notes_generated_at && (
                                <span className="text-[10px] text-subtle shrink-0 hidden sm:inline">
                                    · {new Date(t.notes_generated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                            <button
                                type="button"
                                onClick={handleRegen}
                                disabled={generating}
                                className="btn btn-ghost btn-xs text-subtle hover:text-fg gap-1"
                                title="Regenerate notes"
                            >
                                <RefreshCw className={cx('h-3 w-3', generating && 'animate-spin')} />
                                <span className="text-[11px] hidden sm:inline">Regen</span>
                            </button>
                            {t.notes && (
                                <button
                                    type="button"
                                    onClick={handleCopy}
                                    className="btn btn-ghost btn-xs text-subtle hover:text-fg gap-1"
                                    title="Copy Markdown"
                                >
                                    {copied ? <Check className="h-3 w-3 text-ok" /> : <Copy className="h-3 w-3" />}
                                    <span className="text-[11px] hidden sm:inline">{copied ? 'Copied' : 'Copy'}</span>
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={() => {
                                    if (isEditing) handleSaveEdit();
                                    else {
                                        setEditText(t.notes || '');
                                        setIsEditing(true);
                                    }
                                }}
                                className={cx('btn btn-xs gap-1', isEditing ? 'btn-primary' : 'btn-ghost text-subtle hover:text-fg')}
                            >
                                {isEditing ? <Check className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                                <span className="text-[11px]">{isEditing ? 'Save' : 'Edit'}</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => setOpenNotes(false)}
                                className="btn btn-ghost btn-icon btn-xs text-subtle hover:text-fg"
                                title="Collapse"
                            >
                                <ChevronUp className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    </div>

                    {generating && !t.notes ? (
                        <div className="py-6 flex flex-col items-center justify-center text-center gap-2">
                            <Loader2 className="h-5 w-5 animate-spin text-accent" />
                            <p className="text-xs text-subtle">Generating high-yield exam blueprint for <span className="font-semibold text-fg">{t.title}</span>...</p>
                        </div>
                    ) : isEditing ? (
                        <div className="space-y-2">
                            <textarea
                                value={editText}
                                onChange={(e) => setEditText(e.target.value)}
                                rows={8}
                                className="w-full text-xs font-mono p-2.5 rounded-lg bg-surface-2 border border-line focus:border-accent focus:outline-none resize-y"
                                placeholder="Write markdown revision notes..."
                            />
                            <div className="flex justify-end gap-1.5">
                                <Button size="xs" variant="ghost" onClick={() => setIsEditing(false)}>Cancel</Button>
                                <Button size="xs" variant="primary" onClick={handleSaveEdit}>Save Changes</Button>
                            </div>
                        </div>
                    ) : (
                        <div className="text-xs leading-relaxed text-fg max-h-96 overflow-y-auto pr-1">
                            <Markdown>{t.notes}</Markdown>
                        </div>
                    )}
                </div>
            )}
        </li>
    );
}

function ConfidenceDots({ value, onChange }) {
    // Tap cycles shaky → okay → solid → unrated
    const next = value == null ? 1 : value >= 3 ? null : value + 1;
    return (
        <button onClick={() => onChange(next)}
            className="flex items-center gap-[3px] h-7 px-1.5 rounded-lg hover:bg-surface-2 transition-colors"
            title={value ? `Confidence: ${CONF_LABEL[value]} (tap to change)` : 'Rate your confidence'}
            aria-label={`Confidence: ${value ? CONF_LABEL[value] : 'not rated'}. Tap to change.`}>
            {[1, 2, 3].map((i) => (
                <span key={i} className={cx('h-[7px] w-[7px] rounded-full transition-colors',
                    value && i <= value ? CONF_BG[value] : 'bg-line-strong')} />
            ))}
        </button>
    );
}

// ---------------- Course Materials List ----------------
function CourseMaterialsList({ subject: s, onAdd, onDelete }) {
    const [categoryFilter, setCategoryFilter] = useState('all');
    const [expandedMat, setExpandedMat] = useState(null);
    const materials = s.materials || [];
    const filtered = materials.filter((m) => categoryFilter === 'all' || m.category === categoryFilter);

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1 overflow-x-auto py-1 max-w-full text-xs">
                    <button
                        type="button"
                        onClick={() => setCategoryFilter('all')}
                        className={cx(
                            'px-2 py-1 rounded-lg font-medium transition-colors shrink-0',
                            categoryFilter === 'all' ? 'bg-surface-2 text-fg font-semibold border border-line' : 'text-subtle hover:text-fg'
                        )}
                    >
                        All ({materials.length})
                    </button>
                    {MATERIAL_CATEGORIES.map((cat) => {
                        const count = materials.filter((m) => m.category === cat.value).length;
                        if (count === 0 && materials.length > 0) return null;
                        return (
                            <button
                                key={cat.value}
                                type="button"
                                onClick={() => setCategoryFilter(cat.value)}
                                className={cx(
                                    'px-2 py-1 rounded-lg font-medium transition-colors flex items-center gap-1 shrink-0',
                                    categoryFilter === cat.value ? 'bg-surface-2 text-fg font-semibold border border-line' : 'text-subtle hover:text-fg'
                                )}
                            >
                                <cat.icon className="h-3 w-3" />
                                <span>{cat.label}</span>
                                {count > 0 && <span className="text-[10px] text-muted">({count})</span>}
                            </button>
                        );
                    })}
                </div>
                <Button size="xs" variant="primary" icon={Plus} onClick={onAdd} className="shrink-0">
                    Add Material
                </Button>
            </div>

            {filtered.length === 0 ? (
                <div className="py-8 text-center rounded-2xl border-2 border-dashed border-line bg-surface-2/30 p-4">
                    <FolderArchive className="h-8 w-8 mx-auto text-subtle mb-2" />
                    <p className="text-sm font-semibold">No materials {categoryFilter !== 'all' ? 'in this category' : 'added yet'}</p>
                    <p className="text-xs text-subtle mt-1 max-w-xs mx-auto">
                        Insert lecture notes, cheatsheets, Drive links, and exam papers to keep this course organized for future reference.
                    </p>
                    <Button size="xs" variant="primary" icon={Plus} onClick={onAdd} className="mt-3">
                        Insert Material
                    </Button>
                </div>
            ) : (
                <ul className="space-y-2">
                    {filtered.map((m) => {
                        const cat = MATERIAL_CATEGORIES.find((c) => c.value === m.category) || MATERIAL_CATEGORIES[0];
                        const isExp = expandedMat === m.id;
                        return (
                            <li key={m.id} className="p-3 rounded-xl bg-surface-2/60 border border-line hover:border-line-strong transition-all">
                                <div className="flex items-start justify-between gap-2">
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className={cx('badge text-[10px] px-1.5 py-0.5 border', cat.color)}>
                                                <cat.icon className="h-2.5 w-2.5 inline mr-1" />
                                                {cat.label}
                                            </span>
                                            {m.created_at && (
                                                <span className="text-[11px] text-subtle">
                                                    {new Date(m.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                                                </span>
                                            )}
                                        </div>
                                        <h4 className="text-[13.5px] font-semibold text-fg mt-1 leading-snug break-words">
                                            {m.title}
                                        </h4>
                                    </div>
                                    <div className="flex items-center gap-1 shrink-0">
                                        {m.url && (
                                            <a
                                                href={m.url}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="btn btn-ghost btn-xs text-accent gap-1 hover:bg-accent/10"
                                                title="Open resource"
                                            >
                                                <ExternalLink className="h-3 w-3" />
                                                <span className="hidden sm:inline text-[11px]">Open</span>
                                            </a>
                                        )}
                                        {m.content && (
                                            <button
                                                type="button"
                                                onClick={() => setExpandedMat(isExp ? null : m.id)}
                                                className="btn btn-ghost btn-icon btn-xs text-subtle hover:text-fg"
                                                title={isExp ? 'Collapse notes' : 'View notes'}
                                            >
                                                <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', isExp && 'rotate-180')} />
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            onClick={() => onDelete(m)}
                                            className="btn btn-ghost btn-icon btn-xs text-subtle hover:text-danger"
                                            title="Delete material"
                                        >
                                            <Trash2 className="h-3 w-3" />
                                        </button>
                                    </div>
                                </div>
                                {m.content && isExp && (
                                    <div className="mt-2.5 pt-2.5 border-t border-line text-xs leading-relaxed text-fg max-h-64 overflow-y-auto pr-1 animate-rise">
                                        <Markdown>{m.content}</Markdown>
                                    </div>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}

// ---------------- Add Material Sheet ----------------
function AddMaterialSheet({ open, subject, onClose, onSave }) {
    const [title, setTitle] = useState('');
    const [category, setCategory] = useState('lecture_notes');
    const [url, setUrl] = useState('');
    const [content, setContent] = useState('');
    const [busy, setBusy] = useState(false);
    const toast = useToast();

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!title.trim()) {
            toast('Please enter a title for the material', 'error');
            return;
        }
        setBusy(true);
        try {
            await onSave({ title: title.trim(), category, url: url.trim(), content: content.trim() });
            setTitle('');
            setUrl('');
            setContent('');
            setCategory('lecture_notes');
        } finally {
            setBusy(false);
        }
    };

    if (!open) return null;

    return (
        <Sheet open={open} onClose={onClose}>
            <form onSubmit={handleSubmit} className="card-pad space-y-4">
                <div className="flex items-start justify-between gap-3 border-b border-line pb-3">
                    <div className="min-w-0">
                        <div className="eyebrow">Insert Material</div>
                        <h2 className="text-lg font-bold tracking-tight leading-snug mt-0.5">{subject?.name}</h2>
                    </div>
                </div>

                <div>
                    <label className="label" htmlFor="mat-title">Title *</label>
                    <input
                        id="mat-title"
                        className="input"
                        required
                        maxLength={200}
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="e.g. Unit 3 Complete Slide Deck or Midterm Solved Paper"
                        autoFocus
                    />
                </div>

                <div>
                    <label className="label">Category</label>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        {MATERIAL_CATEGORIES.map((cat) => (
                            <button
                                key={cat.value}
                                type="button"
                                onClick={() => setCategory(cat.value)}
                                className={cx(
                                    'p-2 rounded-xl border text-left flex items-center gap-2 transition-all text-xs font-medium',
                                    category === cat.value
                                        ? 'border-accent bg-accent/10 text-fg shadow-xs'
                                        : 'border-line hover:border-line-strong bg-surface text-subtle hover:text-fg'
                                )}
                            >
                                <cat.icon className="h-3.5 w-3.5 shrink-0" />
                                <span className="truncate">{cat.label}</span>
                            </button>
                        ))}
                    </div>
                </div>

                <div>
                    <label className="label" htmlFor="mat-url">Resource URL <span className="text-subtle font-normal">(optional)</span></label>
                    <input
                        id="mat-url"
                        className="input font-mono text-xs"
                        type="url"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder="https://drive.google.com/... or https://github.com/..."
                    />
                </div>

                <div>
                    <label className="label" htmlFor="mat-content">Notes &amp; Content <span className="text-subtle font-normal">(optional markdown)</span></label>
                    <textarea
                        id="mat-content"
                        className="input h-auto min-h-[7rem] py-2.5 font-mono text-xs leading-relaxed resize-y"
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        placeholder="Key formulas, lecture summaries, key exam topics, or quick takeaways..."
                    />
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-line">
                    <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button type="submit" variant="primary" icon={Plus} loading={busy} disabled={!title.trim()}>
                        Save Material
                    </Button>
                </div>
            </form>
        </Sheet>
    );
}

// ---------------- Labs & other ----------------
function OtherCourses({
    courses, onUpdateTopic, onDeleteTopic, onTopicGenerated,
    _onAddMaterial, _onDeleteMaterial, onEdit, onAddTopics,
}) {
    const [open, setOpen] = useLocalStorage('study:others-open', false);
    const [expanded, setExpanded] = useState(null);
    const labs = courses.filter((c) => c.kind === 'lab').length;

    return (
        <Card className="overflow-hidden">
            <button onClick={() => setOpen(!open)} className="w-full card-pad flex items-center gap-3 text-left hover:bg-surface-2/50 transition-colors" aria-expanded={open}>
                <div className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line text-muted shrink-0">
                    <FlaskConical className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                    <h2 className="text-[15px] font-semibold tracking-tight">Labs &amp; other courses</h2>
                    <p className="text-xs text-subtle truncate">{labs} lab{labs === 1 ? '' : 's'} · {courses.length - labs} other · no end-sem written exam</p>
                </div>
                <ChevronDown className={cx('h-4 w-4 text-subtle shrink-0 transition-transform', !open && '-rotate-90')} />
            </button>
            {open && (
                <ul className="border-t border-line divide-y divide-line animate-rise">
                    {courses.map((c) => {
                        const hex = hexOf(c);
                        const isExpanded = expanded === c.id && c.total > 0;
                        return (
                            <li key={c.id}>
                                <div className="flex items-center gap-3 px-4 sm:px-5 py-3">
                                    <span className="h-8 w-1 rounded-full shrink-0" style={{ background: hex }} />
                                    <button className="min-w-0 flex-1 text-left" onClick={() => c.total ? setExpanded(isExpanded ? null : c.id) : onEdit(c)}>
                                        <div className="flex items-center gap-2 min-w-0">
                                            {c.code && <span className="font-mono text-[11px] font-semibold text-subtle shrink-0">{c.code}</span>}
                                            <span className="text-[13.5px] font-medium truncate">{c.name}</span>
                                        </div>
                                        <div className="flex items-center gap-2 mt-0.5 min-w-0">
                                            <span className="text-xs text-subtle truncate">{c.faculty || (c.kind === 'lab' ? 'Lab' : 'Course')}</span>
                                            {c.total > 0 && (
                                                <span className="flex items-center gap-1.5 shrink-0 ml-auto">
                                                    <ProgressBar value={c.progress} color={hex} className="w-14 sm:w-20 h-1" />
                                                    <span className="text-[11px] text-subtle tabular-nums w-8 text-right">{c.progress}%</span>
                                                </span>
                                            )}
                                        </div>
                                    </button>
                                    <div className="flex items-center shrink-0">
                                        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => onAddTopics(c)} aria-label={`Add topics to ${c.name}`} title="Add topics">
                                            <ClipboardPaste className="h-3.5 w-3.5" />
                                        </button>
                                        <button className="btn btn-ghost btn-icon btn-sm" onClick={() => onEdit(c)} aria-label={`Edit ${c.name}`} title="Edit">
                                            <Pencil className="h-3.5 w-3.5" />
                                        </button>
                                        {c.total > 0 && (
                                            <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setExpanded(isExpanded ? null : c.id)} aria-label="Show topics" aria-expanded={isExpanded}>
                                                <ChevronDown className={cx('h-4 w-4 transition-transform', !isExpanded && '-rotate-90')} />
                                            </button>
                                        )}
                                    </div>
                                </div>
                                {isExpanded && (
                                    <div className="px-2.5 sm:px-4 pb-3 animate-rise">
                                        <UnitList subject={c} hex={hex}
                                            onUpdateTopic={onUpdateTopic} onDeleteTopic={onDeleteTopic}
                                            onTopicGenerated={onTopicGenerated} compact />
                                    </div>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
        </Card>
    );
}

// ---------------- Sheets ----------------
const EMPTY_SUBJECT = { name: '', code: '', faculty: '', kind: 'theory', exam_date: '', color: 'violet' };

// The forms mount fresh every time a sheet opens (Sheet renders nothing while closed),
// so their state is initialised straight from props.
function SubjectSheet({ open, subject, onClose, onSaved, onDeleted }) {
    return (
        <Sheet open={open} onClose={onClose}>
            <SubjectForm key={subject?.id ?? 'new'} subject={subject} onClose={onClose} onSaved={onSaved} onDeleted={onDeleted} />
        </Sheet>
    );
}

function SubjectForm({ subject, onClose, onSaved, onDeleted }) {
    const [form, setForm] = useState(() => (subject ? {
        name: subject.name, code: subject.code || '', faculty: subject.faculty || '', kind: subject.kind || 'theory',
        exam_date: subject.exam_date || '', color: subject.color || 'violet',
    } : EMPTY_SUBJECT));
    const [busy, setBusy] = useState(false);
    const toast = useToast();

    const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e?.target ? e.target.value : e }));

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const r = subject
                ? await api(`/syllabus/subjects/${subject.id}`, { method: 'PUT', body: form })
                : await api('/syllabus/subjects', { method: 'POST', body: form });
            toast(subject ? 'Subject updated' : `Added ${r.data.name}`);
            onSaved(r.data, !subject);
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setBusy(false);
        }
    };

    const remove = async () => {
        if (!window.confirm(`Delete ${subject.name} and all ${subject.total} of its topics? This can't be undone.`)) return;
        setBusy(true);
        try {
            await api(`/syllabus/subjects/${subject.id}`, { method: 'DELETE' });
            toast('Subject deleted');
            onDeleted();
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setBusy(false);
        }
    };

    return (
        <form onSubmit={submit} className="p-5 sm:p-6 space-y-4">
                <div className="pr-10">
                    <div className="eyebrow">{subject ? 'Edit subject' : 'New subject'}</div>
                    <h2 className="text-xl font-bold tracking-tight mt-1 truncate">{form.name || 'Untitled subject'}</h2>
                </div>
                <div>
                    <label className="label" htmlFor="subj-name">Name</label>
                    <input id="subj-name" className="input" required maxLength={120} value={form.name} onChange={set('name')} placeholder="Next Generation Networking Systems" autoFocus={!subject} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-[8rem_minmax(0,1fr)] gap-3">
                    <div>
                        <label className="label" htmlFor="subj-code">Code</label>
                        <input id="subj-code" className="input font-mono" maxLength={30} value={form.code} onChange={set('code')} placeholder="CS6319" />
                    </div>
                    <div>
                        <label className="label" htmlFor="subj-fac">Faculty</label>
                        <input id="subj-fac" className="input" maxLength={120} value={form.faculty} onChange={set('faculty')} placeholder="Prof. name" />
                    </div>
                </div>
                <div>
                    <span className="label">Type</span>
                    <Segmented options={KINDS} value={form.kind} onChange={set('kind')} />
                    <p className="text-xs text-subtle mt-1.5">Theory subjects drive the countdown, reminders and “study next”.</p>
                </div>
                <div>
                    <label className="label" htmlFor="subj-date">Exam date</label>
                    <div className="flex gap-2">
                        <input id="subj-date" type="date" className="input" value={form.exam_date} onChange={set('exam_date')} />
                        {form.exam_date && <Button type="button" variant="ghost" className="h-10" onClick={() => set('exam_date')('')}>Clear</Button>}
                    </div>
                </div>
                <div>
                    <span className="label">Colour</span>
                    <div className="flex flex-wrap gap-2.5">
                        {COLOR_KEYS.map((k) => (
                            <button key={k} type="button" onClick={() => set('color')(k)} aria-label={k} aria-pressed={form.color === k}
                                className={cx('grid place-items-center h-8 w-8 rounded-full transition-transform hover:scale-110',
                                    form.color === k && 'ring-2 ring-offset-2 ring-offset-surface')}
                                style={{ background: COLORS[k], '--tw-ring-color': COLORS[k] }}>
                                {form.color === k && <Check className="h-4 w-4 text-white" strokeWidth={3} />}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="flex items-center gap-2 pt-2">
                    {subject && <Button type="button" variant="danger" icon={Trash2} onClick={remove} disabled={busy}>Delete</Button>}
                    <div className="flex-1" />
                    <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button type="submit" variant="primary" loading={busy}>{subject ? 'Save' : 'Add subject'}</Button>
                </div>
        </form>
    );
}

const PASTE_EXAMPLE = `Unit 1: Introduction
Software testing principles
Errors, faults and failures
UNIT-II Black box testing
1. Boundary value analysis
2. Equivalence class partitioning`;

function AddTopicsSheet({ open, subject, onClose, onAdded }) {
    return (
        <Sheet open={open && !!subject} onClose={onClose} wide>
            {subject && <AddTopicsForm key={subject.id} subject={subject} onClose={onClose} onAdded={onAdded} />}
        </Sheet>
    );
}

function AddTopicsForm({ subject, onClose, onAdded }) {
    const [mode, setMode] = useLocalStorage('study:add-mode', 'paste');
    const [text, setText] = useState('');
    const [title, setTitle] = useState('');
    const [unit, setUnit] = useState(() => subject.units.at(-1)?.unit || '');
    const [busy, setBusy] = useState(false);
    const toast = useToast();

    const hex = hexOf(subject);
    const lines = text.split('\n').filter((l) => l.trim()).length;

    const submit = async (e) => {
        e.preventDefault();
        const body = mode === 'paste' ? { text } : { title, unit: unit || undefined };
        setBusy(true);
        try {
            const r = await api(`/syllabus/subjects/${subject.id}/topics`, { method: 'POST', body });
            toast(`Added ${r.added} topic${r.added === 1 ? '' : 's'} to ${subject.short || subject.name}`);
            if (mode === 'single') setTitle('');
            onAdded(r.data, mode === 'single');
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            setBusy(false);
        }
    };

    return (
            <form onSubmit={submit} className="p-5 sm:p-6 space-y-4">
                <div className="flex items-start gap-3 pr-10">
                    <div className="grid place-items-center h-10 w-10 rounded-xl shrink-0" style={{ color: hex, background: tint(hex) }}>
                        <ClipboardPaste className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                        <div className="eyebrow">Add topics</div>
                        <h2 className="text-lg font-bold tracking-tight leading-snug mt-0.5">{subject.name}</h2>
                    </div>
                </div>

                <Segmented value={mode} onChange={setMode}
                    options={[{ value: 'paste', label: 'Paste syllabus' }, { value: 'single', label: 'Single topic' }]} />

                {mode === 'paste' ? (
                    <>
                        <div className="rounded-xl border border-line bg-surface-2/60 p-3.5 text-[13px] text-muted space-y-1.5">
                            <p className="flex items-start gap-2"><Sparkles className="h-4 w-4 text-accent shrink-0 mt-px" />
                                <span>Open the course&apos;s <span className="text-fg font-medium">Syllabus</span>, copy it, paste it below.</span></p>
                            <ul className="pl-6 space-y-1 text-xs text-subtle list-disc">
                                <li>Lines like <code className="font-mono text-fg">Unit 1: Title</code>, <code className="font-mono text-fg">UNIT-II …</code> or <code className="font-mono text-fg">Module 3 - …</code> start a unit.</li>
                                <li>Every other line is a topic. Bullets and numbering are removed; comma lists become separate topics.</li>
                                <li>Everything after “Text books” / “References” is ignored.</li>
                            </ul>
                        </div>
                        <div>
                            <textarea className="input h-auto min-h-[16rem] sm:min-h-[20rem] py-3 font-mono text-[13px] leading-relaxed resize-y"
                                value={text} onChange={(e) => setText(e.target.value)} placeholder={PASTE_EXAMPLE}
                                spellCheck={false} autoFocus aria-label="Syllabus text" />
                            <div className="mt-1.5 text-xs text-subtle">{lines ? `${lines} non-empty line${lines === 1 ? '' : 's'}` : 'Tip: long pastes are fine. Up to 400 topics at once.'}</div>
                        </div>
                    </>
                ) : (
                    <div className="grid gap-3">
                        <div>
                            <label className="label" htmlFor="topic-title">Topic</label>
                            <input id="topic-title" className="input" required maxLength={300} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Mutation testing" autoFocus />
                        </div>
                        <div>
                            <label className="label" htmlFor="topic-unit">Unit <span className="text-subtle font-normal">(optional)</span></label>
                            <input id="topic-unit" className="input" maxLength={120} list="unit-options" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="Unit 3 · White box testing" />
                            <datalist id="unit-options">
                                {subject.units.filter((u) => u.unit).map((u) => <option key={u.unit} value={u.unit} />)}
                            </datalist>
                        </div>
                    </div>
                )}

                <div className="flex justify-end gap-2 pt-1">
                    <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button type="submit" variant="primary" icon={Plus} loading={busy} disabled={mode === 'paste' ? !text.trim() : !title.trim()}>
                        {mode === 'paste' ? 'Add topics' : 'Add topic'}
                    </Button>
                </div>
            </form>
    );
}
