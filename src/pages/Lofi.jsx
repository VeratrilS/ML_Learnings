import { useEffect, useRef, useState } from 'react';
import {
    Headphones, Play, Pause, Volume2, Clock
} from 'lucide-react';
import { Button, Card, useToast, cx } from '../components/ui';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';

class GenerativeSynthEngine {
    constructor() {
        this.ctx = null;
        this.activeNodes = [];
        this.gainNode = null;
        this.volume = 0.5;
        this.timerInterval = null;
    }

    init() {
        if (!this.ctx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            this.ctx = new AudioCtx();
            this.gainNode = this.ctx.createGain();
            this.gainNode.gain.setValueAtTime(this.volume, this.ctx.currentTime);
            this.gainNode.connect(this.ctx.destination);
        }
        if (this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
    }

    setVolume(val) {
        this.volume = val;
        if (this.gainNode && this.ctx) {
            this.gainNode.gain.setValueAtTime(val, this.ctx.currentTime);
        }
    }

    stop() {
        if (this.timerInterval) clearInterval(this.timerInterval);
        this.activeNodes.forEach((n) => {
            try { n.stop?.(); n.disconnect?.(); } catch {}
        });
        this.activeNodes = [];
    }

    playPreset(preset) {
        this.init();
        this.stop();

        const params = preset.params;
        const now = this.ctx.currentTime;

        if (params.type === 'binaural') {
            // Stereo Binaural Beat Generator
            const leftOsc = this.ctx.createOscillator();
            const rightOsc = this.ctx.createOscillator();
            const leftPanner = this.ctx.createStereoPanner?.() || this.ctx.createGain();
            const rightPanner = this.ctx.createStereoPanner?.() || this.ctx.createGain();

            leftOsc.type = 'sine';
            rightOsc.type = 'sine';
            leftOsc.frequency.setValueAtTime(params.baseFreq, now);
            rightOsc.frequency.setValueAtTime(params.baseFreq + params.beatFreq, now);

            if (leftPanner.pan) leftPanner.pan.setValueAtTime(-1, now);
            if (rightPanner.pan) rightPanner.pan.setValueAtTime(1, now);

            leftOsc.connect(leftPanner);
            rightOsc.connect(rightPanner);
            leftPanner.connect(this.gainNode);
            rightPanner.connect(this.gainNode);

            leftOsc.start(now);
            rightOsc.start(now);
            this.activeNodes.push(leftOsc, rightOsc);
        } else if (params.type === 'drone') {
            // Low cyberpunk synth sub-oscillator with modulated filter
            const osc = this.ctx.createOscillator();
            const filter = this.ctx.createBiquadFilter();

            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(params.baseFreq, now);

            filter.type = 'lowpass';
            filter.frequency.setValueAtTime(params.filterFreq, now);
            filter.Q.setValueAtTime(4, now);

            osc.connect(filter);
            filter.connect(this.gainNode);
            osc.start(now);
            this.activeNodes.push(osc, filter);
        } else if (params.type === 'noise') {
            // Buffer-based continuous noise generator (Pink / Brown)
            const bufferSize = this.ctx.sampleRate * 2;
            const noiseBuffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
            const output = noiseBuffer.getChannelData(0);

            let lastOut = 0.0;
            for (let i = 0; i < bufferSize; i++) {
                const white = Math.random() * 2 - 1;
                if (params.noiseColor === 'brown') {
                    output[i] = (lastOut + (0.02 * white)) / 1.02;
                    lastOut = output[i];
                    output[i] *= 3.5;
                } else {
                    output[i] = (lastOut + (0.05 * white)) / 1.05;
                    lastOut = output[i];
                    output[i] *= 2.0;
                }
            }

            const whiteNoise = this.ctx.createBufferSource();
            whiteNoise.buffer = noiseBuffer;
            whiteNoise.loop = true;
            whiteNoise.connect(this.gainNode);
            whiteNoise.start(now);
            this.activeNodes.push(whiteNoise);
        } else if (params.type === 'asmr') {
            // Periodic subtle mechanical keystroke impulses
            const playClick = () => {
                if (!this.ctx) return;
                const clickOsc = this.ctx.createOscillator();
                const clickGain = this.ctx.createGain();
                const t = this.ctx.currentTime;
                clickOsc.type = 'triangle';
                clickOsc.frequency.setValueAtTime(700 + Math.random() * 200, t);
                clickGain.gain.setValueAtTime(0.08, t);
                clickGain.gain.exponentialRampToValueAtTime(0.001, t + 0.03);
                clickOsc.connect(clickGain);
                clickGain.connect(this.gainNode);
                clickOsc.start(t);
                clickOsc.stop(t + 0.03);
            };

            this.timerInterval = setInterval(() => {
                playClick();
                if (Math.random() > 0.4) setTimeout(playClick, 100);
            }, 60000 / params.bpm);
        }
    }
}

const synthEngine = new GenerativeSynthEngine();

export default function Lofi() {
    const toast = useToast();
    const presetsRes = useApi('/lofi/presets');
    const statsRes = useApi('/lofi/stats');

    const presets = presetsRes.data?.presets || [];
    const stats = statsRes.data?.stats || { total_minutes: 0, total_hours: 0, sessions_count: 0, total_xp: 0 };

    const [activePreset, setActivePreset] = useState(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [volume, setVolume] = useState(0.4);
    const [sessionSec, setSessionSec] = useState(0);
    const sessionTimerRef = useRef(null);

    // Default select first preset
    useEffect(() => {
        if (!activePreset && presets.length > 0) {
            setActivePreset(presets[0]);
        }
    }, [presets, activePreset]);

    useEffect(() => {
        if (isPlaying) {
            sessionTimerRef.current = setInterval(() => {
                setSessionSec((prev) => prev + 1);
            }, 1000);
        } else {
            if (sessionTimerRef.current) clearInterval(sessionTimerRef.current);
        }
        return () => {
            if (sessionTimerRef.current) clearInterval(sessionTimerRef.current);
        };
    }, [isPlaying]);

    // Handle audio toggle
    const togglePlayback = (presetToPlay = activePreset) => {
        if (!presetToPlay) return;

        if (isPlaying && activePreset?.id === presetToPlay.id) {
            synthEngine.stop();
            setIsPlaying(false);

            // Log session if listened for at least 1 minute
            if (sessionSec >= 60) {
                const minutes = Math.floor(sessionSec / 60);
                api('/lofi/session/log', {
                    method: 'POST',
                    body: { preset_id: activePreset.id, duration_min: minutes },
                }).then(() => {
                    toast.success('Focus Logged', `Completed ${minutes} min focus session! XP awarded.`);
                    statsRes.reload();
                    setSessionSec(0);
                }).catch(() => {});
            }
        } else {
            setActivePreset(presetToPlay);
            synthEngine.setVolume(volume);
            synthEngine.playPreset(presetToPlay);
            setIsPlaying(true);
            toast.info('Soundscape Active', `Streaming ${presetToPlay.title}`);
        }
    };

    const handleVolumeChange = (e) => {
        const val = parseFloat(e.target.value);
        setVolume(val);
        synthEngine.setVolume(val);
    };

    return (
        <div className="space-y-6 animate-fade-in max-w-5xl mx-auto pb-12">
            {/* Header Hero */}
            <div className="relative overflow-hidden rounded-3xl border border-line bg-surface/80 p-6 md:p-8 backdrop-blur-xl shadow-2xl">
                <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
                            <Headphones className="w-3.5 h-3.5" /> Generative Neural Focus Studio
                        </div>
                        <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-fg flex items-center gap-3">
                            Neural Lo-Fi
                        </h1>
                        <p className="text-sm md:text-base text-subtle mt-2 max-w-xl">
                            100% client-synthesized audio environments (Binaural Beats, Cyberpunk Drones, Rain Pink Noise, Mechanical ASMR) designed to lock you into flow state.
                        </p>
                    </div>

                    {/* Stats pills */}
                    <div className="grid grid-cols-3 gap-3 bg-surface-2/60 p-3 rounded-2xl border border-line">
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Focus Hours</div>
                            <div className="text-lg font-black text-indigo-400 tabular-nums">{stats.total_hours}h</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Sessions</div>
                            <div className="text-lg font-black text-fg tabular-nums">{stats.sessions_count}</div>
                        </div>
                        <div className="text-center px-2">
                            <div className="text-[11px] text-subtle font-medium">Earned XP</div>
                            <div className="text-lg font-black text-accent tabular-nums">+{stats.total_xp}</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Live Player Deck */}
            <Card className="p-6 border-line bg-surface space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-center gap-4">
                        <div className="w-14 h-14 rounded-2xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shadow-inner">
                            <Headphones className="w-7 h-7" />
                        </div>
                        <div>
                            <div className="text-xs font-mono text-indigo-400 uppercase font-semibold">
                                {activePreset?.category || 'Neural Audio'}
                            </div>
                            <h2 className="text-xl font-extrabold text-fg">{activePreset?.title}</h2>
                            <div className="flex items-center gap-2 text-xs text-subtle mt-0.5">
                                <Clock className="w-3.5 h-3.5" />
                                <span>Session Time: {Math.floor(sessionSec / 60)}:{(sessionSec % 60).toString().padStart(2, '0')}</span>
                            </div>
                        </div>
                    </div>

                    {/* Controls */}
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <Volume2 className="w-4 h-4 text-subtle" />
                            <input
                                type="range"
                                min="0"
                                max="1"
                                step="0.05"
                                value={volume}
                                onChange={handleVolumeChange}
                                className="w-24 accent-indigo-500"
                            />
                        </div>

                        <Button
                            onClick={() => togglePlayback(activePreset)}
                            className={cx(
                                'px-6 py-3 rounded-2xl text-sm font-bold gap-2 shadow-lg transition-all',
                                isPlaying
                                    ? 'bg-rose-500 hover:bg-rose-600 text-white shadow-rose-500/20'
                                    : 'btn-primary shadow-indigo-500/20'
                            )}
                        >
                            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                            {isPlaying ? 'Pause Soundscape' : 'Start Flow State'}
                        </Button>
                    </div>
                </div>
            </Card>

            {/* Presets Grid */}
            <div className="space-y-3">
                <h3 className="text-sm font-bold text-subtle uppercase tracking-wider px-1">Soundscape Library</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {presets.map((p) => {
                        const isCurrentActive = activePreset?.id === p.id;
                        const isCurrentPlaying = isCurrentActive && isPlaying;

                        return (
                            <button
                                key={p.id}
                                type="button"
                                onClick={() => togglePlayback(p)}
                                className={cx(
                                    'text-left p-4 rounded-2xl border transition-all relative overflow-hidden group',
                                    isCurrentActive
                                        ? 'bg-indigo-500/10 border-indigo-500/40 shadow-md shadow-indigo-500/5'
                                        : 'bg-surface hover:bg-surface-2 border-line'
                                )}
                            >
                                <div className="flex items-center justify-between gap-2 mb-2">
                                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-surface-2 text-subtle border border-line uppercase">
                                        {p.category}
                                    </span>
                                    <div className={cx(
                                        'w-7 h-7 rounded-xl flex items-center justify-center transition-colors',
                                        isCurrentPlaying ? 'bg-indigo-500 text-white' : 'bg-surface-2 text-subtle group-hover:text-fg'
                                    )}>
                                        {isCurrentPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                                    </div>
                                </div>
                                <h4 className="font-bold text-fg text-sm">{p.title}</h4>
                                <p className="text-xs text-subtle line-clamp-2 mt-1">{p.desc}</p>
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
