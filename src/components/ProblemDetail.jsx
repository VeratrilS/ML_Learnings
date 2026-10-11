import { useEffect, useState } from 'react';
import { ExternalLink, BookOpen, CirclePlay, Lightbulb, Eye, Copy, Check, Wand2, RotateCcw, Clock, HardDrive, AlertTriangle, Link2 } from 'lucide-react';
import { api } from '../lib/api';
import { timeAgo } from '../lib/hooks';
import { Button, DifficultyBadge, Sheet, Skeleton, Spinner, useToast, cx } from './ui';

function Section({ title, icon: Icon, children }) {
    return (
        <section className="mt-6">
            <h3 className="eyebrow flex items-center gap-1.5 mb-2.5">{Icon && <Icon className="h-3.5 w-3.5" />}{title}</h3>
            {children}
        </section>
    );
}

function CodeBlock({ code }) {
    const [copied, setCopied] = useState(false);
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch { /* clipboard blocked */ }
    };
    return (
        <div className="relative rounded-xl border border-line bg-surface-2 overflow-hidden">
            <div className="flex items-center justify-between px-3 h-9 border-b border-line text-xs text-subtle">
                <span className="font-mono font-medium">C++</span>
                <button onClick={copy} className="btn btn-ghost btn-sm h-7">
                    {copied ? <><Check className="h-3.5 w-3.5 text-ok" /> Copied</> : <><Copy className="h-3.5 w-3.5" /> Copy</>}
                </button>
            </div>
            <pre className="p-3.5 overflow-x-auto text-[12.5px] leading-relaxed font-mono"><code>{code}</code></pre>
        </div>
    );
}

export default function ProblemDetail({ id, onClose, onToggle }) {
    const [log, setLog] = useState(null);
    const [error, setError] = useState(null);
    const [hints, setHints] = useState(0);
    const [showSolution, setShowSolution] = useState(false);
    const [generating, setGenerating] = useState(false);
    const toast = useToast();

    useEffect(() => {
        if (!id) return;
        setLog(null); setError(null); setHints(0); setShowSolution(false);
        api(`/logs/${id}`).then((r) => setLog(r.data)).catch((e) => setError(e.message));
    }, [id]);

    const generate = async () => {
        setGenerating(true);
        try {
            const r = await api(`/logs/${id}/writeup`, { method: 'POST' });
            setLog(r.data);
            toast('Write-up ready');
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setGenerating(false);
        }
    };

    const toggleSolved = async () => {
        const next = !log.is_completed;
        setLog({ ...log, is_completed: next });
        await onToggle(log, next);
    };

    const w = log?.writeup;
    const links = log?.links || (log?.link ? { leetcode: log.link } : {});

    return (
        <Sheet open={!!id} onClose={onClose} wide>
            <div className="p-5 sm:p-7 pt-3 sm:pt-7">
                {error && <p className="text-sm text-danger">{error}</p>}
                {!log && !error && (
                    <div className="space-y-3 pt-4"><Skeleton className="h-7 w-2/3" /><Skeleton className="h-5 w-40" /><Skeleton className="h-32 w-full" /></div>
                )}
                {log && (
                    <>
                        <div className="pr-10">
                            <div className="flex flex-wrap items-center gap-1.5 mb-2">
                                <DifficultyBadge value={log.difficulty} />
                                {log.topic && <span className="badge bg-surface-2 text-muted">{log.topic}</span>}
                                {w?.pattern && <span className="badge bg-accent-soft text-accent">{w.pattern}</span>}
                            </div>
                            <h2 className="text-xl sm:text-2xl font-bold tracking-tight">{log.title}</h2>
                            <p className="text-xs text-subtle mt-1">Sent {timeAgo(log.timestamp)}{log.completed_at && ` · solved ${timeAgo(log.completed_at)}`}</p>
                        </div>

                        <div className="flex flex-wrap gap-2 mt-5">
                            {links.leetcode && (
                                <a href={links.leetcode} target="_blank" rel="noreferrer" className="btn btn-primary">
                                    Solve on LeetCode <ExternalLink className="h-3.5 w-3.5" />
                                </a>
                            )}
                            <button onClick={toggleSolved} className={cx('btn', log.is_completed ? 'btn-secondary text-ok' : 'btn-secondary')}>
                                <Check className="h-4 w-4" strokeWidth={log.is_completed ? 3 : 2} /> {log.is_completed ? 'Solved' : 'Mark solved'}
                            </button>
                            {links.editorial && <a href={links.editorial} target="_blank" rel="noreferrer" className="btn btn-ghost"><BookOpen className="h-4 w-4" /> Editorial</a>}
                            {links.video && <a href={links.video} target="_blank" rel="noreferrer" className="btn btn-ghost"><CirclePlay className="h-4 w-4" /> Video</a>}
                        </div>

                        {!w?.cpp_code && (
                            <div className="mt-6 rounded-2xl border border-dashed border-line-strong p-5 text-center">
                                {w?.statement && <p className="text-sm text-muted text-left mb-4 whitespace-pre-wrap">{w.statement}</p>}
                                <p className="text-sm font-medium">No AI write-up yet</p>
                                <p className="text-xs text-subtle mt-1">Hints, intuition, approach and an optimal C++ solution.</p>
                                <Button variant="primary" icon={Wand2} loading={generating} onClick={generate} className="mt-4">
                                    {generating ? 'Writing… (up to a minute)' : 'Generate write-up'}
                                </Button>
                            </div>
                        )}

                        {w?.cpp_code && (
                            <>
                                {w.statement && (
                                    <Section title="Problem">
                                        <p className="text-[14.5px] leading-relaxed whitespace-pre-wrap">{w.statement}</p>
                                    </Section>
                                )}

                                {!!w.hints?.length && (
                                    <Section title="Hints" icon={Lightbulb}>
                                        <ol className="space-y-2">
                                            {w.hints.slice(0, hints).map((h, i) => (
                                                <li key={i} className="animate-rise flex gap-2.5 rounded-xl bg-surface-2 border border-line p-3 text-sm">
                                                    <span className="font-mono text-accent font-semibold">{i + 1}</span><span>{h}</span>
                                                </li>
                                            ))}
                                        </ol>
                                        {hints < w.hints.length && (
                                            <Button size="sm" variant="secondary" icon={Lightbulb} onClick={() => setHints(hints + 1)} className={hints ? 'mt-2' : ''}>
                                                Reveal hint {hints + 1} of {w.hints.length}
                                            </Button>
                                        )}
                                    </Section>
                                )}

                                {!showSolution ? (
                                    <div className="mt-7 rounded-2xl border border-line bg-surface-2/50 p-5 text-center">
                                        <p className="text-sm text-muted">Give it an honest try first. When you're ready:</p>
                                        <Button variant="secondary" icon={Eye} onClick={() => setShowSolution(true)} className="mt-3">Show solution</Button>
                                    </div>
                                ) : (
                                    <div className="animate-rise">
                                        {w.brute_force && (
                                            <Section title="Brute force"><p className="text-sm text-muted leading-relaxed">{w.brute_force}</p></Section>
                                        )}
                                        {w.intuition && (
                                            <Section title="Intuition"><p className="text-[14.5px] leading-relaxed">{w.intuition}</p></Section>
                                        )}
                                        {!!w.approach?.length && (
                                            <Section title="Optimal approach">
                                                <ol className="space-y-2">
                                                    {w.approach.map((s, i) => (
                                                        <li key={i} className="flex gap-3 text-[14.5px] leading-relaxed">
                                                            <span className="grid place-items-center h-6 w-6 shrink-0 rounded-full bg-surface-2 border border-line text-xs font-semibold">{i + 1}</span>
                                                            <span className="pt-0.5">{s}</span>
                                                        </li>
                                                    ))}
                                                </ol>
                                            </Section>
                                        )}
                                        {(w.time_complexity || w.space_complexity) && (
                                            <div className="grid grid-cols-2 gap-3 mt-6">
                                                <div className="rounded-xl border border-line p-3">
                                                    <div className="eyebrow flex items-center gap-1"><Clock className="h-3 w-3" /> Time</div>
                                                    <div className="font-mono font-semibold mt-1">{w.time_complexity}</div>
                                                </div>
                                                <div className="rounded-xl border border-line p-3">
                                                    <div className="eyebrow flex items-center gap-1"><HardDrive className="h-3 w-3" /> Space</div>
                                                    <div className="font-mono font-semibold mt-1">{w.space_complexity}</div>
                                                </div>
                                            </div>
                                        )}
                                        {!!w.edge_cases?.length && (
                                            <Section title="Edge cases" icon={AlertTriangle}>
                                                <ul className="space-y-1.5 text-sm list-disc pl-5 marker:text-subtle">
                                                    {w.edge_cases.map((e, i) => <li key={i}>{e}</li>)}
                                                </ul>
                                            </Section>
                                        )}
                                        <Section title="Solution"><CodeBlock code={w.cpp_code} /></Section>
                                    </div>
                                )}

                                {!!w.related?.length && (
                                    <Section title="Practice next" icon={Link2}>
                                        <div className="flex flex-wrap gap-2">
                                            {w.related.map((r) => (
                                                <a key={r} href={`https://leetcode.com/problemset/?search=${encodeURIComponent(r)}`} target="_blank" rel="noreferrer" className="chip">
                                                    {r} <ExternalLink className="h-3 w-3" />
                                                </a>
                                            ))}
                                        </div>
                                    </Section>
                                )}

                                <div className="mt-8 pt-4 border-t border-line flex justify-end">
                                    <button className="btn btn-ghost btn-sm" onClick={generate} disabled={generating}>
                                        {generating ? <Spinner /> : <RotateCcw className="h-3.5 w-3.5" />} Regenerate write-up
                                    </button>
                                </div>
                            </>
                        )}
                    </>
                )}
            </div>
        </Sheet>
    );
}
