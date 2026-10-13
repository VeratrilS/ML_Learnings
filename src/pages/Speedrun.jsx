import { useCallback, useEffect, useRef, useState } from 'react';
import {
    Flame, Play, Pause, RotateCcw, Zap, Shield, Plus, Check, Music
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, CardHeader, cx } from '../components/ui';
import { play } from '../lib/sfx';
import * as ambient from '../lib/ambient';

export default function Speedrun() {
    const statsApi = useApi('/speedrun/stats');
    const parkingApi = useApi('/speedrun/parking');

    const [durationMins, setDurationMins] = useState(25);
    const [secondsLeft, setSecondsLeft] = useState(25 * 60);
    const [running, setRunning] = useState(false);
    const [combo, setCombo] = useState(1.0);
    const [ambientTrack, setAmbientTrack] = useState('rain');
    const [ambientPlaying, setAmbientPlaying] = useState(false);
    const [newThought, setNewThought] = useState('');
    const [completedRun, setCompletedRun] = useState(null);

    const timerRef = useRef(null);

    const onSessionComplete = useCallback(async () => {
        setRunning(false);
        play('combo');
        ambient.stop();

        try {
            const res = await api('/speedrun/complete', {
                method: 'POST',
                body: { minutes: durationMins, combo },
            });
            if (res.data) {
                setCompletedRun(res.data);
                setCombo((c) => Math.min(3.5, Number((c + 0.5).toFixed(1))));
                statsApi.reload({ silent: true });
            }
        } catch (e) {
            console.error('Session complete error', e);
        }
    }, [durationMins, combo, statsApi]);

    // Timer countdown loop
    useEffect(() => {
        if (running) {
            timerRef.current = setInterval(() => {
                setSecondsLeft((prev) => {
                    if (prev <= 1) {
                        clearInterval(timerRef.current);
                        onSessionComplete();
                        return 0;
                    }
                    return prev - 1;
                });
            }, 1000);
        } else {
            clearInterval(timerRef.current);
        }
        return () => clearInterval(timerRef.current);
    }, [running, onSessionComplete]);

    const selectDuration = (mins) => {
        setRunning(false);
        setDurationMins(mins);
        setSecondsLeft(mins * 60);
    };

    const toggleTimer = () => {
        if (!running) {
            play('bell');
            if (ambientPlaying) {
                ambient.start(ambientTrack);
            }
        } else {
            ambient.stop();
        }
        setRunning(!running);
    };

    const resetTimer = () => {
        setRunning(false);
        setSecondsLeft(durationMins * 60);
        ambient.stop();
    };

    const toggleAmbient = (track) => {
        if (ambientPlaying && ambientTrack === track) {
            ambient.stop();
            setAmbientPlaying(false);
        } else {
            setAmbientTrack(track);
            setAmbientPlaying(true);
            ambient.start(track);
        }
    };

    const addParkingThought = async () => {
        if (!newThought.trim()) return;
        try {
            await api('/speedrun/parking', {
                method: 'POST',
                body: { thought: newThought.trim() },
            });
            setNewThought('');
            parkingApi.reload({ silent: true });
        } catch (e) {
            console.error(e);
        }
    };

    const resolveThought = async (id) => {
        try {
            await api(`/speedrun/parking/${id}`, { method: 'DELETE' });
            parkingApi.reload({ silent: true });
        } catch (e) {
            console.error(e);
        }
    };

    const mins = Math.floor(secondsLeft / 60);
    const secs = secondsLeft % 60;
    const progress = 1 - (secondsLeft / (durationMins * 60));
    const strokeDashoffset = 283 - (283 * progress);

    return (
        <div className="space-y-6 animate-rise">
            <header>
                <div className="eyebrow flex items-center gap-1.5 text-amber-500">
                    <Flame className="h-4 w-4" /> Focus Speedrun Arena
                </div>
                <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight">
                    Time-Trial Focus & Boss Raid
                </h1>
                <p className="text-sm text-muted mt-1 max-w-2xl">
                    High-energy sprint intervals. Maintain uninterrupted focus to build up to a 3.0x combo multiplier and deal direct damage to the weekly Gym Boss.
                </p>
            </header>

            {/* Quick Stat Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-amber-500 tabular-nums">{combo}x</div>
                    <div className="text-xs text-subtle mt-0.5">Active Combo Multiplier</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold tabular-nums">{statsApi.data?.today_minutes || 0}m</div>
                    <div className="text-xs text-subtle mt-0.5">Today's Focus Logged</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-rose-500 tabular-nums">-{statsApi.data?.today_damage || 0} HP</div>
                    <div className="text-xs text-subtle mt-0.5">Boss Damage Dealt</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-ok tabular-nums">+{statsApi.data?.total_xp || 0}</div>
                    <div className="text-xs text-subtle mt-0.5">Total Speedrun XP</div>
                </Card>
            </div>

            {/* Circular Timer Hero */}
            <Card className="card-pad flex flex-col items-center justify-center py-10 relative overflow-hidden bg-gradient-to-b from-surface to-surface-2/40">
                {/* Sprint Selector */}
                <div className="flex gap-2 mb-6">
                    {[15, 25, 45].map((m) => (
                        <button
                            key={m}
                            onClick={() => selectDuration(m)}
                            className={cx(
                                'btn btn-sm text-xs font-bold px-4 h-8 rounded-xl transition-all',
                                durationMins === m
                                    ? 'bg-amber-500 text-black shadow-sm scale-105'
                                    : 'btn-secondary text-subtle'
                            )}
                        >
                            {m}m {m === 15 ? 'Sprint' : m === 25 ? 'Classic' : 'Deep'}
                        </button>
                    ))}
                </div>

                {/* SVG Radial Dial */}
                <div className="relative w-64 h-64 flex items-center justify-center">
                    <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                        <circle
                            cx="50"
                            cy="50"
                            r="45"
                            className="stroke-surface-3"
                            strokeWidth="6"
                            fill="transparent"
                        />
                        <circle
                            cx="50"
                            cy="50"
                            r="45"
                            className="stroke-amber-500 transition-all duration-500"
                            strokeWidth="6"
                            strokeDasharray="283"
                            strokeDashoffset={strokeDashoffset}
                            strokeLinecap="round"
                            fill="transparent"
                        />
                    </svg>

                    <div className="absolute flex flex-col items-center text-center">
                        <div className="text-5xl font-mono font-bold tracking-tight tabular-nums">
                            {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
                        </div>
                        <span className="text-xs font-semibold text-amber-500 mt-1 uppercase tracking-wider flex items-center gap-1">
                            <Zap className="h-3 w-3" /> {combo}x Multiplier
                        </span>
                    </div>
                </div>

                {/* Controls */}
                <div className="flex items-center gap-3 mt-6">
                    <Button
                        variant={running ? 'secondary' : 'primary'}
                        size="lg"
                        icon={running ? Pause : Play}
                        onClick={toggleTimer}
                        className="px-8 shadow-md"
                    >
                        {running ? 'Pause Sprint' : 'Ignite Focus'}
                    </Button>
                    <Button
                        variant="ghost"
                        size="lg"
                        icon={RotateCcw}
                        onClick={resetTimer}
                        title="Reset Timer"
                    />
                </div>

                {/* Ambient Soundscapes */}
                <div className="flex flex-wrap items-center justify-center gap-2 mt-8 pt-6 border-t border-line w-full max-w-md">
                    <span className="text-xs text-subtle flex items-center gap-1 mr-1">
                        <Music className="h-3.5 w-3.5" /> Ambience:
                    </span>
                    {ambient.AMBIENTS.map((a) => (
                        <button
                            key={a.id}
                            onClick={() => toggleAmbient(a.id)}
                            className={cx(
                                'btn btn-sm text-[11px] h-7 rounded-lg border',
                                ambientPlaying && ambientTrack === a.id
                                    ? 'bg-accent text-accent-fg border-accent'
                                    : 'bg-surface-2 border-line text-subtle hover:text-fg'
                            )}
                        >
                            {a.label}
                        </button>
                    ))}
                </div>
            </Card>

            {completedRun && (
                <div className="card card-pad border-ok/30 bg-ok/10 flex items-center justify-between animate-rise">
                    <div className="flex items-center gap-2.5">
                        <span className="text-2xl">🎉</span>
                        <div>
                            <div className="font-bold text-sm">Sprint Completed!</div>
                            <div className="text-xs text-muted">
                                Dealt {completedRun.boss_damage} damage to Gym Boss · Combo Multiplier {completedRun.combo}x
                            </div>
                        </div>
                    </div>
                    <span className="badge text-ok bg-ok/20 font-bold text-sm">+{completedRun.xp_earned} XP</span>
                </div>
            )}

            {/* Distraction Parking Lot */}
            <Card className="card-pad">
                <CardHeader
                    title="Distraction Parking Lot"
                    subtitle="Park intrusive thoughts without breaking flow"
                    icon={Shield}
                />

                <div className="flex gap-2 mb-3">
                    <input
                        type="text"
                        value={newThought}
                        onChange={(e) => setNewThought(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') addParkingThought(); }}
                        placeholder="Got an intrusive thought? Type and park it here…"
                        className="input flex-1 text-sm"
                    />
                    <Button variant="secondary" icon={Plus} onClick={addParkingThought}>
                        Park Thought
                    </Button>
                </div>

                <div className="space-y-1.5">
                    {parkingApi.data && parkingApi.data.length > 0 ? (
                        parkingApi.data.map((t) => (
                            <div key={t.id} className="flex items-center justify-between p-2 rounded-lg bg-surface-2/60 border border-line text-xs">
                                <span className="truncate flex-1 font-medium">{t.thought}</span>
                                <Button variant="ghost" size="sm" icon={Check} onClick={() => resolveThought(t.id)}>
                                    Clear
                                </Button>
                            </div>
                        ))
                    ) : (
                        <p className="text-xs text-subtle text-center py-4">Mind clear. Zero distractions parked.</p>
                    )}
                </div>
            </Card>
        </div>
    );
}
