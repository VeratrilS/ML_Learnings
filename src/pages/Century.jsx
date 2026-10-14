import { useState, useMemo } from 'react';
import {
    Trophy, Search, Sparkles, Zap, ArrowRight, CheckCircle2,
    Filter, Star, Flame, Shield, Award, Terminal
} from 'lucide-react';
import { Button, Card, ProgressBar, Skeleton, useToast, cx } from '../components/ui';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { CENTURY_FEATURES } from '../lib/centuryCatalog';

export default function Century() {
    const toast = useToast();
    const catalogRes = useApi('/century/catalog');

    const rawCatalog = catalogRes.data?.catalog;
    const catalog = useMemo(() => {
        if (rawCatalog && rawCatalog.length > 0) return rawCatalog;
        return CENTURY_FEATURES.map((f) => ({
            id: f.id,
            title: f.label,
            domain: f.domain,
            desc: f.desc,
            xp: f.xp || 75,
            route: `#/${f.id}`,
            status: 'unlocked',
            usage_count: 0,
        }));
    }, [rawCatalog]);

    const domains = useMemo(() => {
        if (catalogRes.data?.domains && catalogRes.data.domains.length > 0) return catalogRes.data.domains;
        return Array.from(new Set(CENTURY_FEATURES.map((f) => f.domain)));
    }, [catalogRes.data?.domains]);

    const stats = catalogRes.data?.stats || {
        total_features: catalog.length,
        used_features: 0,
        mastered_features: 0,
        completion_pct: 0
    };

    const [activeDomain, setActiveDomain] = useState('All');
    const [searchQuery, setSearchQuery] = useState('');
    const [activatingId, setActivatingId] = useState(null);

    const filteredFeatures = useMemo(() => {
        return catalog.filter((f) => {
            const matchesDomain = activeDomain === 'All' || f.domain === activeDomain;
            const q = searchQuery.toLowerCase().trim();
            const matchesQuery = !q ||
                (f.title || f.label || '').toLowerCase().includes(q) ||
                (f.desc || '').toLowerCase().includes(q) ||
                (f.domain || '').toLowerCase().includes(q) ||
                (f.id || '').toLowerCase().includes(q);
            return matchesDomain && matchesQuery;
        });
    }, [catalog, activeDomain, searchQuery]);

    const handleActivate = async (feature) => {
        const targetRoute = feature.route || `#/${feature.id}`;
        
        // If it's a navigable feature, jump immediately for instant responsiveness
        if (targetRoute && targetRoute !== '#/century') {
            window.location.hash = targetRoute;
        }

        setActivatingId(feature.id);
        try {
            const res = await api(`/century/action/${feature.id}`, { method: 'POST' });
            toast(res?.message || `Activated ${feature.title || feature.label}! +${feature.xp} XP`, 'success');
            catalogRes.reload();
        } catch (err) {
            toast(err.message || 'Activation failed', 'danger');
        } finally {
            setActivatingId(null);
        }
    };

    return (
        <div className="space-y-6 animate-fade-in max-w-6xl mx-auto pb-12">
            {/* Header Hero */}
            <div className="relative overflow-hidden rounded-3xl border border-line bg-surface/80 p-6 md:p-8 backdrop-blur-xl shadow-2xl">
                <div className="absolute top-0 right-0 -mr-16 -mt-16 w-72 h-72 bg-accent/15 rounded-full blur-3xl pointer-events-none" />
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-accent-soft text-accent border border-accent/25 mb-3">
                            <Trophy className="w-3.5 h-3.5" /> Century Hall of Fame · 100 Beta Features
                        </div>
                        <h1 className="text-3xl md:text-5xl font-black tracking-tight text-fg flex items-center gap-3">
                            The Century Command Center
                        </h1>
                        <p className="text-sm md:text-base text-subtle mt-2 max-w-2xl leading-relaxed">
                            A universe of 100 high-octane engineering, algorithmic combat, distributed systems, deep focus, and semester mastery tools built for high-performance engineers.
                        </p>
                    </div>

                    {/* Overall Progress Meter */}
                    <div className="bg-surface-2/80 p-4 rounded-2xl border border-line min-w-[220px] space-y-2">
                        <div className="flex items-center justify-between text-xs font-bold text-fg">
                            <span>Mastery Progress</span>
                            <span className="text-accent">{stats.completion_pct}%</span>
                        </div>
                        <ProgressBar value={stats.completion_pct} className="h-2.5" />
                        <div className="flex items-center justify-between text-[11px] text-subtle font-medium pt-1">
                            <span>{stats.used_features}/{stats.total_features} Activated</span>
                            <span>{stats.mastered_features} Mastered</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Filter Bar & Search */}
            <div className="space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    {/* Domain Tabs */}
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-2 sm:pb-0 scrollbar-none">
                        <button
                            type="button"
                            onClick={() => setActiveDomain('All')}
                            className={cx(
                                'px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap',
                                activeDomain === 'All'
                                    ? 'bg-accent text-accent-fg shadow-sm'
                                    : 'bg-surface hover:bg-surface-2 text-subtle hover:text-fg border border-line'
                            )}
                        >
                            All (100)
                        </button>
                        {domains.map((dom) => (
                            <button
                                key={dom}
                                type="button"
                                onClick={() => setActiveDomain(dom)}
                                className={cx(
                                    'px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap',
                                    activeDomain === dom
                                        ? 'bg-accent text-accent-fg shadow-sm'
                                        : 'bg-surface hover:bg-surface-2 text-subtle hover:text-fg border border-line'
                                )}
                            >
                                {dom}
                            </button>
                        ))}
                    </div>

                    {/* Search Input */}
                    <div className="relative min-w-[240px]">
                        <Search className="w-4 h-4 text-subtle absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="Search 100 features..."
                            className="w-full pl-9 pr-3 py-1.5 rounded-xl bg-surface border border-line text-xs text-fg focus:border-accent focus:ring-1 focus:ring-accent transition-all"
                        />
                    </div>
                </div>

                <div className="text-xs text-subtle px-1">
                    Showing {filteredFeatures.length} of {catalog.length} features in <b>{activeDomain}</b>
                </div>
            </div>

            {/* Features 100 Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                {filteredFeatures.map((f) => {
                    const isMastered = f.status === 'mastered';
                    const hasUsed = f.usage_count > 0;
                    const titleText = f.title || f.label;

                    return (
                        <Card
                            key={f.id}
                            className={cx(
                                'p-4 border transition-all relative flex flex-col justify-between group hover:shadow-lg',
                                isMastered ? 'border-amber-500/40 bg-amber-500/5' :
                                hasUsed ? 'border-accent/40 bg-accent-soft/30' : 'border-line bg-surface hover:border-accent/30'
                            )}
                        >
                            <div>
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-2 text-subtle border border-line uppercase tracking-wider">
                                        {f.domain}
                                    </span>
                                    <span className="text-xs font-mono font-bold text-accent">+{f.xp} XP</span>
                                </div>

                                <h3 className="font-bold text-fg text-sm flex items-center gap-1.5">
                                    {titleText}
                                    {isMastered && <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />}
                                </h3>
                                <p className="text-xs text-subtle mt-1 line-clamp-2 leading-relaxed">{f.desc}</p>
                            </div>

                            <div className="flex items-center justify-between gap-2 pt-3 mt-3 border-t border-line/60">
                                <div className="text-[11px] text-subtle font-mono">
                                    {f.usage_count > 0 ? `${f.usage_count}x triggered` : 'Ready'}
                                </div>

                                <Button
                                    onClick={() => handleActivate(f)}
                                    disabled={activatingId === f.id}
                                    className="btn-primary btn-sm text-xs px-3 py-1.5 gap-1 shrink-0 shadow-sm"
                                >
                                    {f.route && f.route !== '#/century' ? (
                                        <>Open <ArrowRight className="w-3 h-3" /></>
                                    ) : (
                                        <>Activate <Zap className="w-3 h-3" /></>
                                    )}
                                </Button>
                            </div>
                        </Card>
                    );
                })}
            </div>
        </div>
    );
}
