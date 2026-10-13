import { useState } from 'react';
import { Bot, Cpu, Zap, ArrowRight, CheckCircle2 } from 'lucide-react';
import { api } from '../lib/api';
import { navigate, useApi } from '../lib/hooks';
import { Button, Card, CardHeader, Spinner } from './ui';

export default function AgentSwarmCard() {
    const { reload } = useApi('/agents/history');
    const [running, setRunning] = useState(false);
    const [lastResult, setLastResult] = useState(null);

    const quickAllOut = async () => {
        setRunning(true);
        try {
            const res = await api('/agents/dispatch', {
                method: 'POST',
                body: { mission: 'Brainstorm and audit new high-yield features for this platform', all_out: true, parallel: true },
            });
            if (res.data) {
                setLastResult(res.data);
                reload({ silent: true });
            }
        } catch (e) {
            console.error(e);
        } finally {
            setRunning(false);
        }
    };

    return (
        <Card className="card-pad relative overflow-hidden border-accent/20 bg-gradient-to-br from-surface to-accent-soft/20">
            <CardHeader
                title="Agent Swarm"
                subtitle="5 Parallel Autonomous AI Agents"
                icon={Bot}
                action={
                    <span className="badge text-accent bg-accent-soft gap-1 font-mono text-[11px]">
                        <Cpu className="h-3 w-3 animate-pulse" /> 5 THREADS
                    </span>
                }
            />

            <p className="text-xs text-muted mb-4 leading-relaxed">
                Grandmaster, Sentinel, Principal, Sensei, and Scout operate concurrently in parallel worker threads to audit, solve, and innovate.
            </p>

            <div className="grid grid-cols-5 gap-1.5 p-2 rounded-xl bg-surface-2/60 border border-line mb-4">
                {[
                    { name: 'Grandmaster', avatar: '🧠', tag: 'Algo' },
                    { name: 'Sentinel', avatar: '🛡️', tag: 'Bugs' },
                    { name: 'Principal', avatar: '⚡', tag: 'Scale' },
                    { name: 'Sensei', avatar: '🔥', tag: 'Focus' },
                    { name: 'Scout', avatar: '🎯', tag: 'Intel' },
                ].map((a) => (
                    <div key={a.name} className="flex flex-col items-center text-center p-1 rounded-lg bg-surface/50">
                        <span className="text-base sm:text-lg">{a.avatar}</span>
                        <span className="text-[10px] font-bold mt-0.5 truncate w-full">{a.tag}</span>
                    </div>
                ))}
            </div>

            {lastResult && (
                <div className="mb-4 p-2.5 rounded-xl border border-ok/30 bg-ok/10 text-xs flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-ok shrink-0" />
                    <span className="truncate flex-1 font-medium">{lastResult.summary}</span>
                    <span className="badge text-ok bg-ok/20 font-bold shrink-0">+{lastResult.xp_reward} XP</span>
                </div>
            )}

            <div className="flex items-center gap-2">
                <Button
                    variant="primary"
                    size="sm"
                    loading={running}
                    icon={running ? Spinner : Zap}
                    onClick={quickAllOut}
                    className="flex-1 shadow-sm"
                >
                    {running ? 'Parallel Swarm Running…' : 'Go All Out (Parallel)'}
                </Button>
                <Button
                    variant="secondary"
                    size="sm"
                    icon={ArrowRight}
                    onClick={() => navigate('agents')}
                >
                    War Room
                </Button>
            </div>
        </Card>
    );
}
