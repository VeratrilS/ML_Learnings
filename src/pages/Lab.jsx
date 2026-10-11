import { FlaskConical, Check, EyeOff, ExternalLink, Undo2 } from 'lucide-react';
import { FEATURES, useFeatures } from '../lib/features';
import { Card, cx } from '../components/ui';

const STATUS_STYLE = {
    beta: 'bg-accent-soft text-accent',
    approved: 'bg-ok/10 text-ok',
    hidden: 'bg-surface-2 text-subtle',
};

export default function Lab() {
    const { status, setStatus } = useFeatures();
    const list = FEATURES.filter((f) => f.available);
    const counts = list.reduce((a, f) => ({ ...a, [status(f.id)]: (a[status(f.id)] || 0) + 1 }), {});

    return (
        <div className="space-y-5 sm:space-y-6">
            <header className="animate-rise">
                <div className="eyebrow flex items-center gap-1.5"><FlaskConical className="h-3.5 w-3.5" /> Beta Lab</div>
                <h1 className="mt-1 text-[28px] sm:text-3xl font-bold tracking-tight">New features, your call</h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Everything new starts here as <b>Beta</b>. Try it, then approve it to add it to your nav and Today page, or hide it.
                    {' '}<span className="text-subtle">{counts.approved || 0} approved · {counts.beta || 0} in beta · {counts.hidden || 0} hidden</span>
                </p>
            </header>

            <div className="grid gap-3 sm:gap-4 sm:grid-cols-2">
                {list.map((f) => {
                    const s = status(f.id);
                    return (
                        <Card key={f.id} className={cx('card-pad flex flex-col', s === 'hidden' && 'opacity-60')}>
                            <div className="flex items-start gap-3">
                                <div className="grid place-items-center h-9 w-9 rounded-xl bg-surface-2 border border-line text-muted shrink-0">
                                    <f.icon className="h-[18px] w-[18px]" />
                                </div>
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                        <h2 className="text-[15px] font-semibold tracking-tight">{f.label}</h2>
                                        <span className={cx('badge uppercase tracking-wide', STATUS_STYLE[s])}>{s}</span>
                                    </div>
                                    <p className="text-[13px] text-muted mt-1 leading-snug">{f.desc}</p>
                                </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-line">
                                {f.page && (
                                    <a href={`#/${f.id}`} className="btn btn-secondary btn-sm"><ExternalLink className="h-3.5 w-3.5" /> Try it</a>
                                )}
                                <span className="flex-1" />
                                {s !== 'approved' && (
                                    <button className="btn btn-primary btn-sm" onClick={() => setStatus(f.id, 'approved')}><Check className="h-3.5 w-3.5" /> Approve</button>
                                )}
                                {s === 'approved' && (
                                    <button className="btn btn-ghost btn-sm" onClick={() => setStatus(f.id, 'beta')}><Undo2 className="h-3.5 w-3.5" /> Back to beta</button>
                                )}
                                {s !== 'hidden' ? (
                                    <button className="btn btn-ghost btn-sm" onClick={() => setStatus(f.id, 'hidden')}><EyeOff className="h-3.5 w-3.5" /> Hide</button>
                                ) : (
                                    <button className="btn btn-ghost btn-sm" onClick={() => setStatus(f.id, 'beta')}>Unhide</button>
                                )}
                            </div>
                        </Card>
                    );
                })}
            </div>
        </div>
    );
}
