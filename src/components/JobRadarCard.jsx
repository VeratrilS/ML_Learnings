import { useEffect, useMemo, useState } from 'react';
import {
    Briefcase, Radio, Zap, ArrowRight, CheckCircle2, Clock, Sparkles,
    ShieldCheck, RefreshCw, Send, Building2, Flame, Bot, Check, AlertCircle, BellRing,
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Skeleton, cx, useToast } from './ui';
import { play } from '../lib/sfx';

function fmtCtc(val) {
    if (!val || Number(val) === 0) return 'CTC not listed';
    return `₹${Number(val).toFixed(1)} LPA (est.)`;
}

function useCountdown(targetIso) {
    const [timeLeft, setTimeLeft] = useState('');

    useEffect(() => {
        if (!targetIso) return;
        const target = new Date(targetIso).getTime();

        const update = () => {
            const now = Date.now();
            const diff = target - now;
            if (diff <= 0) {
                setTimeLeft('Check in progress…');
                return;
            }
            const mins = Math.floor(diff / 60000);
            const secs = Math.floor((diff % 60000) / 1000);
            setTimeLeft(`${mins}m ${secs.toString().padStart(2, '0')}s`);
        };

        update();
        const interval = setInterval(update, 1000);
        return () => clearInterval(interval);
    }, [targetIso]);

    return timeLeft;
}

export default function JobRadarCard() {
    const { data, loading, reload } = useApi('/jobs/radar');
    const toast = useToast();
    const [scanning, setScanning] = useState(false);
    const [applying, setApplying] = useState(false);
    const [toggling, setToggling] = useState(false);

    const profile = data?.profile;
    const summary = data?.summary;
    const jobs = useMemo(() => data?.jobs || [], [data]);
    const countdown = useCountdown(summary?.next_hourly_scan);

    // Filter top 2027 eligible jobs with >= 15 LPA (or unlisted CTC)
    const top2027 = useMemo(() => {
        return jobs
            .filter((j) => (!j.eligible_batches || j.eligible_batches.includes('2027')) && (!j.ctc_lpa || j.ctc_lpa === 0 || j.ctc_lpa >= (profile?.min_ctc_lpa || 15)))
            .slice(0, 4);
    }, [jobs, profile]);

    const handleRunScan = async () => {
        setScanning(true);
        try {
            const res = await api('/jobs/scan', { method: 'POST', body: { batch_size: 10 } });
            toast(res.message || 'Huge hourly scan completed!', 'success');
            reload({ silent: true });
        } catch (e) {
            toast(e.message || 'Scan failed', 'error');
        } finally {
            setScanning(false);
        }
    };

    const handleToggleAutoApply = async () => {
        setToggling(true);
        try {
            const res = await api('/jobs/toggle-auto-apply', { method: 'POST' });
            toast(res.message, 'success');
            reload({ silent: true });
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setToggling(false);
        }
    };

    const handleDispatchNextAlert = async () => {
        const targetJob = top2027[0];
        if (!targetJob) return;
        setApplying(true);
        try {
            const res = await api('/jobs/dispatch-live-alert', { method: 'POST', body: { job_id: targetJob.id } });
            toast(res.message || `Dispatched application packet for ${targetJob.company}!`, 'success');
            reload({ silent: true });
        } catch (e) {
            toast(e.message || 'Failed to dispatch alert', 'error');
        } finally {
            setApplying(false);
        }
    };

    const openDesk = () => navigate('job-radar');

    if (loading && !data) {
        return (
            <Card className="card-pad" aria-busy="true">
                <div className="flex items-center gap-2.5 mb-4">
                    <Skeleton className="h-8 w-8 rounded-lg" />
                    <Skeleton className="h-4 w-40" />
                </div>
                <Skeleton className="h-12 mb-2" />
                <Skeleton className="h-10" />
            </Card>
        );
    }

    const autoAppliedCount = summary?.auto_applied_count || 0;
    const dailyTarget = summary?.daily_target || 150;
    const progressPct = Math.min(100, Math.round((autoAppliedCount / dailyTarget) * 100));

    return (
        <Card className="overflow-hidden border-emerald-500/25 bg-gradient-to-b from-surface via-surface to-emerald-950/10 shadow-lg">
            {/* Top Bar with Live Hourly Radar Beacon */}
            <div className="card-pad pb-3 border-b border-line">
                <div className="flex flex-wrap items-center justify-between gap-2.5">
                    <div className="flex items-center gap-2.5">
                        <div className="relative grid place-items-center h-8 w-8 rounded-xl bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0">
                            <Radio className="h-4 w-4 animate-pulse" />
                            <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                            </span>
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h2 className="text-[15px] font-bold tracking-tight">2027 Job Desk & Scan Alerts</h2>
                                <span className="badge text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                                    ≥15 LPA · CSE
                                </span>
                            </div>
                            <p className="text-xs text-subtle mt-0.5 flex items-center gap-1.5">
                                <span>Next scan:</span>
                                <span className="font-mono text-emerald-400 font-semibold">{countdown || 'Scanning soon'}</span>
                                <span className="text-muted">·</span>
                                <span>{summary?.total_openings ?? 0} active roles</span>
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 ml-auto">
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleRunScan}
                            loading={scanning}
                            icon={RefreshCw}
                            title="Trigger immediate scan across career portals"
                        >
                            <span className="hidden sm:inline">Scan Now</span>
                        </Button>
                        <Button size="sm" variant="secondary" onClick={openDesk} className="gap-1.5">
                            Open Desk <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                    </div>
                </div>

                {/* Daily Scan Alerts Strip */}
                <div className="mt-3.5 pt-3 border-t border-line/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                        <button
                            type="button"
                            onClick={handleToggleAutoApply}
                            disabled={toggling}
                            className={cx(
                                'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border transition-all',
                                summary?.auto_apply_enabled
                                    ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                                    : 'bg-surface-2 border-line text-subtle',
                            )}
                            title="Toggle daily scan alerts"
                        >
                            <BellRing className="h-3.5 w-3.5" />
                            {summary?.auto_apply_enabled ? 'Daily scan alerts: ON' : 'Daily scan alerts: OFF'}
                        </button>
                    </div>

                    <div className="flex items-center gap-2">
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleDispatchNextAlert}
                            loading={applying}
                            className="text-xs h-7 px-2 shrink-0 border border-line hover:border-emerald-500/40"
                            title="Dispatch email packet for top role"
                        >
                            <Send className="h-3 w-3 mr-1" />
                            Email Packet
                        </Button>
                    </div>
                </div>
            </div>

            {/* Quick Metrics Bar: Applied This Week & Streak */}
            <div className="grid grid-cols-4 border-b border-line divide-x divide-line bg-surface-2/30 text-center py-2 text-xs">
                <div>
                    <div className="font-mono text-base font-bold tabular-nums text-fg">{summary?.applied_this_week ?? 0}</div>
                    <div className="text-[10px] text-subtle uppercase tracking-wider">Applied This Week</div>
                </div>
                <div>
                    <div className="font-mono text-base font-bold tabular-nums text-amber-400 flex items-center justify-center gap-1">
                        <Flame className="h-3.5 w-3.5 fill-amber-400/20" />
                        <span>{summary?.applied_streak_days ?? 0}d</span>
                    </div>
                    <div className="text-[10px] text-subtle uppercase tracking-wider">Confirmed Streak</div>
                </div>
                <div>
                    <div className="font-mono text-base font-bold tabular-nums text-emerald-400">{summary?.confirmed_applied_count ?? 0}</div>
                    <div className="text-[10px] text-subtle uppercase tracking-wider">Total Confirmed</div>
                </div>
                <div>
                    <div className="font-mono text-base font-bold tabular-nums text-cyan-400">{summary?.eligible_2027_count || 0}</div>
                    <div className="text-[10px] text-subtle uppercase tracking-wider">Eligible 2027</div>
                </div>
            </div>

            {/* Top Match Job Listings Preview */}
            <ul className="divide-y divide-line">
                {top2027.map((job) => {
                    const isApplied = job.status === 'manual_applied' || job.status === 'applied_confirmed';
                    return (
                        <li key={job.id} className="p-3 sm:px-4 hover:bg-surface-2/40 transition-colors">
                            <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-bold text-sm text-fg tracking-tight">{job.company}</span>
                                        <span className="badge text-[11px] font-mono font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
                                            {fmtCtc(job.ctc_lpa)}
                                        </span>
                                        <span className="badge text-[10px] bg-surface-2 border border-line text-subtle">
                                            {job.location}
                                        </span>
                                    </div>
                                    <p className="text-xs text-muted mt-0.5 truncate">{job.role}</p>

                                    {/* Skills tag snippets */}
                                    <div className="flex flex-wrap items-center gap-1.5 mt-2">
                                        {(job.skills_required || []).slice(0, 4).map((s, idx) => (
                                             <span key={idx} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-2 border border-line text-subtle">
                                                {s}
                                            </span>
                                        ))}
                                    </div>
                                </div>

                                <div className="flex flex-col items-end gap-1 shrink-0">
                                    {isApplied ? (
                                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                                            <CheckCircle2 className="h-3 w-3" /> Confirmed Applied
                                        </span>
                                    ) : (
                                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-cyan-400 bg-cyan-500/10 border border-cyan-500/30 px-2 py-0.5 rounded-full">
                                            <Clock className="h-3 w-3" /> Ready to Apply
                                        </span>
                                    )}
                                    <span className="text-[10px] font-mono text-subtle">
                                        ML Match: <strong className="text-emerald-400">{job.match_score}%</strong>
                                    </span>
                                </div>
                            </div>
                        </li>
                    );
                })}
            </ul>

            {/* Bottom Footer */}
            <div className="p-3 bg-surface-2/40 border-t border-line flex items-center justify-between text-xs">
                <span className="text-subtle truncate">
                    Candidate: <strong>{profile?.full_name?.split(' ')[0] || 'Sai'}</strong> · NIT Rourkela (CGPA: 8.99)
                </span>
                <button
                    type="button"
                    onClick={openDesk}
                    className="text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1 ml-auto"
                >
                    View all openings <ArrowRight className="h-3.5 w-3.5" />
                </button>
            </div>
        </Card>
    );
}
