import { useState, useMemo } from 'react';
import { FlaskConical, Check, EyeOff, ExternalLink, Undo2, Search, Trophy, Sparkles, CheckCheck, X } from 'lucide-react';
import { FEATURES, useFeatures } from '../lib/features';
import { Card, cx } from '../components/ui';

const DOMAIN_STYLES = {
    'DSA & Combat': 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    'System Design': 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    'AI & ML': 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    'Academics': 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    'Bio-Hacking': 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    'Placement Warfare': 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    'Power Tools': 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
};

const STATUS_STYLE = {
    beta: 'bg-accent-soft text-accent border border-accent/30',
    approved: 'bg-ok/10 text-ok border border-ok/30',
    hidden: 'bg-surface-2 text-subtle border border-line',
};

const DOMAINS = [
    'All Domains',
    'DSA & Combat',
    'System Design',
    'AI & ML',
    'Academics',
    'Bio-Hacking',
    'Placement Warfare',
    'Power Tools',
];

export default function Lab() {
    const { status, setStatus } = useFeatures();
    const list = FEATURES.filter((f) => f.available);
    const [search, setSearch] = useState('');
    const [selectedDomain, setSelectedDomain] = useState('All Domains');
    const [statusFilter, setStatusFilter] = useState('all');

    const counts = useMemo(() => {
        return list.reduce((a, f) => ({ ...a, [status(f.id)]: (a[status(f.id)] || 0) + 1 }), {});
    }, [list, status]);

    const filtered = useMemo(() => {
        return list.filter((f) => {
            const s = status(f.id);
            if (statusFilter !== 'all' && s !== statusFilter) return false;
            if (selectedDomain !== 'All Domains' && f.domain !== selectedDomain) return false;
            if (search.trim()) {
                const q = search.toLowerCase();
                const matchLabel = f.label.toLowerCase().includes(q);
                const matchDesc = (f.desc || '').toLowerCase().includes(q);
                const matchDomain = (f.domain || '').toLowerCase().includes(q);
                const matchId = f.id.toLowerCase().includes(q);
                if (!matchLabel && !matchDesc && !matchDomain && !matchId) return false;
            }
            return true;
        });
    }, [list, status, statusFilter, selectedDomain, search]);

    const approveAll = () => {
        filtered.forEach((f) => {
            if (status(f.id) !== 'approved') setStatus(f.id, 'approved');
        });
    };

    const resetAllToBeta = () => {
        filtered.forEach((f) => {
            if (status(f.id) !== 'beta') setStatus(f.id, 'beta');
        });
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <header className="animate-rise flex flex-col md:flex-row md:items-end justify-between gap-4">
                <div>
                    <div className="eyebrow flex items-center gap-1.5 text-accent">
                        <FlaskConical className="h-3.5 w-3.5" /> Beta Lab · 100 Engineering Features
                    </div>
                    <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold tracking-tight">
                        Beta Command & Discovery
                    </h1>
                    <p className="text-sm text-muted mt-1 max-w-2xl">
                        Everything new starts here in <b>Beta</b>. Try any feature instantly, approve it to add to your navigation and dashboard, or explore the complete Century cockpit.
                    </p>
                </div>

                {/* Quick Status Stats */}
                <div className="flex flex-wrap items-center gap-2">
                    <button
                        onClick={() => setStatusFilter('all')}
                        className={cx('px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all',
                            statusFilter === 'all' ? 'bg-surface-2 text-fg border-accent' : 'bg-surface border-line text-subtle hover:text-fg')}
                    >
                        Total: {list.length}
                    </button>
                    <button
                        onClick={() => setStatusFilter('beta')}
                        className={cx('px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all',
                            statusFilter === 'beta' ? 'bg-accent/20 text-accent border-accent' : 'bg-surface border-line text-subtle hover:text-fg')}
                    >
                        In Beta: {counts.beta || 0}
                    </button>
                    <button
                        onClick={() => setStatusFilter('approved')}
                        className={cx('px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all',
                            statusFilter === 'approved' ? 'bg-ok/20 text-ok border-ok' : 'bg-surface border-line text-subtle hover:text-fg')}
                    >
                        Approved: {counts.approved || 0}
                    </button>
                </div>
            </header>

            {/* Century Hero Banner */}
            <div className="relative overflow-hidden rounded-2xl border border-accent/30 bg-gradient-to-r from-accent/15 via-purple-500/10 to-surface-2 p-5 sm:p-6 shadow-lg shadow-accent/5">
                <div className="relative z-10 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-1">
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-accent text-accent-fg uppercase tracking-wider">
                            <Trophy className="w-3 h-3" /> Century Suite Active
                        </div>
                        <h2 className="text-lg sm:text-xl font-bold tracking-tight text-fg flex items-center gap-2">
                            100 Elite Engineering & Placement Beta Tools Ready
                        </h2>
                        <p className="text-xs sm:text-sm text-muted max-w-xl">
                            From Hot Seat AI interrogations and FAANG Bug Hunts to Big-O shootout casinos and system simulators — jump into the master cockpit.
                        </p>
                    </div>
                    <div className="flex items-center gap-2.5 shrink-0">
                        <a
                            href="#/century"
                            className="btn btn-primary text-sm shadow-md shadow-accent/20 flex items-center gap-2 font-semibold"
                        >
                            <Trophy className="h-4 w-4" /> Open 100 Cockpit
                        </a>
                    </div>
                </div>
            </div>

            {/* Controls: Search, Domain Tabs, Bulk Actions */}
            <div className="space-y-3 bg-surface/50 border border-line rounded-2xl p-4">
                <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
                    <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-subtle" />
                        <input
                            type="text"
                            placeholder="Search 100 beta features by title, domain, or capability..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full pl-9 pr-8 py-2 rounded-xl border border-line bg-surface-2 text-sm text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-colors"
                        />
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle hover:text-fg"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                        <button
                            onClick={approveAll}
                            className="btn btn-secondary btn-sm flex items-center gap-1.5 text-xs text-ok hover:border-ok/40"
                            title="Approve all visible features into your navigation"
                        >
                            <CheckCheck className="h-3.5 w-3.5" /> Approve Visible ({filtered.length})
                        </button>
                        <button
                            onClick={resetAllToBeta}
                            className="btn btn-ghost btn-sm flex items-center gap-1.5 text-xs text-subtle hover:text-fg"
                            title="Reset visible features back to Beta state"
                        >
                            <Undo2 className="h-3.5 w-3.5" /> Reset to Beta
                        </button>
                    </div>
                </div>

                {/* Domain Category Filter Tabs */}
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
                    {DOMAINS.map((dom) => {
                        const active = selectedDomain === dom;
                        return (
                            <button
                                key={dom}
                                onClick={() => setSelectedDomain(dom)}
                                className={cx(
                                    'whitespace-nowrap px-3 py-1.5 rounded-lg font-medium transition-all',
                                    active
                                        ? 'bg-accent text-accent-fg font-semibold shadow-sm'
                                        : 'bg-surface-2 text-muted hover:text-fg hover:bg-surface-2/80'
                                )}
                            >
                                {dom}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Features Grid */}
            <div className="grid gap-3 sm:gap-4 sm:grid-cols-2">
                {filtered.map((f) => {
                    const s = status(f.id);
                    const domainBadgeClass = DOMAIN_STYLES[f.domain] || 'bg-surface-2 text-subtle border-line';
                    return (
                        <Card
                            key={f.id}
                            className={cx(
                                'card-pad flex flex-col justify-between transition-all hover:border-accent/40',
                                s === 'hidden' && 'opacity-60',
                                s === 'approved' && 'border-ok/30'
                            )}
                        >
                            <div>
                                <div className="flex items-start gap-3">
                                    <div className="grid place-items-center h-10 w-10 rounded-xl bg-surface-2 border border-line text-accent shrink-0 shadow-sm">
                                        <f.icon className="h-5 w-5" />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <h2 className="text-[15px] font-bold tracking-tight text-fg">{f.label}</h2>
                                            <span className={cx('badge text-[10px] font-semibold uppercase tracking-wider', STATUS_STYLE[s])}>
                                                {s}
                                            </span>
                                            {f.domain && (
                                                <span className={cx('badge text-[10px] border', domainBadgeClass)}>
                                                    {f.domain}
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-[13px] text-muted mt-1 leading-snug">{f.desc}</p>
                                    </div>
                                </div>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-line">
                                {f.page && (
                                    <a
                                        href={`#/${f.id}`}
                                        className="btn btn-secondary btn-sm flex items-center gap-1.5 font-semibold text-accent hover:border-accent/50"
                                    >
                                        <ExternalLink className="h-3.5 w-3.5" /> Try it
                                    </a>
                                )}
                                <span className="flex-1" />
                                {s !== 'approved' && (
                                    <button
                                        className="btn btn-primary btn-sm flex items-center gap-1 text-xs"
                                        onClick={() => setStatus(f.id, 'approved')}
                                    >
                                        <Check className="h-3.5 w-3.5" /> Approve
                                    </button>
                                )}
                                {s === 'approved' && (
                                    <button
                                        className="btn btn-ghost btn-sm flex items-center gap-1 text-xs text-ok hover:text-subtle"
                                        onClick={() => setStatus(f.id, 'beta')}
                                    >
                                        <Undo2 className="h-3.5 w-3.5" /> Back to beta
                                    </button>
                                )}
                                {s !== 'hidden' ? (
                                    <button
                                        className="btn btn-ghost btn-sm flex items-center gap-1 text-xs text-subtle hover:text-fg"
                                        onClick={() => setStatus(f.id, 'hidden')}
                                    >
                                        <EyeOff className="h-3.5 w-3.5" /> Hide
                                    </button>
                                ) : (
                                    <button
                                        className="btn btn-ghost btn-sm text-xs"
                                        onClick={() => setStatus(f.id, 'beta')}
                                    >
                                        Unhide
                                    </button>
                                )}
                            </div>
                        </Card>
                    );
                })}
            </div>

            {filtered.length === 0 && (
                <div className="card card-pad text-center py-16 space-y-3">
                    <FlaskConical className="h-8 w-8 text-subtle mx-auto" />
                    <p className="font-semibold text-fg">No beta features match your filters.</p>
                    <p className="text-xs text-subtle">Try clearing your search query or selecting "All Domains".</p>
                    <button
                        onClick={() => { setSearch(''); setSelectedDomain('All Domains'); setStatusFilter('all'); }}
                        className="btn btn-secondary btn-sm"
                    >
                        Reset filters
                    </button>
                </div>
            )}
        </div>
    );
}
