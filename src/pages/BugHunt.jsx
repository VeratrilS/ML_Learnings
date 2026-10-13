import { useEffect, useRef, useState } from 'react';
import {
    Bug, AlertTriangle, ShieldAlert, CheckCircle2, Clock,
    Crosshair, Sparkles, ChevronRight, RotateCcw, Award, ArrowRight
} from 'lucide-react';
import { Button, Card, ProgressBar, Skeleton, useToast, cx } from '../components/ui';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

export default function BugHunt() {
    const toast = useToast();
    const casesRes = useApi('/bughunt/cases');
    const statsRes = useApi('/bughunt/stats');

    const cases = casesRes.data?.cases || [];
    const stats = statsRes.data?.stats || { total_attempts: 0, solved_cases: 0, total_cases: 5, total_xp: 0, rank: 'Trainee Detective' };

    const [selectedCaseId, setSelectedCaseId] = useState(null);
    const [activeCaseData, setActiveCaseData] = useState(null);
    const [selectedLine, setSelectedLine] = useState(null);
    const [selectedPatch, setSelectedPatch] = useState(null);
    const [triageResult, setTriageResult] = useState(null);
    const [timerSec, setTimerSec] = useState(0);
    const [submitting, setSubmitting] = useState(false);
    const timerRef = useRef(null);

    // Auto-select first case
    useEffect(() => {
        if (!selectedCaseId && cases.length > 0) {
            handleOpenCase(cases[0].id);
        }
    }, [cases, selectedCaseId]);

    const handleOpenCase = async (id) => {
        setSelectedCaseId(id);
        setSelectedLine(null);
        setSelectedPatch(null);
        setTriageResult(null);
        setTimerSec(0);

        try {
            const res = await api(`/bughunt/case/${id}`);
            setActiveCaseData(res.data.case);
            if (timerRef.current) clearInterval(timerRef.current);
            timerRef.current = setInterval(() => {
                setTimerSec((prev) => prev + 1);
            }, 1000);
        } catch (err) {
            toast.error('Failed to load forensic case', err.message);
        }
    };

    const handleTriageSubmit = async () => {
        if (!selectedCaseId || submitting) return;
        if (!selectedLine) {
            toast.error('Select Suspect Line', 'Click on the code line you believe contains the vulnerability.');
            return;
        }
        if (!selectedPatch) {
            toast.error('Select Patch', 'Choose one of the 4 remediation patch options.');
            return;
        }

        setSubmitting(true);
        if (timerRef.current) clearInterval(timerRef.current);

        try {
            const res = await api(`/bughunt/case/${selectedCaseId}/triage`, {
                method: 'POST',
                body: {
                    line: selectedLine,
                    patch: selectedPatch,
                    time_taken_sec: timerSec,
                },
            });
            const data = res.data;
            setTriageResult(data);
            if (data.solved) {
                toast.success('Bounty Claimed!', `Case solved! +${data.xp_awarded} XP awarded.`);
            } else {
                toast.error('Triage Inaccurate', `Remediation failed. Received +${data.xp_awarded} partial research XP.`);
            }
            casesRes.reload();
            statsRes.reload();
        } catch (err) {
            toast.error('Submission failed', err.message);
        } finally {
            setSubmitting(false);
        }
    };

    const codeLines = (activeCaseData?.code || '').split('\n');

    return (
        <div className="space-y-6 animate-fade-in max-w-6xl mx-auto pb-12">
            {/* Header Banner */}
            <div className="relative overflow-hidden rounded-3xl border border-line bg-surface/80 p-6 md:p-8 backdrop-blur-xl shadow-2xl">
                <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-rose-500/10 rounded-full blur-3xl pointer-events-none" />
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20 mb-3">
                            <ShieldAlert className="w-3.5 h-3.5" /> Production Code Autopsy
                        </div>
                        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-fg flex items-center gap-3">
                            Bug Hunt
                        </h1>
                        <p className="text-sm md:text-base text-subtle mt-2 max-w-xl">
                            Forensic code autopsy of notorious FAANG post-mortems. Triage the fatal line, pick the correct patch, and neutralize production disasters.
                        </p>
                    </div>

                    {/* Stats pills */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-surface-2/60 p-3 rounded-2xl border border-line">
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Rank</div>
                            <div className="text-xs font-black text-amber-500 truncate mt-0.5">{stats.rank}</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Cases Solved</div>
                            <div className="text-lg font-black text-emerald-500">{stats.solved_cases}/{stats.total_cases}</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Attempts</div>
                            <div className="text-lg font-black text-fg">{stats.total_attempts}</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Bounty XP</div>
                            <div className="text-lg font-black text-accent">+{stats.total_xp}</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Interactive Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Case Dossier Selector Column */}
                <div className="space-y-3">
                    <h2 className="text-sm font-bold text-subtle uppercase tracking-wider px-1">Case Dossiers</h2>
                    <div className="space-y-2.5">
                        {cases.map((c) => {
                            const isSel = selectedCaseId === c.id;
                            return (
                                <button
                                    key={c.id}
                                    type="button"
                                    onClick={() => handleOpenCase(c.id)}
                                    className={cx(
                                        'w-full text-left p-3.5 rounded-2xl border transition-all relative overflow-hidden',
                                        isSel
                                            ? 'bg-rose-500/10 border-rose-500/50 shadow-md shadow-rose-500/5'
                                            : 'bg-surface hover:bg-surface-2 border-line'
                                    )}
                                >
                                    <div className="flex items-center justify-between gap-2 mb-1">
                                        <span className={cx(
                                            'text-[10px] font-bold px-2 py-0.5 rounded-full uppercase',
                                            c.severity === 'Critical' ? 'bg-rose-500/20 text-rose-500' :
                                            c.severity === 'High' ? 'bg-amber-500/20 text-amber-500' : 'bg-blue-500/20 text-blue-500'
                                        )}>
                                            {c.severity}
                                        </span>
                                        <span className="text-xs font-mono font-bold text-accent">+{c.bounty_xp} XP</span>
                                    </div>
                                    <h3 className="font-bold text-fg text-sm">{c.title}</h3>
                                    <p className="text-xs text-subtle line-clamp-1 mt-0.5">{c.summary}</p>
                                    {c.solved && (
                                        <div className="mt-2 inline-flex items-center gap-1 text-[11px] text-emerald-500 font-semibold">
                                            <CheckCircle2 className="w-3 h-3" /> Solved
                                        </div>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Autopsy Examination Chamber */}
                <div className="lg:col-span-2 space-y-4">
                    {activeCaseData ? (
                        <div className="space-y-4 animate-rise">
                            {/* Case Context Header */}
                            <Card className="p-5 border-line bg-surface space-y-3">
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <span className="text-xs font-mono text-rose-500 uppercase font-semibold">{activeCaseData.category}</span>
                                        <h2 className="text-xl font-extrabold text-fg">{activeCaseData.title}</h2>
                                    </div>
                                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-surface-2 border border-line font-mono text-xs font-bold text-fg">
                                        <Clock className="w-3.5 h-3.5 text-subtle" />
                                        <span>{Math.floor(timerSec / 60)}:{(timerSec % 60).toString().padStart(2, '0')}</span>
                                    </div>
                                </div>
                                <p className="text-xs text-subtle bg-surface-2/60 p-3 rounded-xl border border-line">
                                    <b>Incident Brief:</b> {activeCaseData.summary}
                                </p>
                            </Card>

                            {/* Code Terminal with Clickable Suspect Lines */}
                            <div className="rounded-2xl border border-line bg-black/90 p-4 font-mono text-xs overflow-x-auto shadow-xl">
                                <div className="text-[11px] text-zinc-500 pb-2 mb-2 border-b border-zinc-800 flex items-center justify-between">
                                    <span>// Click a suspect line number to flag it</span>
                                    {selectedLine && <span className="text-rose-400 font-bold">Flagged: Line {selectedLine}</span>}
                                </div>
                                <div className="space-y-1">
                                    {codeLines.map((lineText, idx) => {
                                        const lineNum = idx + 1;
                                        const isFlagged = selectedLine === lineNum;
                                        const isActualBug = triageResult && triageResult.actual_bug_line === lineNum;

                                        return (
                                            <div
                                                key={idx}
                                                onClick={() => !triageResult && setSelectedLine(lineNum)}
                                                className={cx(
                                                    'px-2 py-1 rounded cursor-pointer transition-colors flex items-center gap-3',
                                                    isActualBug ? 'bg-rose-500/30 text-rose-300 font-bold' :
                                                    isFlagged ? 'bg-amber-500/25 text-amber-300' : 'hover:bg-zinc-800/80 text-zinc-300'
                                                )}
                                            >
                                                <span className="text-zinc-600 select-none w-6 text-right">{lineNum}</span>
                                                <span className="flex-1 whitespace-pre">{lineText.replace(/^\d+:\s*/, '')}</span>
                                                {isFlagged && <Crosshair className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                                                {isActualBug && <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Patch Options Selection */}
                            <div className="space-y-2">
                                <div className="text-xs font-bold text-subtle uppercase tracking-wider">Select Remediation Patch</div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                                    {activeCaseData.options.map((opt) => {
                                        const isSel = selectedPatch === opt.id;
                                        const isCorrectOpt = triageResult && triageResult.actual_patch === opt.id;

                                        return (
                                            <button
                                                key={opt.id}
                                                type="button"
                                                onClick={() => !triageResult && setSelectedPatch(opt.id)}
                                                className={cx(
                                                    'p-3.5 rounded-2xl border text-left font-mono text-xs transition-all relative',
                                                    isCorrectOpt ? 'bg-emerald-500/15 border-emerald-500 text-emerald-400' :
                                                    isSel ? 'bg-accent/15 border-accent text-accent' : 'bg-surface hover:bg-surface-2 border-line text-fg'
                                                )}
                                            >
                                                <div className="font-bold mb-1 flex items-center justify-between">
                                                    <span>Patch {opt.id}</span>
                                                    {isCorrectOpt && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                                                </div>
                                                <div className="text-zinc-300 whitespace-pre-wrap">{opt.code}</div>
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Submit Button or Autopsy Post-Mortem Card */}
                            {!triageResult ? (
                                <Button
                                    className="w-full btn-primary py-3 gap-2 text-sm font-bold shadow-lg shadow-rose-500/10"
                                    onClick={handleTriageSubmit}
                                    disabled={submitting || !selectedLine || !selectedPatch}
                                >
                                    <Bug className="w-4 h-4" /> {submitting ? 'Submitting Forensic Report...' : 'Submit Triage Diagnostic'}
                                </Button>
                            ) : (
                                <Card className={cx(
                                    'p-5 border space-y-3 animate-rise',
                                    triageResult.solved ? 'bg-emerald-500/5 border-emerald-500/40' : 'bg-rose-500/5 border-rose-500/40'
                                )}>
                                    <div className="flex items-center justify-between">
                                        <h3 className="font-bold text-base text-fg flex items-center gap-2">
                                            {triageResult.solved ? '🎯 Triage Successful!' : '⚠️ Incomplete Diagnostic'}
                                        </h3>
                                        <span className="font-mono text-xs font-bold text-accent">+{triageResult.xp_awarded} XP</span>
                                    </div>
                                    <div className="text-xs text-subtle space-y-1.5">
                                        <p><b>Root Cause:</b> {triageResult.bug_explanation}</p>
                                        <p><b>Post-Mortem History:</b> {triageResult.post_mortem}</p>
                                    </div>
                                    <Button
                                        className="btn-secondary w-full text-xs font-bold mt-2"
                                        onClick={() => {
                                            setTriageResult(null);
                                            setSelectedLine(null);
                                            setSelectedPatch(null);
                                        }}
                                    >
                                        <RotateCcw className="w-3.5 h-3.5" /> Re-examine Case
                                    </Button>
                                </Card>
                            )}
                        </div>
                    ) : (
                        <Skeleton className="h-96 rounded-3xl" />
                    )}
                </div>
            </div>
        </div>
    );
}
