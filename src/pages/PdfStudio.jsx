import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    BookOpen, Check, ChevronDown, CircleAlert, Clock, Copy, FileText, Info, ListChecks,
    MessageSquareText, Play, RotateCcw, Sparkles, Square, Upload, X,
} from 'lucide-react';
import { Button, Card, ProgressBar, Segmented, Skeleton, Spinner, cx, useToast } from '../components/ui';
import Markdown from '../components/Markdown';
import { api, streamSSE } from '../lib/api';
import { timeAgo, useLocalStorage } from '../lib/hooks';
import { extractText, openPdf, renderPagesForUpload } from '../lib/pdf';

const BASE = import.meta.env.BASE_URL || '/';
const SAMPLES = [
    { name: 'Software Testing — Mid-sem notes', url: `${BASE}samples/software-testing-midsem.pdf`, hint: 'Mid-sem notes · ~20 MB' },
    { name: 'NGNS notes', url: `${BASE}samples/ngns.pdf`, hint: 'Lecture notes · ~4 MB' },
];
const MAX_RECENT = 8;
const MAX_TEXT = 20000;
const PAYLOAD_LIMIT = 3_400_000;

const pageLabel = (s) => (s.from === s.to ? `${s.from}` : `${s.from}–${s.to}`);
const cacheKeyFor = (doc, chunk) => `pdfstudio:${doc.name}:${doc.size}:${chunk}`;

function readCache(key) {
    try { return JSON.parse(localStorage.getItem(key)) || {}; } catch { return {}; }
}
function writeCache(key, index, text) {
    try {
        const data = readCache(key);
        data[index] = text;
        localStorage.setItem(key, JSON.stringify(data));
        return true;
    } catch { return false; }
}

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
        document.body.appendChild(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand('copy'); } catch { /* unsupported */ }
        ta.remove();
        return ok;
    }
}

const formatSize = (bytes) => (typeof bytes === 'number'
    ? bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1e3))} KB`
    : 'Sample');

const isPdf = (file) => file && (file.type === 'application/pdf' || /\.pdf$/i.test(file.name));

export default function PdfStudio() {
    const push = useToast();
    const [recent, setRecent] = useLocalStorage('pdfstudio:recent', []);
    const [chunkPref, setChunk] = useLocalStorage('pdfstudio:chunk', 10);
    const chunk = chunkPref === 5 ? 5 : 10;
    const [focus, setFocus] = useLocalStorage('pdfstudio:focus', '');

    const [doc, setDoc] = useState(null); // { name, size, pages, kind, url }
    const [opening, setOpening] = useState(null); // { name, progress }
    const [results, setResults] = useState({});
    const [expanded, setExpanded] = useState({ 0: true });
    const [runAll, setRunAll] = useState(null); // { current } while "Explain all" runs

    const pdfRef = useRef(null);
    const taskRef = useRef(null);
    const genRef = useRef(0);
    const controllers = useRef(new Map());
    const runAllRef = useRef(false);
    const resultsRef = useRef(results);
    const focusRef = useRef(focus);
    const fileInput = useRef(null);
    useEffect(() => { resultsRef.current = results; }, [results]);
    useEffect(() => { focusRef.current = focus; }, [focus]);

    const sections = useMemo(() => {
        if (!doc) return [];
        const out = [];
        for (let from = 1, i = 0; from <= doc.pages; from += chunk, i++) {
            out.push({ index: i, from, to: Math.min(from + chunk - 1, doc.pages) });
        }
        return out;
    }, [doc, chunk]);
    const cacheKey = doc ? cacheKeyFor(doc, chunk) : null;

    const abortAll = useCallback(() => {
        runAllRef.current = false;
        controllers.current.forEach((c) => c.abort());
        controllers.current.clear();
        setRunAll(null);
    }, []);

    const closeDoc = useCallback(() => {
        abortAll();
        genRef.current++;
        taskRef.current?.destroy();
        taskRef.current = null;
        pdfRef.current = null;
        setDoc(null);
        setOpening(null);
        setResults({});
    }, [abortAll]);

    useEffect(() => () => {
        runAllRef.current = false;
        controllers.current.forEach((c) => c.abort());
        taskRef.current?.destroy();
    }, []);

    const loadResults = (d, size) => {
        const cached = readCache(cacheKeyFor(d, size));
        const next = {};
        for (const [k, text] of Object.entries(cached)) if (text) next[k] = { status: 'done', text };
        setResults(next);
        setExpanded({ 0: true });
    };

    const openSource = async ({ name, size, kind, url, file }) => {
        closeDoc();
        const gen = genRef.current;
        setOpening({ name, progress: 0 });
        try {
            const source = file ? { data: new Uint8Array(await file.arrayBuffer()) } : { url };
            const task = await openPdf(source, (p) => gen === genRef.current && setOpening((o) => o && { ...o, progress: p }));
            if (gen !== genRef.current) { task.destroy(); return; }
            taskRef.current = task;
            const pdf = await task.promise;
            if (gen !== genRef.current) return;
            pdfRef.current = pdf;
            const info = { name, size, pages: pdf.numPages, kind, url };
            setDoc(info);
            setOpening(null);
            loadResults(info, chunk);
            const id = `${kind}:${name}:${size}`;
            setRecent((list) => [
                { id, name, size, pages: pdf.numPages, kind, url, openedAt: new Date().toISOString() },
                ...(Array.isArray(list) ? list : []).filter((r) => r.id !== id),
            ].slice(0, MAX_RECENT));
        } catch (e) {
            if (gen !== genRef.current) return;
            setOpening(null);
            taskRef.current = null;
            const msg = e?.name === 'PasswordException' ? 'This PDF is password-protected.' : e?.message || 'Unknown error';
            push(`Couldn't open ${name}: ${msg}`, 'error');
        }
    };

    const openFile = (file) => {
        if (!file) return;
        if (!isPdf(file)) { push(`"${file.name}" isn't a PDF. Please choose a .pdf file.`, 'error'); return; }
        openSource({ name: file.name, size: file.size, kind: 'file', file });
    };

    const changeChunk = (size) => {
        if (size === chunk) return;
        abortAll();
        setChunk(size);
        if (doc) loadResults(doc, size);
    };

    const patch = useCallback((i, obj) => setResults((r) => ({ ...r, [i]: { ...r[i], ...obj } })), []);

    const sectionText = useCallback(async (s) => {
        if (!pdfRef.current) throw new Error('No document open');
        return extractText(pdfRef.current, s.from, s.to);
    }, []);

    // Resolves to 'done' | 'error' | 'aborted'.
    const explain = useCallback(async (s) => {
        const pdf = pdfRef.current;
        if (!pdf || !doc) return 'aborted';
        controllers.current.get(s.index)?.abort();
        const ctrl = new AbortController();
        controllers.current.set(s.index, ctrl);
        const gen = genRef.current;
        const key = cacheKeyFor(doc, chunk);
        const live = () => gen === genRef.current && !ctrl.signal.aborted;
        const count = s.to - s.from + 1;
        setExpanded((e) => ({ ...e, [s.index]: true }));
        patch(s.index, { status: 'preparing', text: '', error: null, progress: 'Reading text…' });

        let acc = '';
        let raf = 0;
        try {
            const text = (await sectionText(s)).slice(0, MAX_TEXT);
            let budget = PAYLOAD_LIMIT - JSON.stringify(text).length - 4000;
            for (let attempt = 0; ; attempt++) {
                const images = await renderPagesForUpload(pdf, s.from, s.to, {
                    budget: Math.max(budget, 400_000),
                    signal: ctrl.signal,
                    onProgress: ({ done, pass }) => live() && patch(s.index, {
                        progress: `${pass ? 'Compressing' : 'Rendering'} pages ${Math.min(done + 1, count)}/${count}…`,
                    }),
                });
                if (!live()) throw new DOMException('Aborted', 'AbortError');
                patch(s.index, { status: 'waiting', progress: 'Reading the pages…' });

                let streamError = null;
                const flush = () => { raf = 0; if (live()) patch(s.index, { status: 'streaming', text: acc }); };
                try {
                    await streamSSE('/pdf/explain', {
                        label: pageLabel(s),
                        total_pages: doc.pages,
                        images,
                        text,
                        focus: (focusRef.current || '').trim(),
                    }, (ev) => {
                        if (ev.type === 'delta' && ev.text) {
                            acc += ev.text;
                            if (!raf) raf = requestAnimationFrame(flush);
                        } else if (ev.type === 'error') {
                            streamError = ev.message || 'The model returned an error';
                        }
                    }, ctrl.signal);
                } catch (e) {
                    if (attempt === 0 && !acc && /too large/i.test(e.message || '')) {
                        budget = Math.floor(budget / 2);
                        continue;
                    }
                    throw e;
                }
                if (streamError) throw new Error(streamError);
                break;
            }
            cancelAnimationFrame(raf);
            if (!live()) throw new DOMException('Aborted', 'AbortError');
            if (!acc.trim()) throw new Error('No explanation came back. Try again.');
            patch(s.index, { status: 'done', text: acc, progress: null });
            if (!writeCache(key, s.index, acc)) push('Notes are too large to save offline, but they are shown below.', 'info');
            return 'done';
        } catch (e) {
            cancelAnimationFrame(raf);
            if (gen !== genRef.current) return 'aborted';
            if (e?.name === 'AbortError' || ctrl.signal.aborted) {
                patch(s.index, acc ? { status: 'stopped', text: acc, progress: null } : { status: 'idle', text: '', progress: null });
                return 'aborted';
            }
            patch(s.index, { status: 'error', text: acc, error: e?.message || 'Something went wrong', progress: null });
            return 'error';
        } finally {
            if (controllers.current.get(s.index) === ctrl) controllers.current.delete(s.index);
        }
    }, [doc, chunk, patch, sectionText, push]);

    const stop = useCallback((i) => controllers.current.get(i)?.abort(), []);

    const explainAll = async () => {
        if (runAllRef.current) return;
        runAllRef.current = true;
        const gen = genRef.current;
        for (const s of sections) {
            if (!runAllRef.current || gen !== genRef.current) break;
            if (resultsRef.current[s.index]?.status === 'done') continue;
            setRunAll({ current: s.index });
            const res = await explain(s);
            if (res === 'error') {
                push(`Stopped at pages ${pageLabel(s)}. Fix the issue and run again; finished sections are kept.`, 'error');
                break;
            }
            if (res === 'aborted') break;
        }
        if (gen === genRef.current) {
            runAllRef.current = false;
            setRunAll(null);
        }
    };

    const stopAll = () => abortAll();

    const doneCount = sections.filter((s) => results[s.index]?.status === 'done').length;
    const busy = Object.values(results).some((r) => ['preparing', 'waiting', 'streaming'].includes(r?.status));

    return (
        <div className="mx-auto w-full max-w-3xl space-y-5 min-w-0">
            <header className="animate-rise">
                <p className="eyebrow">Study tools</p>
                <h1 className="text-2xl sm:text-[28px] font-semibold tracking-tight mt-1">PDF Studio</h1>
                <p className="text-sm text-muted mt-1">
                    Turn lecture notes into clear, section-by-section explanations, then quiz yourself.
                </p>
            </header>

            <input
                ref={fileInput}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => { openFile(e.target.files?.[0]); e.target.value = ''; }}
            />

            {!doc && (
                <EmptyState
                    opening={opening}
                    recent={Array.isArray(recent) ? recent : []}
                    onPick={() => fileInput.current?.click()}
                    onFile={openFile}
                    onSample={(s) => openSource({ name: s.name, size: 'sample', kind: 'sample', url: s.url })}
                    onCancel={closeDoc}
                    onRemoveRecent={(id) => setRecent((l) => l.filter((r) => r.id !== id))}
                    onClearRecent={() => setRecent([])}
                />
            )}

            {doc && (
                <>
                    <Card
                        className="card-pad sticky z-20 animate-rise"
                        style={{ top: 'var(--sticky-top, 12px)' }}
                    >
                        <div className="flex items-start gap-3">
                            <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0">
                                <FileText className="h-5 w-5" />
                            </div>
                            <div className="min-w-0 flex-1">
                                <h2 className="text-[15px] font-semibold tracking-tight truncate" title={doc.name}>{doc.name}</h2>
                                <p className="text-xs text-subtle mt-0.5">
                                    {doc.pages} pages · {sections.length} sections · {formatSize(doc.size)}
                                </p>
                            </div>
                            <Button variant="ghost" className="btn-icon shrink-0" onClick={closeDoc} aria-label="Close document" title="Close">
                                <X className="h-4 w-4" />
                            </Button>
                        </div>

                        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
                            <div className="flex-1 min-w-[160px]">
                                <div className="flex items-baseline justify-between gap-2 mb-1.5 text-xs">
                                    <span className="text-muted truncate">
                                        {runAll
                                            ? `Explaining pages ${pageLabel(sections[runAll.current] || sections[0])}…`
                                            : doneCount === sections.length ? 'All sections explained' : 'Progress'}
                                    </span>
                                    <span className="text-subtle tabular-nums shrink-0">{doneCount}/{sections.length}</span>
                                </div>
                                <ProgressBar
                                    value={sections.length ? (doneCount / sections.length) * 100 : 0}
                                    color={doneCount === sections.length ? 'var(--ok)' : 'var(--accent)'}
                                />
                            </div>
                            {runAll ? (
                                <Button variant="secondary" icon={Square} onClick={stopAll}>Stop</Button>
                            ) : (
                                <Button
                                    variant="primary"
                                    icon={Sparkles}
                                    onClick={explainAll}
                                    disabled={doneCount === sections.length || busy}
                                >
                                    {doneCount > 0 && doneCount < sections.length ? 'Explain remaining' : 'Explain all'}
                                </Button>
                            )}
                        </div>
                    </Card>

                    <Card className="card-pad">
                        <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-end">
                            <div>
                                <span className="label">Pages per section</span>
                                <Segmented
                                    className={cx(busy && 'opacity-50 pointer-events-none')}
                                    options={[{ value: 5, label: '5 pages' }, { value: 10, label: '10 pages' }]}
                                    value={chunk}
                                    onChange={changeChunk}
                                />
                            </div>
                            <div className="min-w-0">
                                <label className="label" htmlFor="pdf-focus">Focus <span className="text-subtle font-normal">(optional)</span></label>
                                <input
                                    id="pdf-focus"
                                    className="input"
                                    value={focus}
                                    maxLength={500}
                                    onChange={(e) => setFocus(e.target.value)}
                                    placeholder="e.g. explain for exam revision, focus on formulas"
                                />
                            </div>
                        </div>
                    </Card>

                    <div className="space-y-3">
                        {sections.map((s) => (
                            <Section
                                key={`${cacheKey}:${s.index}`}
                                section={s}
                                total={sections.length}
                                doc={doc}
                                result={results[s.index]}
                                expanded={!!expanded[s.index]}
                                onToggle={() => setExpanded((e) => ({ ...e, [s.index]: !e[s.index] }))}
                                onExplain={() => explain(s)}
                                onStop={() => stop(s.index)}
                                getText={() => sectionText(s)}
                                disabled={!!runAll}
                            />
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}

function EmptyState({ opening, recent, onPick, onFile, onSample, onCancel, onRemoveRecent, onClearRecent }) {
    const [drag, setDrag] = useState(false);
    const depth = useRef(0);

    if (opening) {
        return (
            <Card className="card-pad animate-rise">
                <div className="flex items-center gap-3">
                    <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0">
                        <Spinner className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">Opening {opening.name}</p>
                        <p className="text-xs text-subtle mt-0.5 tabular-nums">
                            {opening.progress > 0 && opening.progress < 1 ? `Loading ${Math.round(opening.progress * 100)}%` : 'Preparing document…'}
                        </p>
                    </div>
                    <Button variant="ghost" onClick={onCancel}>Cancel</Button>
                </div>
                <ProgressBar className="mt-4" value={Math.max(opening.progress * 100, 4)} />
            </Card>
        );
    }

    return (
        <div className="space-y-5 animate-rise">
            <div
                role="button"
                tabIndex={0}
                onClick={onPick}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(); } }}
                onDragEnter={(e) => { e.preventDefault(); depth.current++; setDrag(true); }}
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; }}
                onDragLeave={() => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setDrag(false); }}
                onDrop={(e) => {
                    e.preventDefault();
                    depth.current = 0;
                    setDrag(false);
                    onFile(e.dataTransfer.files?.[0]);
                }}
                className={cx(
                    'card flex flex-col items-center justify-center text-center cursor-pointer px-5 py-12 sm:py-16 border-2 border-dashed transition-colors',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                    drag ? 'border-accent bg-accent-soft' : 'border-line-strong hover:border-accent/60 hover:bg-surface-2/60',
                )}
            >
                <div className={cx(
                    'grid place-items-center h-14 w-14 rounded-2xl mb-4 transition-all',
                    drag ? 'bg-accent text-accent-fg scale-110' : 'bg-accent-soft text-accent',
                )}>
                    <Upload className="h-6 w-6" />
                </div>
                <p className="text-base font-semibold tracking-tight">{drag ? 'Drop to open' : 'Drop a PDF here'}</p>
                <p className="text-sm text-muted mt-1">or <span className="text-accent font-medium">browse your files</span></p>
                <p className="text-xs text-subtle mt-3 max-w-xs">Your file stays on this device. Only the pages you explain are sent for analysis.</p>
            </div>

            <div>
                <p className="eyebrow mb-2">Try a sample</p>
                <div className="grid gap-2 sm:grid-cols-2">
                    {SAMPLES.map((s) => (
                        <button
                            key={s.url}
                            type="button"
                            onClick={() => onSample(s)}
                            className="card row-hover flex items-center gap-3 p-3 text-left min-h-14 group"
                        >
                            <div className="grid place-items-center h-9 w-9 rounded-lg bg-surface-2 border border-line text-muted shrink-0 group-hover:text-accent transition-colors">
                                <BookOpen className="h-4 w-4" />
                            </div>
                            <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium truncate">{s.name}</p>
                                <p className="text-xs text-subtle">{s.hint}</p>
                            </div>
                            <Play className="h-4 w-4 text-subtle group-hover:text-accent shrink-0" />
                        </button>
                    ))}
                </div>
            </div>

            {recent.length > 0 && (
                <div>
                    <div className="flex items-center justify-between mb-2">
                        <p className="eyebrow">Recent</p>
                        <button type="button" className="text-xs text-subtle hover:text-fg h-9 px-2 -mr-2" onClick={onClearRecent}>Clear</button>
                    </div>
                    <Card className="divide-y divide-line overflow-hidden">
                        {recent.map((r) => {
                            const canOpen = r.kind === 'sample' && r.url;
                            return (
                                <div key={r.id} className="flex items-center gap-1 pr-1.5">
                                    <button
                                        type="button"
                                        onClick={() => (canOpen ? onSample({ name: r.name, url: r.url }) : onPick())}
                                        className="row-hover flex items-center gap-3 flex-1 min-w-0 px-3.5 py-3 text-left min-h-14"
                                        title={canOpen ? 'Open' : 'Re-upload this file to open it'}
                                    >
                                        <FileText className={cx('h-4 w-4 shrink-0', canOpen ? 'text-accent' : 'text-subtle')} />
                                        <div className="min-w-0 flex-1">
                                            <p className={cx('text-sm font-medium truncate', !canOpen && 'text-muted')}>{r.name}</p>
                                            <p className="text-xs text-subtle flex flex-wrap items-center gap-x-1.5">
                                                <span>{r.pages} pages</span>
                                                <span aria-hidden>·</span>
                                                <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{timeAgo(r.openedAt)}</span>
                                                {!canOpen && (<><span aria-hidden>·</span><span>re-upload to open</span></>)}
                                            </p>
                                        </div>
                                        {canOpen ? <Play className="h-4 w-4 text-subtle shrink-0" /> : <Upload className="h-4 w-4 text-subtle shrink-0" />}
                                    </button>
                                    <Button variant="ghost" className="btn-icon shrink-0" onClick={() => onRemoveRecent(r.id)} aria-label={`Remove ${r.name} from recent`}>
                                        <X className="h-3.5 w-3.5" />
                                    </Button>
                                </div>
                            );
                        })}
                    </Card>
                </div>
            )}
        </div>
    );
}

const STATUS = {
    idle: { label: 'Not started', cls: 'text-muted bg-surface-2' },
    preparing: { label: 'Explaining…', cls: 'text-accent bg-accent-soft', spin: true },
    waiting: { label: 'Explaining…', cls: 'text-accent bg-accent-soft', spin: true },
    streaming: { label: 'Explaining…', cls: 'text-accent bg-accent-soft', spin: true },
    done: { label: 'Done', cls: 'text-ok bg-ok/10' },
    stopped: { label: 'Stopped', cls: 'text-medium bg-medium/10' },
    error: { label: 'Error', cls: 'text-danger bg-danger/10' },
};

function Section({ section, total, doc, result, expanded, onToggle, onExplain, onStop, getText, disabled }) {
    const push = useToast();
    const status = result?.status || 'idle';
    const meta = STATUS[status] || STATUS.idle;
    const working = !!meta.spin;
    const label = pageLabel(section);
    const [copied, setCopied] = useState(null);
    const [copyingPrompt, setCopyingPrompt] = useState(false);
    const [quizOpen, setQuizOpen] = useState(false);

    useEffect(() => {
        if (!copied) return;
        const t = setTimeout(() => setCopied(null), 1800);
        return () => clearTimeout(t);
    }, [copied]);

    const copyNotes = async () => {
        const ok = await copyText(`## ${doc.name} — Pages ${label}\n\n${result.text}`);
        if (ok) { setCopied('notes'); push('Notes copied as Markdown'); } else push('Copy failed. Your browser blocked clipboard access.', 'error');
    };

    const copyPrompt = async () => {
        setCopyingPrompt(true);
        try {
            const text = await getText();
            const prompt = [
                `I'm studying pages ${label} of "${doc.name}" (${doc.pages} pages total).`,
                'Explain these pages clearly for exam revision: the key concepts in plain language, important definitions, formulas and how to use them, worked examples, and the questions most likely to be asked in an exam.',
                'The text below was extracted from the PDF, so diagrams are missing and some formatting may be broken.',
                '',
                '----- EXTRACTED TEXT -----',
                text,
            ].join('\n');
            const ok = await copyText(prompt);
            if (ok) { setCopied('prompt'); push('Prompt copied. Paste it into ChatGPT.'); } else push('Copy failed. Your browser blocked clipboard access.', 'error');
        } catch (e) {
            push(e.message || 'Could not read the pages', 'error');
        } finally {
            setCopyingPrompt(false);
        }
    };

    const hasText = !!result?.text;

    return (
        <Card className={cx('overflow-hidden transition-colors', working && 'border-accent/40')}>
            <div className="flex items-center gap-2 p-3 sm:px-4">
                <button
                    type="button"
                    onClick={onToggle}
                    aria-expanded={expanded}
                    className="flex items-center gap-2.5 flex-1 min-w-0 text-left min-h-11 rounded-lg -m-1 p-1 focus-visible:outline-2 focus-visible:outline-accent"
                >
                    <ChevronDown className={cx('h-4 w-4 text-subtle shrink-0 transition-transform duration-200', !expanded && '-rotate-90')} />
                    <div className="min-w-0">
                        <p className="text-[15px] font-semibold tracking-tight">Pages {label}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-subtle whitespace-nowrap">Section {section.index + 1} of {total}</span>
                            <span className={cx('badge', meta.cls)}>
                                {meta.spin && <Spinner className="h-3 w-3" />}
                                {meta.label}
                            </span>
                        </div>
                    </div>
                </button>
                {working ? (
                    <Button variant="secondary" icon={Square} onClick={onStop} className="shrink-0">Stop</Button>
                ) : (
                    <Button
                        variant={status === 'done' ? 'ghost' : 'primary'}
                        icon={status === 'done' || status === 'error' || status === 'stopped' ? RotateCcw : Sparkles}
                        onClick={onExplain}
                        disabled={disabled}
                        className="shrink-0"
                    >
                        {status === 'done' ? 'Re-explain' : status === 'error' ? 'Retry' : 'Explain'}
                    </Button>
                )}
            </div>

            {expanded && (
                <div className="border-t border-line px-4 py-4 sm:px-5 min-w-0 animate-fade">
                    {(status === 'preparing' || status === 'waiting') && (
                        <div className="space-y-3">
                            <p className="flex items-center gap-2 text-sm text-muted">
                                <Spinner className="h-4 w-4 text-accent" />
                                <span className="tabular-nums">{result?.progress || 'Preparing…'}</span>
                            </p>
                            <Skeleton className="h-4 w-2/3" />
                            <Skeleton className="h-3 w-full" />
                            <Skeleton className="h-3 w-5/6" />
                            <Skeleton className="h-3 w-3/4" />
                        </div>
                    )}

                    {status === 'error' && (
                        <div className="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-3 text-sm mb-4">
                            <CircleAlert className="h-4 w-4 text-danger mt-0.5 shrink-0" />
                            <div className="min-w-0">
                                <p className="font-medium text-danger">Couldn't explain these pages</p>
                                <p className="text-muted mt-0.5 break-words">{result?.error}</p>
                            </div>
                        </div>
                    )}

                    {status === 'stopped' && (
                        <p className="flex items-center gap-2 text-xs text-subtle mb-3">
                            <Info className="h-3.5 w-3.5" /> Stopped early. This partial explanation isn't saved.
                        </p>
                    )}

                    {hasText && status !== 'preparing' && status !== 'waiting' && (
                        <div className="min-w-0 break-words">
                            <Markdown streaming={status === 'streaming'}>{result.text}</Markdown>
                        </div>
                    )}

                    {status === 'idle' && (
                        <p className="text-sm text-subtle">
                            Explain these pages to get structured study notes, or copy them into another assistant.
                        </p>
                    )}

                    {!working && (
                        <div className={cx('flex flex-wrap gap-2', (hasText || status === 'idle' || status === 'error') && 'mt-4')}>
                            {status === 'done' && (
                                <>
                                    <Button
                                        variant={quizOpen ? 'secondary' : 'primary'}
                                        icon={ListChecks}
                                        onClick={() => setQuizOpen((o) => !o)}
                                    >
                                        {quizOpen ? 'Hide quiz' : 'Quiz me'}
                                    </Button>
                                    <Button variant="secondary" icon={copied === 'notes' ? Check : Copy} onClick={copyNotes}>
                                        {copied === 'notes' ? 'Copied' : 'Copy notes'}
                                    </Button>
                                </>
                            )}
                            <Button
                                variant="secondary"
                                icon={copied === 'prompt' ? Check : MessageSquareText}
                                loading={copyingPrompt}
                                onClick={copyPrompt}
                            >
                                {copied === 'prompt' ? 'Copied' : 'Copy for ChatGPT'}
                            </Button>
                        </div>
                    )}

                    {status === 'done' && quizOpen && <Quiz notes={result.text} onClose={() => setQuizOpen(false)} />}
                </div>
            )}
        </Card>
    );
}

function normalizeQuestions(data) {
    const list = Array.isArray(data?.questions) ? data.questions : Array.isArray(data) ? data : [];
    return list
        .filter((q) => q && q.question && Array.isArray(q.options) && q.options.length >= 2)
        .map((q) => {
            const options = q.options.map(String);
            let correct = Number(q.correct_answer);
            if (!Number.isInteger(correct) || correct < 0 || correct >= options.length) {
                correct = options.findIndex((o) => o.trim() === String(q.correct_answer ?? '').trim());
            }
            return { question: String(q.question), options, correct, explanation: q.explanation ? String(q.explanation) : '' };
        })
        .filter((q) => q.correct >= 0);
}

function Quiz({ notes, onClose }) {
    const [round, setRound] = useState(0);
    return <QuizRound key={round} notes={notes} onClose={onClose} onNew={() => setRound((r) => r + 1)} />;
}

function QuizRound({ notes, onClose, onNew }) {
    const push = useToast();
    const [state, setState] = useState({ loading: true, error: null, questions: [] });
    const [answers, setAnswers] = useState({});
    const [submitted, setSubmitted] = useState(false);

    useEffect(() => {
        const ctrl = new AbortController();
        api('/pdf/quiz', { method: 'POST', body: { text: notes }, signal: ctrl.signal })
            .then((res) => {
                const questions = normalizeQuestions(res?.data);
                if (!questions.length) throw new Error('The quiz came back empty. Try again.');
                setState({ loading: false, error: null, questions });
            })
            .catch((e) => {
                if (e?.name === 'AbortError') return;
                setState({ loading: false, error: e.message || 'Could not generate a quiz', questions: [] });
            });
        return () => ctrl.abort();
    }, [notes]);

    const { loading, error, questions } = state;
    const answered = Object.keys(answers).length;
    const score = questions.reduce((n, q, i) => n + (answers[i] === q.correct ? 1 : 0), 0);

    const submit = () => {
        setSubmitted(true);
        push(`You scored ${score}/${questions.length}`, score === questions.length ? 'success' : 'info');
    };

    return (
        <div className="mt-5 rounded-2xl border border-line bg-surface-2/60 p-3 sm:p-4 animate-rise">
            <div className="flex items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2 min-w-0">
                    <div className="grid place-items-center h-8 w-8 rounded-lg bg-accent-soft text-accent shrink-0">
                        <ListChecks className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                        <p className="text-sm font-semibold">Quick quiz</p>
                        <p className="text-xs text-subtle">
                            {loading ? 'Writing questions…' : submitted ? 'Results' : `${answered}/${questions.length} answered`}
                        </p>
                    </div>
                </div>
                <Button variant="ghost" className="btn-icon" onClick={onClose} aria-label="Close quiz"><X className="h-4 w-4" /></Button>
            </div>

            {loading && (
                <div className="space-y-4">
                    {[0, 1].map((k) => (
                        <div key={k} className="space-y-2">
                            <Skeleton className="h-4 w-4/5 bg-surface-3" />
                            {[0, 1, 2, 3].map((o) => <Skeleton key={o} className="h-10 w-full bg-surface-3" />)}
                        </div>
                    ))}
                </div>
            )}

            {error && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-3">
                    <p className="text-sm text-danger min-w-0 break-words">{error}</p>
                    <Button variant="secondary" icon={RotateCcw} onClick={onNew}>Try again</Button>
                </div>
            )}

            {!loading && !error && (
                <>
                    {submitted && (
                        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 mb-4">
                            <p className="text-2xl font-semibold tabular-nums tracking-tight">
                                <span className={score === questions.length ? 'text-ok' : score / questions.length >= 0.6 ? 'text-fg' : 'text-danger'}>{score}</span>
                                <span className="text-subtle">/{questions.length}</span>
                            </p>
                            <p className="text-sm text-muted">
                                {score === questions.length ? 'Perfect. You know this section.' : score / questions.length >= 0.6 ? 'Solid. Review the misses below.' : 'Worth another read of the notes above.'}
                            </p>
                        </div>
                    )}

                    <ol className="space-y-5">
                        {questions.map((q, qi) => (
                            <li key={qi} className="min-w-0">
                                <p className="text-sm font-medium leading-snug mb-2">
                                    <span className="text-subtle mr-1.5 tabular-nums">{qi + 1}.</span>{q.question}
                                </p>
                                <div className="grid gap-1.5">
                                    {q.options.map((opt, oi) => {
                                        const picked = answers[qi] === oi;
                                        const isCorrect = oi === q.correct;
                                        return (
                                            <button
                                                key={oi}
                                                type="button"
                                                disabled={submitted}
                                                onClick={() => setAnswers((a) => ({ ...a, [qi]: oi }))}
                                                aria-pressed={picked}
                                                className={cx(
                                                    'flex items-start gap-2.5 w-full min-h-10 rounded-xl border px-3 py-2 text-left text-sm transition-colors',
                                                    !submitted && (picked
                                                        ? 'border-accent bg-accent-soft text-fg'
                                                        : 'border-line bg-surface hover:border-line-strong hover:bg-surface-2'),
                                                    submitted && isCorrect && 'border-ok/50 bg-ok/10 text-fg',
                                                    submitted && picked && !isCorrect && 'border-danger/50 bg-danger/10 text-fg',
                                                    submitted && !picked && !isCorrect && 'border-line bg-surface text-muted opacity-70',
                                                )}
                                            >
                                                <span className={cx(
                                                    'grid place-items-center h-5 w-5 rounded-md text-[11px] font-semibold shrink-0 mt-px',
                                                    submitted && isCorrect ? 'bg-ok text-white'
                                                        : submitted && picked ? 'bg-danger text-white'
                                                            : picked ? 'bg-accent text-accent-fg' : 'bg-surface-2 text-subtle border border-line',
                                                )}>
                                                    {submitted && isCorrect ? <Check className="h-3 w-3" strokeWidth={3} />
                                                        : submitted && picked ? <X className="h-3 w-3" strokeWidth={3} />
                                                            : String.fromCharCode(65 + oi)}
                                                </span>
                                                <span className="min-w-0 break-words">{opt}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                                {submitted && q.explanation && (
                                    <p className={cx(
                                        'mt-2 flex items-start gap-2 text-[13px] leading-relaxed rounded-lg px-3 py-2',
                                        answers[qi] === q.correct ? 'text-muted bg-ok/5' : 'text-muted bg-danger/5',
                                    )}>
                                        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                                        <span className="min-w-0 break-words">{q.explanation}</span>
                                    </p>
                                )}
                            </li>
                        ))}
                    </ol>

                    <div className="flex flex-wrap items-center gap-2 mt-5">
                        {!submitted ? (
                            <>
                                <Button variant="primary" icon={Check} onClick={submit} disabled={answered < questions.length}>Submit</Button>
                                {answered < questions.length && (
                                    <span className="text-xs text-subtle">Answer all {questions.length} to submit</span>
                                )}
                            </>
                        ) : (
                            <>
                                <Button variant="primary" icon={RotateCcw} onClick={() => { setAnswers({}); setSubmitted(false); }}>Retry</Button>
                                <Button variant="secondary" icon={Sparkles} onClick={onNew}>New questions</Button>
                            </>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
