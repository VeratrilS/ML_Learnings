import { useState, useEffect, useMemo } from 'react';
import {
    Flame, Zap, Target, Clock, Sparkles, ChevronRight, CheckCircle2, Play, Pause, RotateCcw,
    Calendar, ArrowDown,
} from 'lucide-react';
import { Card, ProgressBar, cx } from './ui';

const SPRINT_DAYS = [
    { day: 15, dateStr: 'Oct 15', label: 'Day 1', targetProbs: 93, cumulative: 93, focus: 'Sorting & 2 Pointers' },
    { day: 16, dateStr: 'Oct 16', label: 'Day 2', targetProbs: 93, cumulative: 186, focus: 'Prefix Sum & Matrix' },
    { day: 17, dateStr: 'Oct 17', label: 'Day 3', targetProbs: 93, cumulative: 279, focus: 'Hashing & Sliding Window' },
    { day: 18, dateStr: 'Oct 18', label: 'Day 4', targetProbs: 93, cumulative: 372, focus: 'Linked List & Stack' },
    { day: 19, dateStr: 'Oct 19', label: 'Day 5', targetProbs: 93, cumulative: 465, focus: 'Queue & Binary Search' },
    { day: 20, dateStr: 'Oct 20', label: 'Day 6', targetProbs: 93, cumulative: 558, focus: 'Bit Manipulation & Recursion' },
    { day: 21, dateStr: 'Oct 21', label: 'Day 7', targetProbs: 93, cumulative: 651, focus: 'Binary Tree & BST' },
    { day: 22, dateStr: 'Oct 22', label: 'Day 8', targetProbs: 93, cumulative: 744, focus: 'Heap & Tries' },
    { day: 23, dateStr: 'Oct 23', label: 'Day 9', targetProbs: 93, cumulative: 837, focus: 'Greedy & DP Level 1' },
    { day: 24, dateStr: 'Oct 24', label: 'Day 10', targetProbs: 93, cumulative: 930, focus: 'Graphs & Combinatorics' },
    { day: 25, dateStr: 'Oct 25', label: 'Day 11', targetProbs: 89, cumulative: 1019, focus: 'Game Theory & Advance Algos' },
];

export default function SprintRunway({ doneToday = 0, totalDone = 0, totalProbs = 1019 }) {
    const [now, setNow] = useState(() => new Date());
    const [selectedDay, setSelectedDay] = useState(15);
    const [isStopwatchRunning, setIsStopwatchRunning] = useState(true);
    const [elapsedSeconds, setElapsedSeconds] = useState(() => {
        const saved = localStorage.getItem('study:session:seconds');
        return saved ? Number(saved) : 0;
    });

    // Real-time ticking clock (ticks every 1,000ms)
    useEffect(() => {
        const timer = setInterval(() => {
            setNow(new Date());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    // Session stopwatch
    useEffect(() => {
        let interval = null;
        if (isStopwatchRunning) {
            interval = setInterval(() => {
                setElapsedSeconds((prev) => {
                    const next = prev + 1;
                    if (next % 10 === 0) {
                        localStorage.setItem('study:session:seconds', String(next));
                    }
                    return next;
                });
            }, 1000);
        }
        return () => {
            if (interval) clearInterval(interval);
        };
    }, [isStopwatchRunning]);

    // Time left today countdown
    const timeLeftToday = useMemo(() => {
        const midnight = new Date(now);
        midnight.setHours(23, 59, 59, 999);
        const diffMs = Math.max(0, midnight.getTime() - now.getTime());
        const hours = Math.floor(diffMs / (1000 * 60 * 60));
        const mins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
        const secs = Math.floor((diffMs % (1000 * 60)) / 1000);
        return `${String(hours).padStart(2, '0')}h ${String(mins).padStart(2, '0')}m ${String(secs).padStart(2, '0')}s`;
    }, [now]);

    // Format ticking clock
    const formattedClock = useMemo(() => {
        return now.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true,
        });
    }, [now]);

    // Format stopwatch duration
    const formatDuration = (sec) => {
        const h = Math.floor(sec / 3600);
        const m = Math.floor((sec % 3600) / 60);
        const s = sec % 60;
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    };

    const selectedInfo = useMemo(() => {
        return SPRINT_DAYS.find((d) => d.day === selectedDay) || SPRINT_DAYS[0];
    }, [selectedDay]);

    return (
        <Card className="relative overflow-hidden card-pad space-y-4 border-2 border-accent/30 bg-surface-1 shadow-md animate-rise">
            {/* Top Bar: Sprint Title + Live Ticking Clock + Non-stop Indicator */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-line/70">
                <div className="flex items-center gap-3">
                    <div className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-accent" />
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <h2 className="text-base sm:text-lg font-extrabold tracking-tight text-fg flex items-center gap-2">
                                <span>Non-Stop Study Sprint</span>
                                <span className="badge bg-accent text-accent-fg font-mono font-bold text-xs uppercase px-2 py-0.5">
                                    Oct 15 – 25
                                </span>
                            </h2>
                        </div>
                        <p className="text-xs text-subtle mt-0.5">
                            11 days non-stop grind · 1,019 Medium &amp; Hard problems · 93/day plan
                        </p>
                    </div>
                </div>

                {/* Live Ticking Time Widget */}
                <div className="flex flex-wrap items-center gap-2.5">
                    {/* Live Clock */}
                    <div className="flex items-center gap-2 bg-surface-2 border border-line px-3 py-1.5 rounded-lg shadow-sm">
                        <Clock className="h-3.5 w-3.5 text-accent animate-pulse" />
                        <div className="text-right">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-subtle block leading-none">
                                Current Time
                            </span>
                            <span className="font-mono text-xs sm:text-sm font-bold text-fg tabular-nums">
                                {formattedClock}
                            </span>
                        </div>
                    </div>

                    {/* Time Left Today */}
                    <div className="flex items-center gap-2 bg-surface-2 border border-line px-3 py-1.5 rounded-lg shadow-sm">
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                        <div className="text-right">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-subtle block leading-none">
                                Day Time Left
                            </span>
                            <span className="font-mono text-xs sm:text-sm font-semibold text-fg tabular-nums">
                                {timeLeftToday}
                            </span>
                        </div>
                    </div>

                    {/* Session Stopwatch */}
                    <div className="flex items-center gap-1.5 bg-accent/10 border border-accent/20 px-2.5 py-1.5 rounded-lg">
                        <div className="text-left mr-1">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-accent block leading-none">
                                Session
                            </span>
                            <span className="font-mono text-xs sm:text-sm font-bold text-accent tabular-nums">
                                {formatDuration(elapsedSeconds)}
                            </span>
                        </div>
                        <button
                            type="button"
                            onClick={() => setIsStopwatchRunning((r) => !r)}
                            className="p-1 text-accent hover:text-accent-fg hover:bg-accent rounded transition-colors"
                            title={isStopwatchRunning ? 'Pause timer' : 'Resume timer'}
                        >
                            {isStopwatchRunning ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                        </button>
                        <button
                            type="button"
                            onClick={() => {
                                setElapsedSeconds(0);
                                localStorage.setItem('study:session:seconds', '0');
                            }}
                            className="p-1 text-subtle hover:text-fg hover:bg-surface-3 rounded transition-colors"
                            title="Reset session timer"
                        >
                            <RotateCcw className="h-3 w-3" />
                        </button>
                    </div>
                </div>
            </div>

            {/* 11-Day Timeline Runway (Oct 15 to 25) with Pointing Indicator */}
            <div>
                <div className="flex items-center justify-between mb-2">
                    <span className="text-xs uppercase font-bold tracking-wider text-subtle flex items-center gap-1.5">
                        <Calendar className="h-3.5 w-3.5 text-accent" />
                        11-Day Study Runway (Oct 15 – 25)
                    </span>
                    <span className="text-[11px] text-muted font-medium">
                        Click any day to view daily target milestone
                    </span>
                </div>

                {/* Day Cards Runway */}
                <div className="grid grid-cols-11 gap-1.5 sm:gap-2 overflow-x-auto pb-1 pt-4">
                    {SPRINT_DAYS.map((sd) => {
                        const isToday = sd.day === 15; // October 15 is today!
                        const isSelected = sd.day === selectedDay;
                        const isPast = sd.day < 15;

                        return (
                            <div key={sd.day} className="relative flex flex-col items-center">
                                {/* POINTING INDICATOR: Prominently points to Day 15 (TODAY) */}
                                {isToday && (
                                    <div className="absolute -top-4 flex flex-col items-center animate-bounce z-10 pointer-events-none">
                                        <span className="text-[9px] font-black uppercase tracking-wider text-accent bg-accent/20 border border-accent/40 rounded px-1 py-0.2 shadow-sm whitespace-nowrap">
                                            TODAY
                                        </span>
                                        <ArrowDown className="h-2.5 w-2.5 text-accent -mt-0.5" />
                                    </div>
                                )}

                                <button
                                    type="button"
                                    onClick={() => setSelectedDay(sd.day)}
                                    className={cx(
                                        'w-full flex flex-col items-center justify-center p-1.5 sm:p-2 rounded-xl border text-center transition-all',
                                        isToday
                                            ? 'bg-accent/15 border-accent text-fg shadow-md ring-2 ring-accent/30 font-bold scale-[1.03]'
                                            : isSelected
                                                ? 'bg-surface-2 border-line-strong text-fg font-semibold'
                                                : isPast
                                                    ? 'bg-surface-2/40 border-line/40 text-subtle opacity-75'
                                                    : 'bg-surface-1 border-line text-muted hover:border-line-strong hover:bg-surface-2/60'
                                    )}
                                >
                                    <span className={cx('text-[10px] uppercase font-bold', isToday ? 'text-accent' : 'text-subtle')}>
                                        {sd.label}
                                    </span>
                                    <span className="text-xs sm:text-sm font-black font-mono leading-none my-0.5">
                                        {sd.day}
                                    </span>
                                    <span className="text-[9px] text-subtle font-mono">
                                        {sd.dateStr.split(' ')[0]}
                                    </span>

                                    {/* Daily progress or target pill */}
                                    <div className="mt-1 w-full">
                                        {isToday ? (
                                            <span className="inline-block w-full text-[9px] font-mono font-bold text-accent bg-accent/20 rounded py-0.5">
                                                {doneToday}/{sd.targetProbs}
                                            </span>
                                        ) : (
                                            <span className="inline-block w-full text-[9px] font-mono text-subtle bg-surface-2/80 rounded py-0.5">
                                                +{sd.targetProbs}
                                            </span>
                                        )}
                                    </div>
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Selected Day Planning Card Details */}
            <div className="bg-surface-2/50 rounded-xl border border-line/70 p-3 sm:p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <span className="badge bg-accent text-accent-fg text-[11px] font-bold">
                            {selectedInfo.label} · {selectedInfo.dateStr}
                        </span>
                        {selectedInfo.day === 15 && (
                            <span className="badge bg-ok/20 text-ok border border-ok/30 text-[10px] font-bold flex items-center gap-1">
                                <Sparkles className="h-2.5 w-2.5" /> STUDYING NOW
                            </span>
                        )}
                        <span className="text-xs font-semibold text-fg">
                            Recommended Focus: <span className="text-accent">{selectedInfo.focus}</span>
                        </span>
                    </div>
                    <div className="text-xs text-subtle flex items-center gap-3">
                        <span>Daily Target: <strong className="text-fg font-mono">{selectedInfo.targetProbs} problems</strong></span>
                        <span>·</span>
                        <span>Cumulative Goal: <strong className="text-fg font-mono">{selectedInfo.cumulative} / {totalProbs}</strong></span>
                        <span>·</span>
                        <span>Sprint Completion: <strong className="text-accent font-mono">{Math.round((selectedInfo.cumulative / totalProbs) * 100)}%</strong></span>
                    </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right">
                        <span className="text-[10px] uppercase font-bold text-subtle block">Today&apos;s Solved</span>
                        <span className="font-mono text-sm font-bold text-fg">
                            {doneToday} <span className="text-subtle font-normal">/ {selectedInfo.targetProbs}</span>
                        </span>
                    </div>
                    <div className="w-24">
                        <ProgressBar value={Math.min(100, Math.round((doneToday / selectedInfo.targetProbs) * 100))} className="h-2" color="var(--accent)" />
                    </div>
                </div>
            </div>
        </Card>
    );
}
