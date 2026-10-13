import { useState } from 'react';
import {
    Flame, Zap, Trophy, CheckCircle2, RotateCcw, Swords, Bot, Code2, Play, Sparkles
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, CardHeader, Spinner, cx } from '../components/ui';
import { play } from '../lib/sfx';

export default function Dempsey() {
    const { data, reload } = useApi('/dempsey/status');
    const [unleashing, setUnleashing] = useState(false);

    const habits = data?.habits || [];
    const completed = data?.completed_count || 0;
    const feverActive = data?.fever_active;
    const readyToUnleash = data?.ready_to_unleash;

    const unleashRoll = async () => {
        setUnleashing(true);
        play('bell');
        setTimeout(() => play('combo'), 400);
        try {
            await api('/dempsey/unleash', { method: 'POST' });
            reload({ silent: true });
        } catch (e) {
            console.error(e);
        } finally {
            setUnleashing(false);
        }
    };

    return (
        <div className="space-y-6 animate-rise">
            <header>
                <div className="eyebrow flex items-center gap-1.5 text-orange-500">
                    <Flame className="h-4 w-4" /> Momentum Engine
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight">
                    The Dempsey Roll & 2x XP Fever
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    Ippo's signature unstoppable figure-eight combination. Complete your 4 daily training pillars (DSA solve, Focus Speedrun, Active Recall, and Agent Swarm) to unleash Fever Mode.
                </p>
            </header>

            {/* Fever Mode Status Hero */}
            <Card className={cx(
                'card-pad border text-center py-10 relative overflow-hidden transition-all',
                feverActive
                    ? 'border-orange-500 bg-gradient-to-br from-surface via-surface to-orange-500/20 shadow-[0_0_30px_-5px_rgba(249,115,22,0.3)]'
                    : 'border-line bg-surface'
            )}>
                <div className="text-6xl mb-3 animate-bounce">
                    {feverActive ? '🥊' : '🌪️'}
                </div>
                <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
                    {feverActive ? '2X XP FEVER MODE UNLEASHED!' : `${completed} of 4 Training Pillars Closed`}
                </h2>
                <p className="text-sm text-muted max-w-md mx-auto mt-1">
                    {feverActive
                        ? 'Every action, problem solve, and drill earns DOUBLE XP across your entire platform today!'
                        : 'Close all 4 habits today to ignite the Dempsey Roll and double your XP progression.'}
                </p>

                <div className="flex justify-center items-center gap-3 mt-6">
                    {readyToUnleash && !feverActive && (
                        <Button
                            variant="primary"
                            size="lg"
                            loading={unleashing}
                            icon={Zap}
                            onClick={unleashRoll}
                            className="bg-orange-600 hover:bg-orange-500 text-white font-bold px-8 shadow-lg"
                        >
                            UNLEASH DEMPSEY ROLL!
                        </Button>
                    )}
                    {feverActive && (
                        <div className="badge text-orange-400 bg-orange-500/20 text-sm font-mono font-bold px-4 py-1.5 rounded-full border border-orange-500/30">
                            🔥 2.0x XP MULTIPLIER ACTIVE TODAY
                        </div>
                    )}
                </div>
            </Card>

            {/* Habit Pillars Grid */}
            <div className="grid gap-3 sm:grid-cols-2">
                {habits.map((h) => (
                    <Card
                        key={h.id}
                        className={cx(
                            'card-pad flex items-center justify-between border transition-all',
                            h.done ? 'bg-orange-500/5 border-orange-500/30' : 'bg-surface border-line'
                        )}
                    >
                        <div className="flex items-center gap-3">
                            <span className="text-2xl">{h.done ? '🥊' : '⚪'}</span>
                            <div>
                                <h3 className="font-bold text-sm tracking-tight">{h.label}</h3>
                                <p className="text-xs text-subtle">{h.done ? 'Closed today' : 'Pending completion'}</p>
                            </div>
                        </div>
                        {h.done ? (
                            <span className="badge text-ok bg-ok/15 gap-1 font-semibold text-xs">
                                <CheckCircle2 className="h-3.5 w-3.5" /> Done
                            </span>
                        ) : (
                            <span className="badge bg-surface-2 text-subtle text-xs">
                                Incomplete
                            </span>
                        )}
                    </Card>
                ))}
            </div>
        </div>
    );
}
