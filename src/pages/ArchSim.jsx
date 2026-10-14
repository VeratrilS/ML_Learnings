import { useState, useEffect } from 'react';
import {
    Network, Server, Database, Zap, AlertTriangle, ShieldCheck,
    Flame, Sliders, Play, HardDrive, Globe, RefreshCw, Cpu, Activity
} from 'lucide-react';
import { api } from '../lib/api';
import { Card, CardHeader, cx, useToast } from '../components/ui';

export default function ArchSim() {
    const toast = useToast();
    const [rps, setRps] = useState(15000);
    const [instances, setInstances] = useState(4);
    const [cdnEnabled, setCdnEnabled] = useState(true);
    const [cacheEnabled, setCacheEnabled] = useState(true);
    const [dbReplicas, setDbReplicas] = useState(2);
    const [scenario, setScenario] = useState('none');
    const [simulating, setSimulating] = useState(false);
    const [metrics, setMetrics] = useState(null);
    const [bottlenecks, setBottlenecks] = useState([]);

    const runSimulation = async (currScenario = scenario) => {
        setSimulating(true);
        try {
            const res = await api('/century/archsim/simulate', {
                method: 'POST',
                body: {
                    rps,
                    instances,
                    cdn_enabled: cdnEnabled,
                    cache_enabled: cacheEnabled,
                    db_replicas: dbReplicas,
                    scenario: currScenario,
                },
            });
            if (res && res.success) {
                setMetrics(res.metrics);
                setBottlenecks(res.bottlenecks || []);
                api('/century/action/archsim', { method: 'POST' }).catch(() => {});
            }
        } catch {
            toast.show('Simulation telemetry offline. Check API connection.', 'error');
        } finally {
            setSimulating(false);
        }
    };

    useEffect(() => {
        runSimulation('none');
    }, [instances, cdnEnabled, cacheEnabled, dbReplicas]); // auto-recalculate on architecture change

    const triggerChaos = (scenKey) => {
        setScenario(scenKey);
        runSimulation(scenKey);
        if (scenKey === 'flash_sale') {
            toast.show('🔥 100,000 RPS Flash Sale traffic spike injected!', 'warning');
        } else if (scenKey === 'cache_stampede') {
            toast.show('⚠️ Cache Stampede (Thundering herd) triggered on DB!', 'warning');
        } else if (scenKey === 'db_primary_down') {
            toast.show('💥 Primary DB Crash! Write transactions failing!', 'error');
        } else {
            toast.show('System restored to normal traffic state.', 'success');
        }
    };

    return (
        <div className="space-y-6">
            <header className="animate-rise">
                <div className="eyebrow flex items-center gap-1.5 text-blue-400">
                    <Network className="h-3.5 w-3.5" /> System Design · Distributed Architecture Simulator
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-extrabold tracking-tight">
                    System Architecture & Traffic Stress Lab
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Configure your distributed tier (Edge CDN, Load Balancer, Microservices, Redis Cache, DB Replicas) and inject chaos spikes to test P99 latencies and bottlenecks.
                </p>
            </header>

            {/* Architecture Topology View */}
            <Card className="card-pad border-accent/20 bg-surface/50">
                <div className="flex items-center justify-between mb-4">
                    <div className="text-xs font-bold uppercase tracking-wider text-subtle flex items-center gap-2">
                        <Activity className="h-4 w-4 text-accent" /> Live Distributed Architecture Topology
                    </div>
                    <span className="badge text-[11px] font-mono bg-surface-2 border border-line text-accent">
                        {instances} Pods · {dbReplicas} DB Nodes · {cdnEnabled ? 'CDN Active' : 'No CDN'}
                    </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 items-center text-center py-4">
                    {/* Clients & CDN */}
                    <div className="p-3 rounded-xl bg-surface-2 border border-line flex flex-col items-center">
                        <Globe className="h-6 w-6 text-blue-400 mb-1" />
                        <div className="text-xs font-bold text-fg">Edge / CDN</div>
                        <div className="text-[10.5px] text-subtle mt-0.5">
                            {cdnEnabled ? 'Cloudflare 75% Hit' : 'Bypassed'}
                        </div>
                    </div>

                    <div className="hidden sm:flex justify-center text-subtle">➔</div>

                    {/* Compute Layer */}
                    <div className="p-3 rounded-xl bg-surface-2 border border-line flex flex-col items-center">
                        <Server className="h-6 w-6 text-emerald-400 mb-1" />
                        <div className="text-xs font-bold text-fg">Compute Cluster</div>
                        <div className="text-[10.5px] text-accent font-semibold mt-0.5">
                            {instances} Microservices ({instances * 4}K RPS cap)
                        </div>
                    </div>

                    <div className="hidden sm:flex justify-center text-subtle">➔</div>

                    {/* Data Layer */}
                    <div className="p-3 rounded-xl bg-surface-2 border border-line flex flex-col items-center">
                        <div className="flex gap-2">
                            <HardDrive className={cx('h-5 w-5', cacheEnabled ? 'text-amber-400' : 'text-subtle')} />
                            <Database className="h-5 w-5 text-purple-400" />
                        </div>
                        <div className="text-xs font-bold text-fg mt-1">Redis + Postgres</div>
                        <div className="text-[10.5px] text-subtle mt-0.5">
                            {cacheEnabled ? 'Redis LRU' : 'No Cache'} · {dbReplicas} Replicas
                        </div>
                    </div>
                </div>
            </Card>

            <div className="grid gap-6 lg:grid-cols-12 items-start">
                {/* Configuration Controls */}
                <div className="lg:col-span-6 space-y-4">
                    <Card className="card-pad space-y-5">
                        <CardHeader
                            title="Infrastructure Controls"
                            subtitle="Tune capacity and edge components"
                            icon={Sliders}
                        />

                        {/* Traffic Slider */}
                        <div>
                            <div className="flex justify-between items-center text-xs mb-1.5 font-semibold">
                                <span className="text-subtle">Incoming Request Rate</span>
                                <span className="text-accent font-mono text-sm font-bold">{rps.toLocaleString()} RPS</span>
                            </div>
                            <input
                                type="range"
                                min={1000}
                                max={120000}
                                step={1000}
                                value={rps}
                                onChange={(e) => setRps(Number(e.target.value))}
                                className="w-full accent-accent cursor-pointer"
                            />
                            <div className="flex justify-between text-[10px] text-subtle mt-1 font-mono">
                                <span>1K (Chill)</span>
                                <span>25K (Heavy)</span>
                                <span>60K (Spike)</span>
                                <span>120K (Black Friday)</span>
                            </div>
                        </div>

                        {/* Instances Slider */}
                        <div>
                            <div className="flex justify-between items-center text-xs mb-1.5 font-semibold">
                                <span className="text-subtle">Microservice Pods (Autoscaling)</span>
                                <span className="text-fg font-mono text-sm font-bold">{instances} Instances</span>
                            </div>
                            <input
                                type="range"
                                min={1}
                                max={20}
                                step={1}
                                value={instances}
                                onChange={(e) => setInstances(Number(e.target.value))}
                                className="w-full accent-accent cursor-pointer"
                            />
                        </div>

                        {/* Database Replicas */}
                        <div>
                            <div className="flex justify-between items-center text-xs mb-1.5 font-semibold">
                                <span className="text-subtle">PostgreSQL Read Replicas</span>
                                <span className="text-fg font-mono text-sm font-bold">{dbReplicas} Nodes</span>
                            </div>
                            <input
                                type="range"
                                min={1}
                                max={6}
                                step={1}
                                value={dbReplicas}
                                onChange={(e) => setDbReplicas(Number(e.target.value))}
                                className="w-full accent-accent cursor-pointer"
                            />
                        </div>

                        {/* Toggles */}
                        <div className="grid grid-cols-2 gap-3 pt-2">
                            <button
                                onClick={() => setCdnEnabled(!cdnEnabled)}
                                className={cx(
                                    'p-3 rounded-xl border text-xs font-semibold flex items-center justify-between transition-all',
                                    cdnEnabled
                                        ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                                        : 'bg-surface-2 border-line text-subtle'
                                )}
                            >
                                <span>Edge CDN Cache</span>
                                <span>{cdnEnabled ? 'ON' : 'OFF'}</span>
                            </button>

                            <button
                                onClick={() => setCacheEnabled(!cacheEnabled)}
                                className={cx(
                                    'p-3 rounded-xl border text-xs font-semibold flex items-center justify-between transition-all',
                                    cacheEnabled
                                        ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                                        : 'bg-surface-2 border-line text-subtle'
                                )}
                            >
                                <span>Redis In-Memory</span>
                                <span>{cacheEnabled ? 'ON' : 'OFF'}</span>
                            </button>
                        </div>

                        {/* Chaos Injection */}
                        <div className="pt-2 border-t border-line space-y-2">
                            <div className="text-xs font-semibold text-subtle uppercase flex items-center gap-1.5">
                                <Flame className="h-3.5 w-3.5 text-rose-400" /> Chaos Monkey Scenarios:
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <button
                                    onClick={() => triggerChaos('none')}
                                    className={cx(
                                        'btn btn-sm text-xs font-medium',
                                        scenario === 'none' ? 'btn-primary' : 'btn-secondary'
                                    )}
                                >
                                    Normal Baseline
                                </button>
                                <button
                                    onClick={() => triggerChaos('flash_sale')}
                                    className={cx(
                                        'btn btn-sm text-xs font-medium',
                                        scenario === 'flash_sale' ? 'bg-rose-500 text-white font-bold' : 'btn-secondary'
                                    )}
                                >
                                    Flash Sale (100K RPS)
                                </button>
                                <button
                                    onClick={() => triggerChaos('cache_stampede')}
                                    className={cx(
                                        'btn btn-sm text-xs font-medium',
                                        scenario === 'cache_stampede' ? 'bg-amber-500 text-black font-bold' : 'btn-secondary'
                                    )}
                                >
                                    Cache Stampede
                                </button>
                                <button
                                    onClick={() => triggerChaos('db_primary_down')}
                                    className={cx(
                                        'btn btn-sm text-xs font-medium',
                                        scenario === 'db_primary_down' ? 'bg-red-600 text-white font-bold' : 'btn-secondary'
                                    )}
                                >
                                    Primary DB Down
                                </button>
                            </div>
                        </div>

                        <button
                            onClick={() => runSimulation()}
                            disabled={simulating}
                            className="btn btn-primary w-full py-2.5 font-bold shadow-md shadow-accent/20 flex items-center justify-center gap-2"
                        >
                            <Play className="h-4 w-4" /> Run Traffic Stress Test (+120 XP)
                        </button>
                    </Card>
                </div>

                {/* Live Telemetry & Bottleneck Warnings */}
                <div className="lg:col-span-6 space-y-4">
                    {metrics ? (
                        <div className="space-y-4 animate-rise">
                            {/* Key Performance Indicators */}
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                                <Card className="p-3 text-center border-line">
                                    <div className="text-[11px] text-subtle font-semibold uppercase">P99 Latency</div>
                                    <div className={cx(
                                        'text-xl font-extrabold tabular-nums mt-0.5',
                                        metrics.p99_latency_ms < 50 ? 'text-ok' : metrics.p99_latency_ms < 150 ? 'text-amber-400' : 'text-rose-400'
                                    )}>
                                        {metrics.p99_latency_ms} ms
                                    </div>
                                </Card>

                                <Card className="p-3 text-center border-line">
                                    <div className="text-[11px] text-subtle font-semibold uppercase">Error Rate</div>
                                    <div className={cx(
                                        'text-xl font-extrabold tabular-nums mt-0.5',
                                        metrics.error_rate_pct === 0 ? 'text-ok' : metrics.error_rate_pct < 5 ? 'text-amber-400' : 'text-rose-400'
                                    )}>
                                        {metrics.error_rate_pct}%
                                    </div>
                                </Card>

                                <Card className="p-3 text-center border-line">
                                    <div className="text-[11px] text-subtle font-semibold uppercase">CPU Load</div>
                                    <div className={cx(
                                        'text-xl font-extrabold tabular-nums mt-0.5',
                                        metrics.cpu_load_pct < 70 ? 'text-ok' : metrics.cpu_load_pct < 90 ? 'text-amber-400' : 'text-rose-400'
                                    )}>
                                        {metrics.cpu_load_pct}%
                                    </div>
                                </Card>

                                <Card className="p-3 text-center border-line">
                                    <div className="text-[11px] text-subtle font-semibold uppercase">Served RPS</div>
                                    <div className="text-xl font-extrabold tabular-nums text-accent mt-0.5">
                                        {metrics.throughput_rps?.toLocaleString()}
                                    </div>
                                </Card>
                            </div>

                            {/* Offload Stats */}
                            <Card className="card-pad border-line">
                                <div className="text-xs font-semibold text-subtle uppercase mb-2">Traffic Offload Summary</div>
                                <div className="grid grid-cols-2 gap-3 text-xs">
                                    <div className="p-2.5 rounded-lg bg-surface-2 border border-line">
                                        <div className="text-subtle">Absorbed by CDN Edge:</div>
                                        <div className="text-base font-bold text-blue-400 tabular-nums mt-0.5">
                                            {metrics.cdn_saved_rps?.toLocaleString()} RPS
                                        </div>
                                    </div>
                                    <div className="p-2.5 rounded-lg bg-surface-2 border border-line">
                                        <div className="text-subtle">Absorbed by Redis:</div>
                                        <div className="text-base font-bold text-amber-400 tabular-nums mt-0.5">
                                            {metrics.cache_saved_rps?.toLocaleString()} RPS
                                        </div>
                                    </div>
                                </div>
                            </Card>

                            {/* Bottleneck Alerts Console */}
                            <Card className="card-pad border-line space-y-2.5">
                                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-subtle">
                                    <AlertTriangle className="h-3.5 w-3.5 text-amber-400" /> Architectural Bottleneck Radar
                                </div>

                                <div className="space-y-2">
                                    {bottlenecks.map((b, i) => (
                                        <div
                                            key={i}
                                            className={cx(
                                                'p-3 rounded-xl border text-xs flex items-start gap-2.5',
                                                b.severity === 'HEALTHY'
                                                    ? 'bg-ok/10 border-ok/30 text-ok'
                                                    : b.severity === 'CRITICAL' || b.severity === 'DISASTER'
                                                    ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                                                    : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                                            )}
                                        >
                                            <div className="min-w-0 flex-1">
                                                <div className="font-bold flex items-center gap-2">
                                                    <span>{b.component}</span>
                                                    <span className="badge text-[9px] uppercase px-1.5 py-0">
                                                        {b.severity}
                                                    </span>
                                                </div>
                                                <p className="mt-0.5 leading-relaxed opacity-90">{b.detail}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </Card>
                        </div>
                    ) : (
                        <Card className="card-pad text-center py-16 space-y-3 border-dashed border-line">
                            <Activity className="h-10 w-10 text-subtle mx-auto animate-pulse" />
                            <p className="font-semibold text-fg">Ready for Architecture Simulation</p>
                            <p className="text-xs text-subtle max-w-xs mx-auto">
                                Adjust parameters on the left and click "Run Traffic Stress Test" to view real-time latency and bottleneck telemetry.
                            </p>
                        </Card>
                    )}
                </div>
            </div>
        </div>
    );
}
