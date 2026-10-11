import { useRef, useState } from 'react';
import { ScanSearch, Bug, FlaskConical, Sparkles, Clock, HardDrive, RotateCcw, CheckCircle2, XCircle, GraduationCap } from 'lucide-react';
import { api } from '../lib/api';
import { Button, cx } from './ui';

const LANGS = [
    { value: 'cpp', label: 'C++' },
    { value: 'java', label: 'Java' },
    { value: 'python', label: 'Python' },
];
const INDENT = '    ';
const VERDICT = {
    correct: 'bg-ok/10 text-ok',
    'likely correct': 'bg-ok/10 text-ok',
    buggy: 'bg-medium/10 text-medium',
    'wrong approach': 'bg-danger/10 text-danger',
};
const GRADE = { again: 'text-danger', hard: 'text-medium', good: 'text-ok', easy: 'text-accent' };

const draftKey = (id) => `tutor:code:${id}`;
function loadDraft(id) {
    try { return JSON.parse(localStorage.getItem(draftKey(id))) || {}; } catch { return {}; }
}
function saveDraft(id, draft) {
    try { localStorage.setItem(draftKey(id), JSON.stringify(draft)); } catch { /* storage unavailable */ }
}

function Block({ title, icon: Icon, children }) {
    return (
        <div className="mt-4">
            <h4 className="eyebrow flex items-center gap-1.5 mb-2"><Icon className="h-3.5 w-3.5" />{title}</h4>
            {children}
        </div>
    );
}

function ReviewResult({ r, onRerun, loading }) {
    return (
        <div className="card card-pad mt-5 animate-rise">
            <div className="flex flex-wrap items-center gap-2">
                <span className={cx('badge text-[12px] capitalize', VERDICT[r.verdict] || 'bg-surface-2 text-muted')}>{r.verdict}</span>
                <span className={cx('badge', r.matches_optimal ? 'bg-ok/10 text-ok' : 'bg-medium/10 text-medium')}>
                    {r.matches_optimal ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                    {r.matches_optimal ? 'Optimal' : 'Not optimal'}
                </span>
                <span className="ml-auto flex items-center gap-1.5 text-xs text-subtle">
                    {r.cached && 'cached'}
                    <button className="btn btn-ghost btn-sm h-7" onClick={onRerun} disabled={loading} title="Review again without cache">
                        <RotateCcw className="h-3.5 w-3.5" /> Re-run
                    </button>
                </span>
            </div>
            {r.summary && <p className="text-[14.5px] leading-relaxed mt-3">{r.summary}</p>}

            <div className="grid grid-cols-3 gap-2.5 mt-4">
                <div className="rounded-xl border border-line p-2.5">
                    <div className="eyebrow flex items-center gap-1"><Clock className="h-3 w-3" /> Time</div>
                    <div className="font-mono font-semibold text-sm mt-1 break-words">{r.time || '?'}</div>
                </div>
                <div className="rounded-xl border border-line p-2.5">
                    <div className="eyebrow flex items-center gap-1"><HardDrive className="h-3 w-3" /> Space</div>
                    <div className="font-mono font-semibold text-sm mt-1 break-words">{r.space || '?'}</div>
                </div>
                <div className="rounded-xl border border-line p-2.5">
                    <div className="eyebrow flex items-center gap-1"><GraduationCap className="h-3 w-3" /> Grade</div>
                    <div className={cx('font-semibold text-sm mt-1 capitalize', GRADE[r.suggested_grade])}>{r.suggested_grade}</div>
                </div>
            </div>

            {!!r.bugs?.length && (
                <Block title="Bugs" icon={Bug}>
                    <ul className="space-y-1.5">
                        {r.bugs.map((b, i) => (
                            <li key={i} className="flex gap-2.5 text-sm">
                                <span className="badge bg-danger/10 text-danger font-mono shrink-0 h-5">{b.line ? `L${b.line}` : '—'}</span>
                                <span className="leading-relaxed">{b.issue}</span>
                            </li>
                        ))}
                    </ul>
                </Block>
            )}

            {!!r.failing_cases?.length && (
                <Block title="Failing cases" icon={FlaskConical}>
                    <div className="space-y-2">
                        {r.failing_cases.map((c, i) => (
                            <div key={i} className="rounded-xl bg-surface-2 border border-line p-3 text-sm">
                                <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                                    <span className="text-subtle text-xs pt-0.5">Input</span><code className="font-mono text-[12.5px] break-all">{c.input}</code>
                                    {c.expected && <><span className="text-subtle text-xs pt-0.5">Expected</span><code className="font-mono text-[12.5px] break-all">{c.expected}</code></>}
                                </div>
                                {c.why && <p className="text-muted mt-2 leading-relaxed">{c.why}</p>}
                            </div>
                        ))}
                    </div>
                </Block>
            )}

            {!!r.cleanups?.length && (
                <Block title="Cleanups" icon={Sparkles}>
                    <ul className="space-y-1.5 text-sm list-disc pl-5 marker:text-subtle">
                        {r.cleanups.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                </Block>
            )}

            {!r.bugs?.length && !r.failing_cases?.length && (
                <p className="mt-4 flex items-center gap-1.5 text-sm text-ok"><CheckCircle2 className="h-4 w-4" /> No bugs found.</p>
            )}
        </div>
    );
}

export default function CodeReview({ logId }) {
    const [draft] = useState(() => loadDraft(logId));
    const [language, setLanguage] = useState(draft.language || 'cpp');
    const [code, setCode] = useState(draft.code || '');
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(false);
    const ref = useRef(null);

    const update = (next) => {
        setCode(next.code ?? code);
        setLanguage(next.language ?? language);
        saveDraft(logId, { code, language, ...next });
    };

    const review = async (fresh = false) => {
        if (!code.trim() || loading) return;
        setLoading(true); setError(null);
        try {
            const { data } = await api(`/tutor/${logId}/review`, { method: 'POST', body: { code, language, fresh } });
            setResult(data);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    // Tab / Shift+Tab indent with spaces; Ctrl/Cmd+Enter submits.
    const onKeyDown = (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            review();
            return;
        }
        if (e.key !== 'Tab') return;
        e.preventDefault();
        const el = e.target;
        const { selectionStart: s, selectionEnd: end, value } = el;
        let next, caretStart, caretEnd;
        if (!e.shiftKey && s === end) {
            next = value.slice(0, s) + INDENT + value.slice(end);
            caretStart = caretEnd = s + INDENT.length;
        } else {
            const lineStart = value.lastIndexOf('\n', s - 1) + 1;
            const block = value.slice(lineStart, end);
            const lines = block.split('\n');
            const changed = e.shiftKey
                ? lines.map((l) => l.replace(new RegExp(`^ {1,${INDENT.length}}`), ''))
                : lines.map((l) => INDENT + l);
            const firstDelta = changed[0].length - lines[0].length;
            next = value.slice(0, lineStart) + changed.join('\n') + value.slice(end);
            caretStart = Math.max(lineStart, s + firstDelta);
            caretEnd = end + (changed.join('\n').length - block.length);
        }
        update({ code: next });
        requestAnimationFrame(() => {
            if (ref.current) ref.current.setSelectionRange(caretStart, caretEnd);
        });
    };

    const lineCount = code ? code.split('\n').length : 0;

    return (
        <div className="mt-5">
            <div className="rounded-2xl border border-line bg-surface-2 overflow-hidden focus-within:border-accent/60 transition-colors">
                <div className="flex items-center justify-between gap-2 px-2.5 h-10 border-b border-line">
                    <select
                        value={language}
                        onChange={(e) => update({ language: e.target.value })}
                        className="input h-7 py-0 text-xs w-auto font-mono"
                        aria-label="Language"
                    >
                        {LANGS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                    </select>
                    <span className="text-[11px] text-subtle">{lineCount ? `${lineCount} lines · ` : ''}Tab indents · Ctrl+Enter reviews</span>
                </div>
                <textarea
                    ref={ref}
                    value={code}
                    onChange={(e) => update({ code: e.target.value })}
                    onKeyDown={onKeyDown}
                    spellCheck={false}
                    autoCapitalize="off"
                    autoCorrect="off"
                    maxLength={20000}
                    rows={14}
                    placeholder="Paste or write your solution here…"
                    className="block w-full resize-y bg-transparent p-3.5 font-mono text-[12.5px] leading-relaxed outline-none placeholder:text-subtle [tab-size:4]"
                />
            </div>

            <div className="flex items-center justify-between gap-3 mt-3">
                <p className="text-xs text-subtle">Checked against the optimal solution. Identical code is cached.</p>
                <Button variant="primary" icon={ScanSearch} loading={loading} disabled={!code.trim()} onClick={() => review()}>
                    {loading ? 'Reviewing…' : 'Review code'}
                </Button>
            </div>

            {error && <p className="mt-3 text-sm text-danger">{error}</p>}
            {result && <ReviewResult r={result} loading={loading} onRerun={() => review(true)} />}
        </div>
    );
}
