import { useState } from 'react';
import {
    FileCheck, Sparkles, CheckCircle2, AlertTriangle, Copy, Check,
    Zap, ArrowRight, ShieldCheck, Flame, RefreshCw, Layers
} from 'lucide-react';
import { api } from '../lib/api';
import { Card, CardHeader, cx, useToast } from '../components/ui';

const SAMPLE_BULLETS = [
    {
        label: 'Weak Bullet (Unquantified)',
        role: 'Backend Engineer',
        text: 'Worked on backend REST API to make it faster and helped team fix production bugs.',
    },
    {
        label: 'Average College Project',
        role: 'Full-Stack Developer',
        text: 'Created an e-commerce website using React, Node.js and MongoDB with user authentication and payment gateway.',
    },
    {
        label: 'ML / AI Project',
        role: 'ML Engineer',
        text: 'Trained CNN and transformer models on image datasets and improved accuracy.',
    },
];

const ROLES = [
    'Backend Engineer',
    'Full-Stack Developer',
    'Distributed Systems SDE',
    'ML / AI Engineer',
];

export default function ATS() {
    const toast = useToast();
    const [bullet, setBullet] = useState(SAMPLE_BULLETS[0].text);
    const [targetRole, setTargetRole] = useState(SAMPLE_BULLETS[0].role);
    const [analyzing, setAnalyzing] = useState(false);
    const [result, setResult] = useState(null);
    const [copiedIdx, setCopiedIdx] = useState(null);

    const runAnalysis = async (textToAnalyze, role) => {
        const queryText = textToAnalyze !== undefined ? textToAnalyze : bullet;
        const currentRole = role !== undefined ? role : targetRole;
        if (!queryText.trim()) return;

        setAnalyzing(true);
        try {
            const res = await api('/century/ats/analyze', {
                method: 'POST',
                body: { bullet: queryText, target_role: currentRole },
            });
            if (res && res.success) {
                setResult(res);
                // Trigger action for century state
                api('/century/action/ats_scan', { method: 'POST' }).catch(() => {});
            }
        } catch {
            toast.show('Failed to connect to ATS scanner. Using offline fallback.', 'error');
        } finally {
            setAnalyzing(false);
        }
    };

    const copyRewrite = (text, idx) => {
        navigator.clipboard.writeText(text);
        setCopiedIdx(idx);
        toast.show('Bullet copied to clipboard! Ready for Overleaf / LaTeX.', 'success');
        setTimeout(() => setCopiedIdx(null), 2500);
    };

    return (
        <div className="space-y-6">
            <header className="animate-rise">
                <div className="eyebrow flex items-center gap-1.5 text-cyan-400">
                    <FileCheck className="h-3.5 w-3.5" /> Placement Warfare · ATS Resume Weaponizer
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold tracking-tight">
                    ATS Resume Scanner & Bullet Weaponizer
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Score your resume bullet points against the Google XYZ formula: <b>Accomplished [X] measured by [Y] by doing [Z]</b>. Replace weak verbs with high-impact power metrics.
                </p>
            </header>

            <div className="grid gap-6 lg:grid-cols-12 items-start">
                {/* Input & Target Controls */}
                <div className="lg:col-span-6 space-y-4">
                    <Card className="card-pad space-y-4">
                        <CardHeader
                            title="Input Bullet Point"
                            subtitle="Paste any project or experience bullet point"
                            icon={Layers}
                        />

                        {/* Target Role Selector */}
                        <div>
                            <label className="text-xs font-semibold text-subtle uppercase tracking-wider block mb-1.5">
                                Target Role
                            </label>
                            <div className="flex flex-wrap gap-1.5">
                                {ROLES.map((r) => (
                                    <button
                                        key={r}
                                        onClick={() => setTargetRole(r)}
                                        className={cx(
                                            'px-3 py-1 rounded-lg text-xs font-medium transition-all',
                                            targetRole === r
                                                ? 'bg-accent text-accent-fg font-semibold shadow-sm'
                                                : 'bg-surface-2 text-muted hover:text-fg'
                                        )}
                                    >
                                        {r}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Bullet Textarea */}
                        <div>
                            <label className="text-xs font-semibold text-subtle uppercase tracking-wider block mb-1.5">
                                Bullet Text
                            </label>
                            <textarea
                                value={bullet}
                                onChange={(e) => setBullet(e.target.value)}
                                rows={4}
                                placeholder="e.g. Worked on backend API to make it faster and helped team fix bugs."
                                className="w-full p-3 rounded-xl border border-line bg-surface-2 text-sm text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-colors"
                            />
                        </div>

                        {/* Quick Presets */}
                        <div>
                            <div className="text-[11px] text-subtle font-semibold uppercase mb-1.5">Quick Samples:</div>
                            <div className="flex flex-wrap gap-2">
                                {SAMPLE_BULLETS.map((s) => (
                                    <button
                                        key={s.label}
                                        onClick={() => {
                                            setBullet(s.text);
                                            setTargetRole(s.role);
                                            runAnalysis(s.text, s.role);
                                        }}
                                        className="btn btn-ghost btn-sm text-xs bg-surface-2 hover:bg-surface-2/80"
                                    >
                                        {s.label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <button
                            onClick={() => runAnalysis()}
                            disabled={analyzing || !bullet.trim()}
                            className="btn btn-primary w-full py-2.5 font-bold shadow-md shadow-accent/20 flex items-center justify-center gap-2"
                        >
                            {analyzing ? (
                                <>
                                    <RefreshCw className="h-4 w-4 animate-spin" /> Scanning Bullet...
                                </>
                            ) : (
                                <>
                                    <Sparkles className="h-4 w-4" /> Scan & Generate Weaponized Rewrites
                                </>
                            )}
                        </button>
                    </Card>
                </div>

                {/* Live Diagnostic Score & Rewrites */}
                <div className="lg:col-span-6 space-y-4">
                    {result ? (
                        <div className="space-y-4 animate-rise">
                            {/* Score Card */}
                            <Card className="card-pad border-accent/30">
                                <div className="flex items-center justify-between pb-3 border-b border-line">
                                    <div>
                                        <div className="text-xs text-subtle font-semibold uppercase">ATS Impact Score</div>
                                        <div className="flex items-baseline gap-2 mt-0.5">
                                            <span className={cx(
                                                'text-3xl font-extrabold tabular-nums',
                                                result.score >= 80 ? 'text-ok' : result.score >= 60 ? 'text-amber-400' : 'text-rose-400'
                                            )}>
                                                {result.score}%
                                            </span>
                                            <span className="text-xs text-muted">
                                                {result.score >= 80 ? 'Tier-1 Interview Ready' : result.score >= 60 ? 'Moderate - Needs Metrics' : 'Weak - High Rejection Risk'}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-xs text-subtle font-semibold uppercase">Google XYZ Status</div>
                                        <div className="flex items-center gap-1.5 mt-1 text-xs font-semibold">
                                            {result.metrics_found?.length ? (
                                                <span className="text-ok flex items-center gap-1">
                                                    <CheckCircle2 className="h-4 w-4" /> Quantified
                                                </span>
                                            ) : (
                                                <span className="text-rose-400 flex items-center gap-1">
                                                    <AlertTriangle className="h-4 w-4" /> Unmeasured
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Verb Analysis */}
                                <div className="grid grid-cols-2 gap-3 py-3 border-b border-line text-xs">
                                    <div>
                                        <div className="font-semibold text-subtle mb-1">Power Verbs Found:</div>
                                        {result.power_verbs_found?.length ? (
                                            <div className="flex flex-wrap gap-1">
                                                {result.power_verbs_found.map((v) => (
                                                    <span key={v} className="badge bg-ok/10 text-ok border border-ok/30 font-mono">
                                                        {v}
                                                    </span>
                                                ))}
                                            </div>
                                        ) : (
                                            <span className="text-muted italic">None detected</span>
                                        )}
                                    </div>
                                    <div>
                                        <div className="font-semibold text-subtle mb-1">Weak Verbs Found:</div>
                                        {result.weak_verbs_found?.length ? (
                                            <div className="flex flex-wrap gap-1">
                                                {result.weak_verbs_found.map((v) => (
                                                    <span key={v} className="badge bg-rose-500/10 text-rose-400 border border-rose-500/30 font-mono line-through">
                                                        {v}
                                                    </span>
                                                ))}
                                            </div>
                                        ) : (
                                            <span className="text-ok text-xs">No weak verbs!</span>
                                        )}
                                    </div>
                                </div>

                                {/* Keyword Suggestions */}
                                <div className="pt-2 text-xs">
                                    <div className="font-semibold text-subtle mb-1.5">Recommended Tech Keywords to Infuse:</div>
                                    <div className="flex flex-wrap gap-1.5">
                                        {result.suggested_keywords?.map((k) => (
                                            <span key={k} className="px-2 py-0.5 rounded bg-surface-2 border border-line text-subtle font-mono text-[11px]">
                                                +{k}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </Card>

                            {/* Rewrites Section */}
                            <div className="space-y-3">
                                <div className="flex items-center gap-2">
                                    <Sparkles className="h-4 w-4 text-accent" />
                                    <h3 className="text-sm font-bold text-fg uppercase tracking-wider">
                                        Weaponized AI Rewrites (Ready to Copy)
                                    </h3>
                                </div>

                                {result.ai_rewrites?.map((rw, i) => (
                                    <Card key={i} className="card-pad border-line hover:border-accent/40 transition-colors">
                                        <div className="flex items-start justify-between gap-3 mb-2">
                                            <span className="badge text-[11px] font-bold bg-accent/15 text-accent border border-accent/20">
                                                {rw.flavor}
                                            </span>
                                            <button
                                                onClick={() => copyRewrite(rw.text, i)}
                                                className="btn btn-secondary btn-sm flex items-center gap-1.5 text-xs font-semibold"
                                            >
                                                {copiedIdx === i ? (
                                                    <>
                                                        <Check className="h-3.5 w-3.5 text-ok" /> Copied!
                                                    </>
                                                ) : (
                                                    <>
                                                        <Copy className="h-3.5 w-3.5" /> Copy Bullet
                                                    </>
                                                )}
                                            </button>
                                        </div>
                                        <p className="text-[13px] text-fg leading-relaxed bg-surface-2/60 p-2.5 rounded-lg border border-line font-medium">
                                            {rw.text}
                                        </p>
                                        <div className="mt-2 flex items-center justify-between text-[11px] text-subtle">
                                            <span>Metrics: <b className="text-accent">{rw.metrics}</b></span>
                                            <span>Power Verbs: <b>{rw.verbs?.join(', ')}</b></span>
                                        </div>
                                    </Card>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <Card className="card-pad text-center py-16 space-y-3 border-dashed border-line">
                            <FileCheck className="h-10 w-10 text-subtle mx-auto" />
                            <p className="font-semibold text-fg">Ready for your first bullet scan</p>
                            <p className="text-xs text-subtle max-w-xs mx-auto">
                                Click "Scan & Generate Weaponized Rewrites" to benchmark your bullet point against top tech recruiters.
                            </p>
                        </Card>
                    )}
                </div>
            </div>
        </div>
    );
}
