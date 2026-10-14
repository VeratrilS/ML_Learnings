import { FileCheck, ArrowRight, Sparkles, CheckCircle2 } from 'lucide-react';
import { Card, CardHeader } from './ui';

export default function ATSCard() {
    return (
        <Card className="card-pad hover:border-accent/40 transition-colors animate-rise">
            <CardHeader
                title="ATS Bullet Weaponizer"
                subtitle="Google XYZ Metric Optimizer"
                icon={FileCheck}
                action={
                    <span className="badge text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 font-bold">
                        Placement Ready
                    </span>
                }
            />

            <div className="p-3 rounded-xl bg-surface-2/60 border border-line my-3 space-y-1.5 text-xs">
                <div className="flex items-center gap-1.5 text-accent font-semibold">
                    <Sparkles className="h-3.5 w-3.5" /> Formula: Accomplished [X] measured by [Y] by doing [Z]
                </div>
                <p className="text-subtle leading-relaxed">
                    Scan your resume bullets for weak verbs, missing performance metrics, and inject FAANG-tier power verbs.
                </p>
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
                <span className="text-[11px] text-subtle flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3 text-ok" /> 3 AI Rewrite Flavors
                </span>
                <a href="#/ats_scan" className="btn btn-primary btn-sm shrink-0 gap-1 font-semibold">
                    Scan Resume <ArrowRight className="h-3.5 w-3.5" />
                </a>
            </div>
        </Card>
    );
}
