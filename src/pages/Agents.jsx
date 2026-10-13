import { useState } from 'react';
import {
    Bot, Cpu, Zap, Send, Copy, Check, Clock, Terminal
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, Spinner, cx } from '../components/ui';
import Markdown from '../components/Markdown';

export default function Agents() {
    const rosterApi = useApi('/agents/roster');
    const historyApi = useApi('/agents/history');
    const [selectedAgent, setSelectedAgent] = useState('swarm');
    const [mission, setMission] = useState('');
    const [allOut, setAllOut] = useState(true);
    const [parallel, setParallel] = useState(true);
    const [running, setRunning] = useState(false);
    const [currentRun, setCurrentRun] = useState(null);
    const [copiedIndex, setCopiedIndex] = useState(null);

    const roster = rosterApi.data || [];

    const PRESETS = [
        { label: '🚀 Brainstorm & Investigate New Features', prompt: 'Brainstorm and investigate revolutionary addictive and productive features for our developer platform.' },
        { label: '🧩 2D Dynamic Programming Blueprint', prompt: 'Deconstruct 2D DP on subsequences (e.g. Longest Common Subsequence & Edit Distance) with optimal state compression and edge cases.' },
        { label: '⚡ Distributed Rate Limiter Architecture', prompt: 'Design a distributed rate limiter supporting 500,000 RPS using sliding window log/counter, Redis, and fallback circuits.' },
        { label: '🔥 48-Hour OA Emergency Sprint', prompt: 'I have an online assessment in 48 hours. Formulate a high-yield triage roadmap covering top frequency patterns.' },
        { label: '🎯 FAANG Interview STAR Formulation', prompt: 'Draft a compelling STAR behavioral story for optimizing an API latency bottleneck from 450ms down to 35ms.' },
    ];

    const runMission = async (customMission) => {
        const text = (customMission || mission).trim();
        if (!text) return;
        setRunning(true);
        try {
            const isSwarm = selectedAgent === 'swarm';
            const res = await api('/agents/dispatch', {
                method: 'POST',
                body: {
                    agent_id: isSwarm ? 'grandmaster' : selectedAgent,
                    mission: text,
                    all_out: isSwarm || allOut,
                    parallel: isSwarm || parallel,
                },
            });
            if (res.data) {
                setCurrentRun(res.data);
                historyApi.reload({ silent: true });
            }
        } catch (e) {
            console.error('Agent dispatch failed', e);
        } finally {
            setRunning(false);
        }
    };

    const copyCode = (text, idx) => {
        navigator.clipboard.writeText(text);
        setCopiedIndex(idx);
        setTimeout(() => setCopiedIndex(null), 2000);
    };

    return (
        <div className="space-y-6 animate-rise">
            <header>
                <div className="eyebrow flex items-center gap-1.5 text-accent">
                    <Bot className="h-4 w-4" /> Autonomous Swarm Ops
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight">
                    Parallel AI Agents War Room
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Dispatch 5 specialized agents concurrently in parallel worker threads. The Grandmaster, Sentinel, Principal, Sensei, and Scout collaborate, audit, and go all out on your goals.
                </p>
            </header>

            {/* Agent Roster Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
                <button
                    onClick={() => { setSelectedAgent('swarm'); setAllOut(true); setParallel(true); }}
                    className={cx(
                        'p-3 rounded-2xl border text-left transition-all relative overflow-hidden',
                        selectedAgent === 'swarm'
                            ? 'bg-accent-soft/40 border-accent shadow-[0_0_20px_-5px_var(--accent)] ring-1 ring-accent'
                            : 'bg-surface border-line hover:border-line-strong'
                    )}
                >
                    <div className="flex items-center justify-between">
                        <span className="text-2xl">⚡</span>
                        <span className="badge text-accent bg-accent-soft text-[10px] uppercase font-mono">Parallel</span>
                    </div>
                    <div className="mt-2 font-bold text-sm">ALL OUT SWARM</div>
                    <div className="text-[11px] text-subtle truncate">5 Agents Concurrently</div>
                </button>

                {roster.map((agent) => (
                    <button
                        key={agent.id}
                        onClick={() => setSelectedAgent(agent.id)}
                        className={cx(
                            'p-3 rounded-2xl border text-left transition-all',
                            selectedAgent === agent.id
                                ? 'bg-surface-2 border-fg/40 shadow-sm ring-1 ring-fg/20'
                                : 'bg-surface border-line hover:border-line-strong'
                        )}
                    >
                        <div className="flex items-center justify-between">
                            <span className="text-2xl">{agent.avatar}</span>
                            <span className="text-[10px] text-subtle font-mono">{agent.badge}</span>
                        </div>
                        <div className="mt-2 font-semibold text-sm truncate">{agent.name}</div>
                        <div className="text-[11px] text-muted truncate">{agent.tag}</div>
                    </button>
                ))}
            </div>

            {/* Mission Dispatch Console */}
            <Card className="card-pad border-accent/20 bg-gradient-to-br from-surface via-surface to-accent-soft/10">
                <div className="flex items-center justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                        <Terminal className="h-4 w-4 text-accent" />
                        <span className="text-sm font-bold tracking-tight">Mission Directive</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <label className="flex items-center gap-1.5 text-xs font-medium cursor-pointer">
                            <input
                                type="checkbox"
                                checked={parallel}
                                onChange={(e) => setParallel(e.target.checked)}
                                className="rounded accent-accent"
                            />
                            <span className="flex items-center gap-1">
                                <Cpu className="h-3.5 w-3.5 text-accent" /> Parallel Threads
                            </span>
                        </label>
                        <label className="flex items-center gap-1.5 text-xs font-medium cursor-pointer">
                            <input
                                type="checkbox"
                                checked={allOut}
                                onChange={(e) => setAllOut(e.target.checked)}
                                className="rounded accent-accent"
                            />
                            <span className="flex items-center gap-1">
                                <Zap className="h-3.5 w-3.5 text-amber-500" /> Go All Out
                            </span>
                        </label>
                    </div>
                </div>

                <div className="flex gap-2">
                    <input
                        type="text"
                        value={mission}
                        onChange={(e) => setMission(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') runMission(); }}
                        placeholder="Enter any challenge, algorithm, system design, or feature to investigate…"
                        className="input flex-1 font-medium text-sm"
                    />
                    <Button
                        variant="primary"
                        loading={running}
                        icon={running ? Spinner : Send}
                        onClick={() => runMission()}
                    >
                        {running ? 'Executing Swarm…' : 'Dispatch'}
                    </Button>
                </div>

                {/* Quick Presets */}
                <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-line">
                    <span className="text-xs text-subtle self-center mr-1">Quick Presets:</span>
                    {PRESETS.map((p) => (
                        <button
                            key={p.label}
                            onClick={() => { setMission(p.prompt); runMission(p.prompt); }}
                            className="btn btn-ghost btn-sm text-[11px] h-7 bg-surface-2 border border-line hover:border-accent/40"
                        >
                            {p.label}
                        </button>
                    ))}
                </div>
            </Card>

            {/* Active Swarm Run Display */}
            {running && (
                <div className="card card-pad text-center py-12 border-accent/30 bg-accent-soft/10">
                    <div className="flex justify-center items-center gap-2 mb-3">
                        <Spinner className="h-6 w-6 text-accent" />
                        <span className="font-bold text-lg">Agents Deploying in Parallel…</span>
                    </div>
                    <div className="flex justify-center gap-4 text-xs text-subtle font-mono">
                        <span className="animate-pulse">Thread 1: Grandmaster</span>
                        <span className="animate-pulse">Thread 2: Sentinel</span>
                        <span className="animate-pulse">Thread 3: Principal</span>
                        <span className="animate-pulse">Thread 4: Sensei</span>
                        <span className="animate-pulse">Thread 5: Scout</span>
                    </div>
                </div>
            )}

            {currentRun && !running && (
                <div className="space-y-4">
                    <div className="flex items-center justify-between p-3.5 rounded-xl border border-ok/30 bg-ok/10 text-xs">
                        <div className="flex items-center gap-2 font-medium">
                            <span className="text-base">🚀</span>
                            <span>{currentRun.summary}</span>
                        </div>
                        <span className="badge text-ok bg-ok/20 font-bold">+{currentRun.xp_reward} XP Awarded</span>
                    </div>

                    <div className="space-y-4">
                        {currentRun.stages.map((stage, idx) => (
                            <Card key={idx} className="card-pad border-line/80 relative">
                                <div className="flex items-start justify-between gap-3 mb-3">
                                    <div className="flex items-center gap-2.5">
                                        <span className="text-2xl">{stage.avatar || '🤖'}</span>
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <h3 className="font-bold text-sm tracking-tight">{stage.title || stage.agent}</h3>
                                                {stage.badge && <span className="badge text-xs">{stage.badge}</span>}
                                            </div>
                                            <p className="text-[11px] text-subtle font-mono">
                                                {stage.role} {stage.thread_id ? `· ${stage.thread_id}` : ''} {stage.execution_time_ms ? `· ${stage.execution_time_ms}ms` : ''}
                                            </p>
                                        </div>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        icon={copiedIndex === idx ? Check : Copy}
                                        onClick={() => copyCode(stage.content, idx)}
                                    >
                                        {copiedIndex === idx ? 'Copied' : 'Copy'}
                                    </Button>
                                </div>
                                <div className="text-sm border-t border-line pt-3 mt-1">
                                    <Markdown>{stage.content}</Markdown>
                                </div>
                            </Card>
                        ))}
                    </div>
                </div>
            )}

            {/* Mission History */}
            {historyApi.data && historyApi.data.length > 0 && (
                <div className="space-y-2 pt-4">
                    <div className="flex items-center gap-2 text-xs font-bold text-subtle uppercase tracking-wider">
                        <Clock className="h-3.5 w-3.5" /> Recent Swarm Missions
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                        {historyApi.data.slice(0, 6).map((h) => (
                            <Card
                                key={h.id}
                                className="p-3 hover:border-line-strong transition-colors cursor-pointer"
                                onClick={async () => {
                                    const d = await api(`/agents/mission/${h.id}`);
                                    if (d.data) setCurrentRun(d.data);
                                }}
                            >
                                <div className="flex items-center justify-between text-xs">
                                    <span className="font-semibold truncate flex-1">{h.mission_title}</span>
                                    <span className="badge font-mono text-[10px] ml-2 shrink-0">{h.agent_id}</span>
                                </div>
                                <p className="text-[11px] text-muted mt-1 truncate">{h.summary}</p>
                            </Card>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
