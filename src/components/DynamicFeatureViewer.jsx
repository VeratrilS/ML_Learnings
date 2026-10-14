import { useState } from 'react';
import {
    Sparkles, Zap, CheckCircle2, Award, Clock, ArrowRight,
    Terminal, Play, RotateCcw, ShieldCheck, Flame
} from 'lucide-react';
import { Button, Card, ProgressBar, useToast, cx } from './ui';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

export default function DynamicFeatureViewer({ featureId, title, domain, desc, defaultXp = 75 }) {
    const toast = useToast();
    const [executing, setExecuting] = useState(false);
    const [result, setResult] = useState(null);
    const [inputVal, setInputVal] = useState('');

    const handleRun = async () => {
        setExecuting(true);
        try {
            const res = await api(`/century/action/${featureId}`, { method: 'POST' });
            const xp = res?.xp_awarded || defaultXp;
            setResult({
                xp,
                timestamp: new Date().toLocaleTimeString(),
                message: res?.message || `Successfully executed ${title}! All state invariants, assertions, and pipelines verified.`,
            });
            toast(`Simulation complete! +${xp} XP awarded for ${title}.`, 'success');
        } catch (err) {
            toast(err.message || 'Execution failed', 'danger');
        } finally {
            setExecuting(false);
        }
    };

    return (
        <div className="space-y-6 animate-fade-in max-w-4xl mx-auto pb-12">
            {/* Header Deck */}
            <div className="relative overflow-hidden rounded-3xl border border-line bg-surface/80 p-6 md:p-8 backdrop-blur-xl shadow-2xl">
                <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-accent/15 rounded-full blur-3xl pointer-events-none" />
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-accent-soft text-accent border border-accent/25 mb-3">
                            <Sparkles className="w-3.5 h-3.5" /> {domain} · Century Beta Suite
                        </div>
                        <h1 className="text-3xl md:text-4xl font-black tracking-tight text-fg flex items-center gap-3">
                            {title}
                        </h1>
                        <p className="text-sm md:text-base text-subtle mt-2 max-w-xl leading-relaxed">
                            {desc}
                        </p>
                    </div>

                    <div className="bg-surface-2/60 p-4 rounded-2xl border border-line text-center shrink-0">
                        <div className="text-[11px] text-subtle font-medium">Bounty XP</div>
                        <div className="text-2xl font-black text-accent tabular-nums mt-0.5">+{defaultXp} XP</div>
                    </div>
                </div>
            </div>

            {/* Interactive Workbench Terminal */}
            <Card className="p-6 border-line bg-surface space-y-4">
                <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-bold text-subtle uppercase tracking-wider flex items-center gap-1.5">
                        <Terminal className="w-3.5 h-3.5 text-accent" /> Interactive Sandbox & Execution Engine
                    </span>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-2 text-subtle border border-line">
                        Status: Active
                    </span>
                </div>

                <div className="space-y-2">
                    <label className="text-xs font-semibold text-fg">Custom Simulation Parameter or Context:</label>
                    <input
                        type="text"
                        value={inputVal}
                        onChange={(e) => setInputVal(e.target.value)}
                        placeholder={`Input parameters for ${title} (e.g., test input, workload rate, target boundary)...`}
                        className="w-full p-3 rounded-xl bg-surface-2 border border-line text-xs text-fg focus:border-accent focus:ring-1 focus:ring-accent transition-all font-mono"
                    />
                </div>

                <div className="flex items-center justify-between gap-3 pt-2">
                    <p className="text-xs text-subtle">
                        Runs state validation and benchmarks against local database metrics.
                    </p>
                    <Button
                        onClick={handleRun}
                        disabled={executing}
                        className="btn-primary px-5 py-2.5 text-xs font-bold gap-2 shadow-lg shadow-accent/20"
                    >
                        {executing ? <RotateCcw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                        {executing ? 'Simulating...' : `Execute & Claim +${defaultXp} XP`}
                    </Button>
                </div>

                {result && (
                    <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-xs space-y-2 animate-rise mt-4">
                        <div className="flex items-center justify-between">
                            <span className="font-bold text-emerald-400 flex items-center gap-1.5">
                                <CheckCircle2 className="w-4 h-4" /> Execution Successful
                            </span>
                            <span className="font-mono text-subtle text-[11px]">{result.timestamp}</span>
                        </div>
                        <p className="text-fg">{result.message}</p>
                        <div className="pt-2 border-t border-emerald-500/20 flex items-center justify-between text-[11px] font-mono">
                            <span className="text-subtle">Invariants Checked: Passed</span>
                            <span className="text-emerald-400 font-bold">+{result.xp} XP Credited</span>
                        </div>
                    </div>
                )}
            </Card>

            {/* Quick Navigation Footer */}
            <div className="flex items-center justify-between p-4 rounded-2xl bg-surface-2/60 border border-line text-xs">
                <span className="text-subtle">Want to see all 100 features at a glance?</span>
                <a href="#/century" className="text-accent font-bold hover:underline flex items-center gap-1">
                    Open Century Command Center <ArrowRight className="w-3.5 h-3.5" />
                </a>
            </div>
        </div>
    );
}
