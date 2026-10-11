import { useEffect, useRef, useState } from 'react';
import { BookOpen, CircleAlert, Layers, ListPlus, RotateCcw, Sparkles, Square } from 'lucide-react';
import { Button, Checkbox, Empty, Sheet, Skeleton, Spinner, cx, useToast } from './ui';
import { api } from '../lib/api';
import { renderPagesForUpload } from '../lib/pdf';

const MAX_TEXT = 20000;
const PAYLOAD_LIMIT = 3_400_000;
const MARKS = {
    high: { label: 'High marks', cls: 'text-danger bg-danger/10' },
    medium: { label: 'Medium', cls: 'text-medium bg-medium/10' },
    low: { label: 'Low', cls: 'text-muted bg-surface-2' },
};

const isNotFound = (e) => /\(404\)|not found/i.test(e?.message || '');
// The syllabus parser splits titles on commas / semicolons, so keep each topic a single item.
const safeTitle = (t) => t.replace(/\s*[,;]\s*/g, ' / ').replace(/\s+/g, ' ').trim();

function guessSubject(subjects, docName) {
    const name = (docName || '').toLowerCase();
    return subjects.find((s) => [s.short, s.code, s.name].some((k) => k && name.includes(String(k).toLowerCase())))
        || subjects[0];
}

function toDraft(data) {
    return {
        unit: data?.unit || '',
        topics: (data?.topics || []).map((t, i) => ({
            key: i,
            title: t.title,
            summary: t.summary,
            marks: t.likely_marks,
            on: true,
            cards: (t.flashcards || []).map((c, j) => ({ key: j, q: c.q, a: c.a, on: true })),
        })),
    };
}

export default function ExtractSheet({ open, onClose, getPdf, doc, section, label, getText }) {
    return (
        <Sheet open={open} onClose={onClose} wide>
            {open && <ExtractBody key={`${doc?.name}:${label}`} getPdf={getPdf} doc={doc} section={section} label={label} getText={getText} />}
        </Sheet>
    );
}

function ExtractBody({ getPdf, doc, section, label, getText }) {
    const push = useToast();
    const [subjects, setSubjects] = useState(null); // null while loading
    const [subjectId, setSubjectId] = useState('');
    const [run, setRun] = useState({ status: 'idle', progress: '', error: null }); // idle | working | done | error
    const [draft, setDraft] = useState(null);
    const [saving, setSaving] = useState(null); // 'topics' | 'cards'
    const [saved, setSaved] = useState({ topics: false, cards: false });
    const ctrlRef = useRef(null);

    useEffect(() => {
        const ctrl = new AbortController();
        api('/syllabus', { signal: ctrl.signal })
            .then((res) => {
                const list = (res?.data || []).filter((s) => (s.kind || 'theory') === 'theory');
                setSubjects(list);
                setSubjectId(String(guessSubject(list, doc?.name)?.id ?? ''));
            })
            .catch((e) => { if (e?.name !== 'AbortError') { setSubjects([]); push(e.message || 'Could not load subjects', 'error'); } });
        return () => { ctrl.abort(); ctrlRef.current?.abort(); };
    }, [doc?.name, push]);

    const subject = subjects?.find((s) => String(s.id) === subjectId);
    const count = section.to - section.from + 1;

    const extract = async () => {
        const pdf = getPdf();
        if (!pdf) { push('Open the PDF again to extract topics.', 'error'); return; }
        ctrlRef.current?.abort();
        const ctrl = new AbortController();
        ctrlRef.current = ctrl;
        setRun({ status: 'working', progress: 'Reading text…', error: null });
        setSaved({ topics: false, cards: false });
        try {
            const text = (await getText()).slice(0, MAX_TEXT);
            let budget = PAYLOAD_LIMIT - JSON.stringify(text).length - 4000;
            let res;
            for (let attempt = 0; ; attempt++) {
                const images = await renderPagesForUpload(pdf, section.from, section.to, {
                    budget: Math.max(budget, 400_000),
                    signal: ctrl.signal,
                    onProgress: ({ done, pass }) => setRun((r) => ({
                        ...r, progress: `${pass ? 'Compressing' : 'Rendering'} pages ${Math.min(done + 1, count)}/${count}…`,
                    })),
                });
                setRun((r) => ({ ...r, progress: 'Finding topics and writing flashcards…' }));
                try {
                    res = await api('/pdf-extract/topics', {
                        method: 'POST',
                        signal: ctrl.signal,
                        body: { images: images.slice(0, 12), text, subject_name: subject?.name || '', label },
                    });
                    break;
                } catch (e) {
                    if (attempt === 0 && /\(413\)|too large/i.test(e?.message || '')) { budget = Math.floor(budget / 2); continue; }
                    throw e;
                }
            }
            const next = toDraft(res?.data);
            setDraft(next);
            setRun({ status: 'done', progress: '', error: null });
            if (!next.topics.length) push('No study topics found on these pages.', 'info');
        } catch (e) {
            if (e?.name === 'AbortError' || ctrl.signal.aborted) { setRun({ status: 'idle', progress: '', error: null }); return; }
            setRun({ status: 'error', progress: '', error: e?.message || 'Something went wrong' });
        } finally {
            if (ctrlRef.current === ctrl) ctrlRef.current = null;
        }
    };

    const editTopic = (key, obj) => setDraft((d) => ({ ...d, topics: d.topics.map((t) => (t.key === key ? { ...t, ...obj } : t)) }));
    const editCard = (tk, ck, obj) => setDraft((d) => ({
        ...d,
        topics: d.topics.map((t) => (t.key === tk ? { ...t, cards: t.cards.map((c) => (c.key === ck ? { ...c, ...obj } : c)) } : t)),
    }));

    const chosenTopics = draft ? draft.topics.filter((t) => t.on && t.title.trim()) : [];
    const chosenCards = draft ? draft.topics.flatMap((t) => t.cards.filter((c) => c.on && c.q.trim() && c.a.trim())) : [];

    const addTopics = async () => {
        if (!subject || !chosenTopics.length) return;
        setSaving('topics');
        try {
            const res = await api(`/syllabus/subjects/${subject.id}/topics`, {
                method: 'POST',
                body: {
                    unit: draft.unit.trim() || `Pages ${label}`,
                    text: chosenTopics.map((t) => `- ${safeTitle(t.title)}`).join('\n'),
                },
            });
            setSaved((s) => ({ ...s, topics: true }));
            push(`Added ${res?.added ?? chosenTopics.length} topics to ${subject.short || subject.name}`, 'success');
        } catch (e) {
            push(e.message || 'Could not add topics', 'error');
        } finally {
            setSaving(null);
        }
    };

    const createCards = async () => {
        if (!chosenCards.length) return;
        setSaving('cards');
        let made = 0;
        let failed = 0;
        try {
            for (const c of chosenCards) {
                try {
                    await api('/cards', {
                        method: 'POST',
                        body: { subject: subject?.short || subject?.name || 'PDF', question: c.q.trim(), answer: c.a.trim(), tags: 'pdf', difficulty: 2 },
                    });
                    made++;
                } catch (e) {
                    if (isNotFound(e)) {
                        push('Flashcards aren\'t available on this server yet. Topics still work.', 'info');
                        return;
                    }
                    failed++;
                }
            }
            if (made) setSaved((s) => ({ ...s, cards: true }));
            push(failed ? `Created ${made} flashcards, ${failed} failed` : `Created ${made} flashcards`, failed ? 'error' : 'success');
        } finally {
            setSaving(null);
        }
    };

    const working = run.status === 'working';

    return (
        <div className="p-5 sm:p-6 space-y-5">
            <header className="pr-10">
                <p className="eyebrow">Pages {label}</p>
                <h2 className="text-lg font-semibold tracking-tight mt-0.5">Extract topics &amp; cards</h2>
                <p className="text-sm text-muted mt-1">Pull the exam topics from these pages into your syllabus, with flashcards to revise them.</p>
            </header>

            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                <div className="min-w-0">
                    <label className="label" htmlFor="extract-subject">Subject</label>
                    {subjects === null ? (
                        <Skeleton className="h-10 w-full" />
                    ) : (
                        <select
                            id="extract-subject"
                            className="input"
                            value={subjectId}
                            disabled={working || !subjects.length}
                            onChange={(e) => setSubjectId(e.target.value)}
                        >
                            {!subjects.length && <option value="">No theory subjects</option>}
                            {subjects.map((s) => <option key={s.id} value={String(s.id)}>{s.code ? `${s.code} · ` : ''}{s.name}</option>)}
                        </select>
                    )}
                </div>
                {working ? (
                    <Button variant="secondary" icon={Square} onClick={() => ctrlRef.current?.abort()}>Stop</Button>
                ) : (
                    <Button variant={draft ? 'ghost' : 'primary'} icon={draft ? RotateCcw : Sparkles} onClick={extract} disabled={!subject}>
                        {draft ? 'Extract again' : 'Extract'}
                    </Button>
                )}
            </div>

            {working && (
                <div className="space-y-3">
                    <p className="flex items-center gap-2 text-sm text-muted">
                        <Spinner className="h-4 w-4 text-accent" />
                        <span className="tabular-nums">{run.progress}</span>
                    </p>
                    {[0, 1, 2].map((k) => <Skeleton key={k} className="h-16 w-full" />)}
                </div>
            )}

            {run.status === 'error' && (
                <div className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-3 text-sm">
                    <CircleAlert className="h-4 w-4 text-danger mt-0.5 shrink-0" />
                    <div className="min-w-0">
                        <p className="font-medium text-danger">Couldn't extract topics</p>
                        <p className="text-muted mt-0.5 break-words">{run.error}</p>
                    </div>
                </div>
            )}

            {!working && draft && !draft.topics.length && (
                <Empty icon={BookOpen} title="No topics found">These pages look like title or admin slides. Try another section.</Empty>
            )}

            {!working && draft && draft.topics.length > 0 && (
                <>
                    <div>
                        <label className="label" htmlFor="extract-unit">Unit</label>
                        <input
                            id="extract-unit"
                            className="input"
                            value={draft.unit}
                            maxLength={120}
                            onChange={(e) => setDraft((d) => ({ ...d, unit: e.target.value }))}
                            placeholder={`Pages ${label}`}
                        />
                    </div>

                    <ul className="space-y-2.5">
                        {draft.topics.map((t) => {
                            const m = MARKS[t.marks] || MARKS.medium;
                            return (
                                <li key={t.key} className={cx('rounded-xl border border-line bg-surface-2/60 p-3 transition-opacity', !t.on && 'opacity-60')}>
                                    <div className="flex items-start gap-2.5">
                                        <Checkbox className="mt-2.5" checked={t.on} onChange={(v) => editTopic(t.key, { on: v })} label={`Include ${t.title}`} />
                                        <div className="min-w-0 flex-1 space-y-1.5">
                                            <div className="flex items-center gap-2">
                                                <input
                                                    className="input flex-1 min-w-0 font-medium"
                                                    value={t.title}
                                                    maxLength={200}
                                                    aria-label="Topic title"
                                                    onChange={(e) => editTopic(t.key, { title: e.target.value })}
                                                />
                                                <span className={cx('badge shrink-0', m.cls)}>{m.label}</span>
                                            </div>
                                            {t.summary && <p className="text-[13px] text-muted leading-snug break-words">{t.summary}</p>}
                                            {t.cards.length > 0 && (
                                                <div className="space-y-2 pt-1">
                                                    {t.cards.map((c) => (
                                                        <div key={c.key} className={cx('flex items-start gap-2 rounded-lg border border-line bg-surface p-2', !c.on && 'opacity-60')}>
                                                            <Checkbox className="mt-1.5" checked={c.on} onChange={(v) => editCard(t.key, c.key, { on: v })} label="Include flashcard" />
                                                            <div className="min-w-0 flex-1 space-y-1">
                                                                <textarea
                                                                    className="input min-h-0 h-auto py-1.5 text-[13px] font-medium resize-y"
                                                                    rows={1}
                                                                    value={c.q}
                                                                    aria-label="Question"
                                                                    onChange={(e) => editCard(t.key, c.key, { q: e.target.value })}
                                                                />
                                                                <textarea
                                                                    className="input min-h-0 h-auto py-1.5 text-[13px] text-muted resize-y"
                                                                    rows={2}
                                                                    value={c.a}
                                                                    aria-label="Answer"
                                                                    onChange={(e) => editCard(t.key, c.key, { a: e.target.value })}
                                                                />
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </li>
                            );
                        })}
                    </ul>

                    <div className="sticky bottom-0 -mx-5 sm:-mx-6 px-5 sm:px-6 py-3 bg-surface border-t border-line flex flex-wrap gap-2">
                        <Button
                            variant="primary"
                            icon={ListPlus}
                            loading={saving === 'topics'}
                            disabled={!chosenTopics.length || !!saving || saved.topics}
                            onClick={addTopics}
                        >
                            {saved.topics ? 'Topics added' : `Add ${chosenTopics.length} topic${chosenTopics.length === 1 ? '' : 's'}`}
                        </Button>
                        <Button
                            variant="secondary"
                            icon={Layers}
                            loading={saving === 'cards'}
                            disabled={!chosenCards.length || !!saving || saved.cards}
                            onClick={createCards}
                        >
                            {saved.cards ? 'Flashcards created' : `Create ${chosenCards.length} flashcard${chosenCards.length === 1 ? '' : 's'}`}
                        </Button>
                    </div>
                </>
            )}

            {run.status === 'idle' && !draft && (
                <p className="text-sm text-subtle">
                    {subject ? <>Topics will be added to <span className="text-fg font-medium">{subject.name}</span>. You can edit and untick anything before saving.</> : 'Choose a subject to start.'}
                </p>
            )}
        </div>
    );
}
