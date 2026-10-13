import { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
    Bot, Check, ChevronDown, CircleAlert, Download, ExternalLink, FileArchive, FileMinus, FilePen, FilePlus, FileText,
    Files, FolderCog, FolderOpen, ListChecks, Play, RotateCcw, StickyNote, Trash2, Upload, X,
} from 'lucide-react';
import { api, getToken } from '../lib/api';
import Markdown from '../components/Markdown';
import { Button, Card, CardHeader, ProgressBar, Spinner, cx, useToast } from '../components/ui';

const DEFAULT_MAX_MB = 4;
const PROMPT_MAX = 4000;
const SKIP_DIRS = ['node_modules', '.git', 'dist', 'build', '__pycache__', '.venv'];
const EXAMPLES = [
    'Complete this lab: implement the missing functions and add tests',
    'Fix the failing tests and explain each bug you found',
    'Implement the assignment described in the README / problem statement',
    'Add input validation and error handling, then refactor for readability',
    'Write docstrings and comments, and add a short usage section',
];
const STAGES = [
    { id: 'upload', label: 'Uploading' },
    { id: 'working', label: 'Gemini is working' },
    { id: 'receiving', label: 'Building README & PDF' },
];
const ACTIONS = {
    create: { label: 'Created', icon: FilePlus, cls: 'text-ok bg-ok/10' },
    update: { label: 'Updated', icon: FilePen, cls: 'text-accent bg-accent-soft' },
    delete: { label: 'Deleted', icon: FileMinus, cls: 'text-danger bg-danger/10' },
};

const fmtSize = (b) => (b < 1024 ? `${b} B` : b < 1024 * 1024 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1024 / 1024).toFixed(2)} MB`);
const fmtTime = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
const isSkipped = (path) => path.split('/').some((seg) => SKIP_DIRS.includes(seg));
const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

function b64ToBlob(b64, type) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type });
}

// --- Folder walking (drag & drop of directories via the File System entries API) ---
const entryFile = (entry) => new Promise((resolve, reject) => entry.file(resolve, reject));
const readBatch = (reader) => new Promise((resolve, reject) => reader.readEntries(resolve, reject));

async function walkEntry(entry, out, skipped) {
    const path = entry.fullPath.replace(/^\/+/, '');
    if (isSkipped(path)) { skipped.count += 1; return; }
    if (entry.isFile) {
        out.push({ file: await entryFile(entry), path });
    } else if (entry.isDirectory) {
        const reader = entry.createReader();
        // readEntries returns results in batches; keep reading until it returns nothing.
        for (;;) {
            const batch = await readBatch(reader);
            if (!batch.length) break;
            for (const child of batch) await walkEntry(child, out, skipped);
        }
    }
}

function Steps({ stage, uploadPct, downPct, elapsed }) {
    const at = STAGES.findIndex((s) => s.id === stage);
    return (
        <>
            <ol className="space-y-3" aria-label="Progress">
            {STAGES.map((s, i) => {
                const done = i < at;
                const active = i === at;
                return (
                    <li key={s.id} className="flex items-start gap-3" aria-current={active ? 'step' : undefined}>
                        <span
                            className={cx(
                                'grid place-items-center h-6 w-6 rounded-full border text-[11px] font-semibold shrink-0',
                                done ? 'bg-ok border-ok text-white' : active ? 'border-accent text-accent bg-accent-soft' : 'border-line-strong text-subtle',
                            )}
                        >
                            {done ? <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden /> : active ? <Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> : i + 1}
                        </span>
                        <div className="min-w-0 flex-1 pt-0.5">
                            <p className={cx('text-sm font-medium', active ? 'text-fg' : done ? 'text-muted' : 'text-subtle')}>
                                {s.label}
                                <span className="sr-only">{done ? ' (done)' : active ? ' (in progress)' : ' (pending)'}</span>
                            </p>
                            {active && s.id === 'upload' && (
                                <div className="mt-1.5 flex items-center gap-2">
                                    <ProgressBar value={uploadPct} className="flex-1" />
                                    <span className="text-xs text-muted tabular-nums w-9 text-right">{uploadPct}%</span>
                                </div>
                            )}
                            {active && s.id === 'working' && (
                                <p className="text-xs text-subtle mt-0.5">
                                    Usually 1–4 minutes. Gemini edits the project, then the server writes the README and renders the PDF.
                                </p>
                            )}
                            {active && s.id === 'receiving' && (
                                <p className="text-xs text-subtle mt-0.5 tabular-nums">
                                    Results are arriving{downPct != null ? ` · ${downPct}%` : '…'}
                                </p>
                            )}
                        </div>
                    </li>
                );
            })}
            </ol>
            <p className="mt-3 text-xs text-subtle tabular-nums pl-9" aria-live="off">Elapsed {fmtTime(elapsed)}</p>
        </>
    );
}

function ChangesTable({ changes }) {
    if (!changes?.length) return <p className="text-sm text-subtle">No file changes were reported.</p>;
    return (
        <div className="-mx-4 sm:mx-0 overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left">
                        <th scope="col" className="eyebrow font-semibold py-2 pl-4 sm:pl-0 pr-3 w-px">Action</th>
                        <th scope="col" className="eyebrow font-semibold py-2 pr-3">File</th>
                        <th scope="col" className="eyebrow font-semibold py-2 pr-4 sm:pr-0 hidden md:table-cell">Why</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-line border-t border-line">
                    {changes.map((c, i) => {
                        const a = ACTIONS[c.action] || { label: c.action || 'Changed', icon: FileText, cls: 'text-muted bg-surface-2' };
                        return (
                            <tr key={`${c.path}-${i}`} className="align-top">
                                <td className="py-2.5 pl-4 sm:pl-0 pr-3">
                                    <span className={cx('badge', a.cls)}><a.icon className="h-3 w-3" aria-hidden />{a.label}</span>
                                </td>
                                <td className="py-2.5 pr-4 md:pr-3 min-w-0">
                                    <code className={cx('font-mono text-[12.5px] break-all', c.action === 'delete' && 'line-through text-muted')}>{c.path}</code>
                                    {c.why && <p className="md:hidden text-xs text-muted mt-1 leading-snug">{c.why}</p>}
                                </td>
                                <td className="py-2.5 pr-4 sm:pr-0 text-muted leading-snug hidden md:table-cell">{c.why}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

function Result({ result, onAgain, onReset }) {
    const { data, zipUrl, pdfUrl } = result;
    return (
        <div className="space-y-4 animate-rise">
            <Card className="card-pad">
                <CardHeader
                    title={data.title || 'Task complete'}
                    subtitle={data.model ? `Done with ${data.model}` : 'Done'}
                    icon={Check}
                />
                {data.summary && <p className="text-sm leading-relaxed text-fg whitespace-pre-line">{data.summary}</p>}
                <div className="mt-4 flex flex-wrap gap-2">
                    {zipUrl && (
                        <a href={zipUrl} download={data.zip_name || 'project.zip'} className="btn btn-primary">
                            <Download className="h-4 w-4" aria-hidden /> Download project (.zip)
                        </a>
                    )}
                    {pdfUrl && (
                        <a href={pdfUrl} download={data.pdf_name || 'report.pdf'} className="btn btn-secondary">
                            <FileText className="h-4 w-4" aria-hidden /> Download report (.pdf)
                        </a>
                    )}
                </div>
            </Card>

            {data.steps?.length > 0 && (
                <Card className="card-pad">
                    <CardHeader title="What Gemini did" subtitle={`${data.steps.length} step${data.steps.length === 1 ? '' : 's'}`} icon={ListChecks} />
                    <ol className="space-y-2 text-sm">
                        {data.steps.map((s, i) => (
                            <li key={i} className="flex gap-2.5">
                                <span className="text-subtle tabular-nums font-mono text-xs pt-0.5 w-5 shrink-0 text-right">{i + 1}.</span>
                                <span className="min-w-0 leading-relaxed">{s}</span>
                            </li>
                        ))}
                    </ol>
                </Card>
            )}

            <Card className="card-pad">
                <CardHeader title="Changes" subtitle={`${data.changes?.length || 0} file${data.changes?.length === 1 ? '' : 's'}`} icon={Files} />
                <ChangesTable changes={data.changes} />
            </Card>

            {data.notes?.length > 0 && (
                <Card className="card-pad">
                    <CardHeader title="Notes" subtitle="Things to check before you submit" icon={StickyNote} />
                    <ul className="list-disc pl-5 space-y-1.5 text-sm leading-relaxed marker:text-subtle">
                        {data.notes.map((n, i) => <li key={i}>{n}</li>)}
                    </ul>
                </Card>
            )}

            {data.readme_md && (
                <Card className="card-pad">
                    <details className="group">
                        <summary className="flex items-center justify-between gap-3 cursor-pointer list-none rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden">
                            <span className="flex items-center gap-2.5 min-w-0">
                                <span className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line text-muted shrink-0">
                                    <FileText className="h-4 w-4" aria-hidden />
                                </span>
                                <span className="text-[15px] font-semibold tracking-tight">README preview</span>
                            </span>
                            <ChevronDown className="h-4 w-4 text-subtle transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden />
                        </summary>
                        <div className="mt-4 pt-4 border-t border-line min-w-0 overflow-x-auto">
                            <Markdown>{data.readme_md}</Markdown>
                        </div>
                    </details>
                </Card>
            )}

            {pdfUrl && (
                <Card className="card-pad">
                    <CardHeader
                        title="Report preview"
                        subtitle={data.pdf_name || 'report.pdf'}
                        icon={FileText}
                        action={
                            <a href={pdfUrl} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
                                <ExternalLink className="h-4 w-4" aria-hidden /> Open
                            </a>
                        }
                    />
                    <iframe
                        src={pdfUrl}
                        title="PDF report preview"
                        className="hidden md:block w-full h-[75vh] rounded-xl border border-line bg-surface-2"
                    />
                    <p className="md:hidden text-sm text-muted">
                        PDF previews don't fit small screens. Use <span className="font-medium text-fg">Open</span> or download the report.
                    </p>
                </Card>
            )}

            <div className="flex flex-wrap gap-2">
                <Button variant="primary" icon={RotateCcw} onClick={onAgain}>Run another task</Button>
                <Button variant="ghost" icon={Trash2} onClick={onReset}>Start over with new files</Button>
            </div>
        </div>
    );
}

/** Task Studio: upload a project, describe the task, Gemini Pro returns the finished project + README + PDF report. */
export default function Studio() {
    const toast = useToast();
    const ids = { prompt: useId(), title: useId(), author: useId(), counter: useId(), size: useId() };
    const [items, setItems] = useState([]);
    const [skipped, setSkipped] = useState(0);
    const [dragging, setDragging] = useState(false);
    const [reading, setReading] = useState(false);
    const [prompt, setPrompt] = useState('');
    const [title, setTitle] = useState('');
    const [author, setAuthor] = useState('');
    const [maxMb, setMaxMb] = useState(DEFAULT_MAX_MB);
    const [phase, setPhase] = useState('idle'); // idle | running | done
    const [stage, setStage] = useState('upload');
    const [uploadPct, setUploadPct] = useState(0);
    const [downPct, setDownPct] = useState(null);
    const [elapsed, setElapsed] = useState(0);
    const [error, setError] = useState(null);
    const [result, setResult] = useState(null);

    const filesRef = useRef(null);
    const folderRef = useRef(null);
    const zipRef = useRef(null);
    const xhrRef = useRef(null);
    const startRef = useRef(0);
    const urlsRef = useRef([]);
    const resultRef = useRef(null);
    const dragDepth = useRef(0);

    const maxBytes = maxMb * 1024 * 1024;
    const total = items.reduce((s, it) => s + it.size, 0);
    const over = total > maxBytes;
    const running = phase === 'running';
    const canRun = items.length > 0 && prompt.trim().length > 0 && prompt.length <= PROMPT_MAX && !over && !running && !reading;

    useEffect(() => {
        api('/studio/info').then((r) => {
            const mb = Number(r?.data?.max_upload_mb);
            if (mb > 0) setMaxMb(mb);
        }).catch(() => { /* fall back to the default limit */ });
    }, []);

    const revokeUrls = useCallback(() => {
        urlsRef.current.forEach((u) => URL.revokeObjectURL(u));
        urlsRef.current = [];
    }, []);

    useEffect(() => () => {
        xhrRef.current?.abort();
        revokeUrls();
    }, [revokeUrls]);

    useEffect(() => {
        if (!running) return undefined;
        const t = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
        return () => clearInterval(t);
    }, [running]);

    const addFiles = useCallback((list, skippedCount = 0) => {
        if (skippedCount) setSkipped((n) => n + skippedCount);
        if (!list.length) return;
        setError(null);
        setItems((prev) => {
            const byPath = new Map(prev.map((it) => [it.path, it]));
            for (const { file, path } of list) byPath.set(path, { path, file, size: file.size });
            return [...byPath.values()];
        });
    }, []);

    const fromInput = (e) => {
        const picked = [...(e.target.files || [])];
        let skip = 0;
        const list = [];
        for (const file of picked) {
            const path = file.webkitRelativePath || file.name;
            if (isSkipped(path)) skip += 1;
            else list.push({ file, path });
        }
        addFiles(list, skip);
        e.target.value = '';
    };

    const onDrop = async (e) => {
        e.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        if (running) return;
        const dt = e.dataTransfer;
        // Entries must be grabbed synchronously; the DataTransfer is cleared after the event.
        const entries = [...(dt.items || [])].filter((i) => i.kind === 'file').map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
        if (!entries.length) {
            addFiles([...(dt.files || [])].map((file) => ({ file, path: file.name })));
            return;
        }
        setReading(true);
        try {
            const out = [];
            const skippedBox = { count: 0 };
            for (const entry of entries) await walkEntry(entry, out, skippedBox);
            addFiles(out, skippedBox.count);
        } catch {
            toast('Could not read some dropped items. Try "Choose folder" instead.', 'error');
        } finally {
            setReading(false);
        }
    };

    const dragProps = {
        onDragEnter: (e) => { e.preventDefault(); dragDepth.current += 1; if (!running) setDragging(true); },
        onDragOver: (e) => { e.preventDefault(); e.dataTransfer.dropEffect = running ? 'none' : 'copy'; },
        onDragLeave: () => { dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); },
        onDrop,
    };

    const removeOne = (path) => setItems((prev) => prev.filter((it) => it.path !== path));
    const clearAll = () => { setItems([]); setSkipped(0); };

    const fail = (message, status) => {
        setPhase('idle');
        setError({ message, status });
        xhrRef.current = null;
    };

    const run = () => {
        if (!canRun) return;
        setError(null);
        revokeUrls();
        setResult(null);

        const fd = new FormData();
        fd.append('prompt', prompt.trim());
        if (title.trim()) fd.append('title', title.trim());
        if (author.trim()) fd.append('author', author.trim());
        items.forEach((it) => fd.append('files', it.file, it.path));

        const xhr = new XMLHttpRequest();
        xhrRef.current = xhr;
        xhr.open('POST', '/api/studio/run');
        xhr.setRequestHeader('X-App-Key', getToken());
        xhr.responseType = 'text';
        xhr.upload.onprogress = (e) => { if (e.lengthComputable) setUploadPct(Math.round((100 * e.loaded) / e.total)); };
        xhr.upload.onload = () => { setUploadPct(100); setStage('working'); };
        xhr.onprogress = (e) => {
            setStage('receiving');
            setDownPct(e.lengthComputable ? Math.round((100 * e.loaded) / e.total) : null);
        };
        xhr.onerror = () => fail('Network error. Is the backend running?');
        xhr.ontimeout = () => fail('The request timed out. Try a smaller project or a more focused task.');
        xhr.onabort = () => { xhrRef.current = null; };
        xhr.onload = () => {
            xhrRef.current = null;
            if (xhr.status === 401) window.dispatchEvent(new CustomEvent('auth-required'));
            let body = null;
            try { body = JSON.parse(xhr.responseText); } catch { /* non-JSON */ }
            if (xhr.status === 413) {
                fail(`${body?.message ? `${body.message} ` : ''}The upload is over the ${maxMb} MB limit. Remove datasets, binaries, images or build output, or zip only the source files.`, 413);
                return;
            }
            if (xhr.status === 401) { fail('Locked. Enter your passcode and run it again.', 401); return; }
            if (xhr.status < 200 || xhr.status >= 300 || body?.status !== 'success' || !body?.data) {
                fail(body?.message || `Request failed (${xhr.status || 'no response'})`, xhr.status);
                return;
            }
            const data = body.data;
            let zipUrl = null;
            let pdfUrl = null;
            try {
                if (data.zip_b64) zipUrl = URL.createObjectURL(b64ToBlob(data.zip_b64, 'application/zip'));
                if (data.pdf_b64) pdfUrl = URL.createObjectURL(b64ToBlob(data.pdf_b64, 'application/pdf'));
            } catch {
                toast('Could not decode one of the returned files.', 'error');
            }
            urlsRef.current = [zipUrl, pdfUrl].filter(Boolean);
            // Drop the large base64 strings once they are blobs.
            setResult({ data: { ...data, zip_b64: undefined, pdf_b64: undefined }, zipUrl, pdfUrl });
            setPhase('done');
            toast('Task complete');
            requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start' }));
        };

        startRef.current = Date.now();
        setElapsed(0);
        setUploadPct(0);
        setDownPct(null);
        setStage('upload');
        setPhase('running');
        xhr.send(fd);
    };

    const cancel = () => {
        xhrRef.current?.abort();
        xhrRef.current = null;
        setPhase('idle');
        toast('Cancelled. Your files and prompt are still here.', 'info');
    };

    const again = () => {
        revokeUrls();
        setResult(null);
        setPhase('idle');
        window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' });
    };
    const startOver = () => {
        again();
        clearAll();
        setPrompt('');
        setError(null);
    };

    const pct = Math.min(100, (100 * total) / maxBytes);

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="animate-rise min-w-0">
                <h1 className="text-[28px] sm:text-3xl font-bold tracking-tight">Task Studio</h1>
                <p className="text-sm text-muted mt-1">Drop a project, describe the task, get back the finished work with a README and a PDF report.</p>
            </header>

            <Card className="card-pad animate-rise">
                <CardHeader title="Project" subtitle={`Files, a .zip or a whole folder · up to ${maxMb} MB`} icon={FolderCog} />
                <fieldset disabled={running} className="space-y-5 min-w-0 disabled:opacity-70">
                    <legend className="sr-only">Project files and task</legend>

                    <div
                        {...dragProps}
                        className={cx(
                            'rounded-2xl border-2 border-dashed px-4 py-7 sm:py-9 text-center transition-colors motion-reduce:transition-none',
                            dragging ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface-2/50',
                        )}
                    >
                        <div className="mx-auto grid place-items-center h-11 w-11 rounded-2xl bg-surface border border-line text-subtle mb-3">
                            {reading ? <Spinner className="h-5 w-5 motion-reduce:animate-none" /> : <Upload className="h-5 w-5" aria-hidden />}
                        </div>
                        <p className="text-sm font-medium">{reading ? 'Reading folder…' : dragging ? 'Drop to add' : 'Drag files, a .zip or a folder here'}</p>
                        <p className="text-xs text-subtle mt-1 max-w-md mx-auto">
                            Folder paths are kept. {SKIP_DIRS.join(', ')} are skipped. A single .zip is unpacked on the server.
                        </p>
                        <div className="mt-4 flex flex-wrap justify-center gap-2">
                            <Button size="sm" icon={Files} onClick={() => filesRef.current?.click()}>Choose files</Button>
                            <Button size="sm" icon={FolderOpen} onClick={() => folderRef.current?.click()}>Choose folder</Button>
                            <Button size="sm" icon={FileArchive} onClick={() => zipRef.current?.click()}>Choose .zip</Button>
                        </div>
                        <input ref={filesRef} type="file" multiple className="sr-only" tabIndex={-1} aria-hidden onChange={fromInput} />
                        <input ref={folderRef} type="file" multiple webkitdirectory="" directory="" className="sr-only" tabIndex={-1} aria-hidden onChange={fromInput} />
                        <input ref={zipRef} type="file" accept=".zip,application/zip,application/x-zip-compressed" className="sr-only" tabIndex={-1} aria-hidden onChange={fromInput} />
                    </div>

                    {(items.length > 0 || skipped > 0) && (
                        <div className="min-w-0">
                            <div className="flex items-center justify-between gap-3 mb-2">
                                <p className="text-sm font-medium tabular-nums">
                                    {items.length} file{items.length === 1 ? '' : 's'}
                                    {skipped > 0 && <span className="text-subtle font-normal"> · {skipped} skipped (build/dependency folders)</span>}
                                </p>
                                {items.length > 0 && <Button variant="ghost" size="sm" icon={Trash2} onClick={clearAll}>Clear all</Button>}
                            </div>
                            {items.length > 0 && (
                                <ul className="max-h-60 overflow-y-auto rounded-xl border border-line divide-y divide-line" aria-label="Selected files">
                                    {items.map((it) => (
                                        <li key={it.path} className="flex items-center gap-2 pl-3 pr-1 py-1 text-sm min-w-0">
                                            <span className="font-mono text-[12.5px] truncate flex-1 min-w-0" title={it.path}>{it.path}</span>
                                            <span className="text-xs text-subtle tabular-nums shrink-0">{fmtSize(it.size)}</span>
                                            <button
                                                type="button"
                                                onClick={() => removeOne(it.path)}
                                                className="btn btn-ghost btn-icon h-8 w-8 shrink-0"
                                                aria-label={`Remove ${it.path}`}
                                            >
                                                <X className="h-3.5 w-3.5" aria-hidden />
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            )}
                            <div className="mt-2.5" id={ids.size}>
                                <div className="flex items-center justify-between text-xs tabular-nums mb-1">
                                    <span className={over ? 'text-danger font-medium' : 'text-muted'}>{fmtSize(total)} of {maxMb} MB</span>
                                    <span className="text-subtle">{Math.round((100 * total) / maxBytes)}%</span>
                                </div>
                                <ProgressBar value={pct} color={over ? 'var(--danger)' : pct > 85 ? 'var(--medium)' : 'var(--accent)'} />
                                {over && (
                                    <p className="mt-2 text-xs text-danger flex items-start gap-1.5" role="alert">
                                        <CircleAlert className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden />
                                        Over the {maxMb} MB limit. Remove datasets, binaries, images or build output, or zip only the source files.
                                    </p>
                                )}
                            </div>
                        </div>
                    )}

                    <div>
                        <label htmlFor={ids.prompt} className="label">Task <span className="text-danger" aria-hidden>*</span></label>
                        <textarea
                            id={ids.prompt}
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value.slice(0, PROMPT_MAX))}
                            rows={5}
                            required
                            aria-describedby={ids.counter}
                            placeholder="e.g. Complete this lab: implement the missing functions and add tests"
                            className="input h-auto min-h-32 py-2.5 leading-relaxed resize-y"
                        />
                        <div className="mt-1.5 flex flex-wrap items-start justify-between gap-2">
                            <div className="flex flex-wrap gap-1.5 min-w-0" aria-label="Example tasks">
                                {EXAMPLES.map((ex) => (
                                    <button
                                        key={ex}
                                        type="button"
                                        onClick={() => setPrompt(ex)}
                                        className={cx('chip max-w-full focus-visible:outline-2 focus-visible:outline-accent', prompt === ex && 'chip-on')}
                                        title={ex}
                                    >
                                        <span className="truncate">{ex}</span>
                                    </button>
                                ))}
                            </div>
                            <span id={ids.counter} className={cx('text-xs tabular-nums ml-auto', prompt.length > PROMPT_MAX * 0.9 ? 'text-medium' : 'text-subtle')}>
                                {prompt.length}/{PROMPT_MAX}
                            </span>
                        </div>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                            <label htmlFor={ids.title} className="label">Report title <span className="text-subtle font-normal">(optional)</span></label>
                            <input id={ids.title} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className="input" placeholder="e.g. Lab 4: Linked lists" />
                        </div>
                        <div>
                            <label htmlFor={ids.author} className="label">Your name <span className="text-subtle font-normal">(for the report)</span></label>
                            <input id={ids.author} value={author} onChange={(e) => setAuthor(e.target.value)} maxLength={120} className="input" autoComplete="name" />
                        </div>
                    </div>
                </fieldset>

                <div className="mt-5 flex flex-wrap items-center gap-3">
                    {running ? (
                        <Button variant="secondary" icon={X} onClick={cancel}>Cancel</Button>
                    ) : (
                        <Button variant="primary" size="lg" icon={Bot} disabled={!canRun} onClick={run}>Run with Gemini Pro</Button>
                    )}
                    {!running && !canRun && (
                        <span className="text-xs text-subtle">
                            {!items.length ? 'Add your project files first.' : !prompt.trim() ? 'Describe the task.' : over ? 'Reduce the upload size.' : ''}
                        </span>
                    )}
                </div>

                {error && (
                    <div role="alert" className="mt-4 flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-3 text-sm">
                        <CircleAlert className="h-4 w-4 mt-0.5 text-danger shrink-0" aria-hidden />
                        <div className="min-w-0 flex-1">
                            <p className="font-medium text-danger">{error.status === 413 ? 'Upload too large' : 'Task failed'}</p>
                            <p className="text-fg mt-0.5 wrap-break-word">{error.message}</p>
                        </div>
                        <button type="button" onClick={() => setError(null)} className="btn btn-ghost btn-icon h-7 w-7 -mr-1.5 -mt-1 shrink-0" aria-label="Dismiss error">
                            <X className="h-3.5 w-3.5" aria-hidden />
                        </button>
                    </div>
                )}
            </Card>

            {running && (
                <Card className="card-pad animate-rise" aria-live="polite" aria-busy="true">
                    <CardHeader title="Working on it" subtitle="Keep this tab open until it finishes" icon={Play} />
                    <Steps stage={stage} uploadPct={uploadPct} downPct={downPct} elapsed={elapsed} />
                </Card>
            )}

            <div ref={resultRef} className="scroll-mt-20">
                {phase === 'done' && result && <Result result={result} onAgain={again} onReset={startOver} />}
            </div>
        </div>
    );
}
