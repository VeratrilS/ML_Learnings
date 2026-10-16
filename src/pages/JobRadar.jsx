import { useState, useMemo, useEffect, useRef } from 'react';
import {
    Radio, Bot, Briefcase, Zap, CheckCircle2, Clock, ShieldCheck,
    RefreshCw, Filter, Search, ExternalLink, ChevronDown, ChevronRight,
    Sparkles, ArrowRight, Building2, Flame, Award, Sliders, Check, Terminal,
    FileText, User, GraduationCap, Code2, Globe, Send, Play, Pause,
    Mail, Copy, BellRing, Target, BookOpen, Layers, Trophy, CheckCheck,
    AlertCircle, Undo2, Share2, Compass, Cpu, X, Upload,
} from 'lucide-react';
import { api, getToken } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, CardHeader, Empty, Segmented, Sheet, Skeleton, useToast, cx } from '../components/ui';
import { play } from '../lib/sfx';
import { buildBookmarklet, autofillSnippet } from '../lib/autofill';

function fmtCtc(val) {
    if (!val || Number(val) === 0) return 'CTC not listed';
    return `₹${Number(val).toFixed(1)} LPA (est.)`;
}

function fmtEstCtc(job) {
    if (!job) return '';
    if (!job.ctc_lpa || Number(job.ctc_lpa) === 0) {
        return 'CTC not listed';
    }
    if (job.notes && typeof job.notes === 'string') {
        const estMatch = job.notes.match(/est\.?\s*CTC\s*([0-9]+(?:\.[0-9]+)?(?:[–-][0-9]+(?:\.[0-9]+)?)?\s*LPA)/i);
        if (estMatch) {
            return `~${estMatch[1]} (est.)`;
        }
    }
    return `~₹${Number(job.ctc_lpa).toFixed(1)} LPA (est.)`;
}

function countWords(str) {
    if (!str || typeof str !== 'string') return 0;
    return str.trim().split(/\s+/).filter(Boolean).length;
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
                setTimeLeft('Scanning now…');
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

export default function JobRadar() {
    const { data, loading, reload } = useApi('/jobs/radar');
    const blueprintsApi = useApi('/jobs/blueprints');
    const queueApi = useApi('/jobs/queue');
    const resumeInfoApi = useApi('/jobs/resume-file/info');
    const [liveMinCtc15, setLiveMinCtc15] = useState(true);
    const liveApi = useApi(`/jobs/live?min_score=50${liveMinCtc15 ? '&min_ctc=15' : ''}`);
    const toast = useToast();

    // Tab state: 'openings' | 'portals' | 'confirmed' | 'blueprints'
    const [activeTab, setActiveTab] = useState('openings');

    // Filter states
    const [query, setQuery] = useState('');
    const [statusFilter, setStatusFilter] = useState('all');
    const [minCtcFilter, setMinCtcFilter] = useState(15);
    const [roleTypeFilter, setRoleTypeFilter] = useState('all');
    const [locationFilter, setLocationFilter] = useState('all');
    const [expandedJobId, setExpandedJobId] = useState(null);
    const [terminalOpen, setTerminalOpen] = useState(false);
    const [mlDrawerOpen, setMlDrawerOpen] = useState(false);
    const [visibleCount, setVisibleCount] = useState(30);

    // Application Pack Drawer state
    const [packDrawerJob, setPackDrawerJob] = useState(null);
    const [packData, setPackData] = useState(null);
    const [packLoading, setPackLoading] = useState(false);
    const [packError, setPackError] = useState(null);
    const [copiedField, setCopiedField] = useState(null);

    // Confirm Application Modal state
    const [confirmModalJob, setConfirmModalJob] = useState(null);
    const [confirmRefInput, setConfirmRefInput] = useState('');
    const [confirmNotesInput, setConfirmNotesInput] = useState('');
    const [confirming, setConfirming] = useState(false);

    // Resume upload state
    const resumeFileInputRef = useRef(null);
    const [uploadingResume, setUploadingResume] = useState(false);

    // Action states
    const [scanning, setScanning] = useState(false);
    const [emailingJobId, setEmailingJobId] = useState(null);
    const [toggling, setToggling] = useState(false);

    const profile = data?.profile;
    const summary = data?.summary;
    const resumeInfo = resumeInfoApi.data?.data;
    const jobs = useMemo(() => data?.jobs || [], [data]);
    const recentLogs = useMemo(() => data?.recent_logs || [], [data]);
    const blueprints = useMemo(() => blueprintsApi.data?.blueprints || [], [blueprintsApi.data]);
    const liveJobs = useMemo(() => liveApi.data?.data || [], [liveApi.data]);
    const approvedJobs = useMemo(() => {
        if (queueApi.data?.data && Array.isArray(queueApi.data.data) && queueApi.data.data.length > 0) {
            return queueApi.data.data;
        }
        return jobs.filter((j) => j.status === 'approved');
    }, [queueApi.data, jobs]);
    const countdown = useCountdown(summary?.next_hourly_scan);

    const profileWithResume = useMemo(() => {
        if (!profile) return null;
        return {
            ...profile,
            resume_url: resumeInfo?.uploaded ? resumeInfo.url : undefined,
            resume_name: resumeInfo?.uploaded ? (resumeInfo.filename || 'NandamVenkataSaiRaghava_Resume.pdf') : undefined,
        };
    }, [profile, resumeInfo]);

    const bookmarkletSnippet = useMemo(() => profileWithResume ? autofillSnippet(profileWithResume) : '', [profileWithResume]);

    const handleCopyBookmarklet = () => {
        if (navigator.clipboard && bookmarkletSnippet) {
            navigator.clipboard.writeText(bookmarkletSnippet);
            play('pop', { force: true });
            toast('Autofill code copied! Paste into developer console (F12) or browser bookmark URL.', 'success');
        }
    };

    const handleResumeUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            toast('Please select a PDF file.', 'error');
            return;
        }
        if (file.size > 2 * 1024 * 1024) {
            toast('Resume must be 2 MB or smaller.', 'error');
            return;
        }
        setUploadingResume(true);
        try {
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch('/api/jobs/resume-upload', {
                method: 'POST',
                headers: { 'X-App-Key': getToken() },
                body: formData,
            });
            const json = await res.json().catch(() => null);
            if (!res.ok || json?.status === 'error') {
                throw new Error(json?.message || `Upload failed (${res.status})`);
            }
            play('bell', { force: true });
            toast(`Resume uploaded: ${json.data?.filename || file.name}`, 'success');
            if (resumeInfoApi?.reload) resumeInfoApi.reload({ silent: true });
        } catch (err) {
            toast(err.message || 'Resume upload failed', 'error');
        } finally {
            setUploadingResume(false);
            if (resumeFileInputRef.current) resumeFileInputRef.current.value = '';
        }
    };

    const handleOpenPack = async (job, refresh = false) => {
        setPackDrawerJob(job);
        setPackLoading(true);
        setPackError(null);
        try {
            const queryParam = refresh ? '?refresh=1' : '';
            const res = await api(`/jobs/${job.id}/pack${queryParam}`);
            if (res?.data) {
                setPackData(res.data);
                if (refresh) {
                    toast('Application pack regenerated!', 'success');
                    play('bell', { force: true });
                }
            }
        } catch (e) {
            setPackError(e.message || 'Failed to load application pack');
            toast(e.message || 'Failed to load application pack', 'error');
        } finally {
            setPackLoading(false);
        }
    };

    const handleCopyField = (fieldName, text) => {
        if (!text) return;
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text);
            setCopiedField(fieldName);
            setTimeout(() => setCopiedField(null), 2000);
            play('pop', { force: true });
            toast(`Copied ${fieldName} to clipboard!`, 'success');
        }
    };

    const handleCopyFullPack = () => {
        if (!packData) return;
        const bullets = (packData.resume_highlights || []).map((b) => `• ${b}`).join('\n');
        const answersText = (packData.answers || []).map((a) => `Q: ${a.question}\nA: ${a.answer}`).join('\n\n');
        const fullText = `=== APPLICATION PACK FOR ${packData.company.toUpperCase()} ===
Role: ${packData.role}
Portal: ${packData.url}

--- COVER NOTE ---
${packData.cover_note || ''}

--- WHY ${packData.company.toUpperCase()} ---
${packData.why_company || ''}

--- SCREENING Q&A ---
${answersText}

--- RESUME HIGHLIGHTS ---
${bullets}
`.trim();
        if (navigator.clipboard) {
            navigator.clipboard.writeText(fullText);
            setCopiedField('full_pack');
            setTimeout(() => setCopiedField(null), 2000);
            play('combo', { force: true });
            toast('Copied full application pack to clipboard!', 'success');
        }
    };

    // Filtered jobs list
    const filteredJobs = useMemo(() => {
        return jobs.filter((job) => {
            if (job.eligible_batches && !job.eligible_batches.includes('2027')) return false;
            if (job.ctc_lpa > 0 && job.ctc_lpa < minCtcFilter) return false;

            const isAppliedStatus = job.status === 'applied_confirmed' || job.status === 'manual_applied';
            if (statusFilter === 'applied' && !isAppliedStatus) return false;
            if (statusFilter === 'approved' && job.status !== 'approved') return false;
            if (statusFilter === 'ready' && (isAppliedStatus || job.status === 'skipped')) return false;
            if (statusFilter === 'skipped' && job.status !== 'skipped') return false;
            if (statusFilter === 'all' && job.status === 'skipped') return false;

            if (roleTypeFilter === 'fte' && !job.role.toLowerCase().includes('fte')) return false;
            if (roleTypeFilter === 'intern' && !job.role.toLowerCase().includes('intern')) return false;

            if (locationFilter !== 'all') {
                if (!job.location?.toLowerCase().includes(locationFilter.toLowerCase())) return false;
            }

            if (query.trim()) {
                const q = query.toLowerCase();
                const matchedCompany = job.company?.toLowerCase().includes(q);
                const matchedRole = job.role?.toLowerCase().includes(q);
                const matchedSkills = (job.skills_required || []).some((s) => s.toLowerCase().includes(q));
                if (!matchedCompany && !matchedRole && !matchedSkills) return false;
            }

            return true;
        });
    }, [jobs, minCtcFilter, statusFilter, roleTypeFilter, locationFilter, query]);

    useEffect(() => {
        setVisibleCount(30);
    }, [query, statusFilter, minCtcFilter, roleTypeFilter, locationFilter]);

    // Unique Companies for the Portals Directory
    const companyPortals = useMemo(() => {
        const map = new Map();
        for (const j of jobs) {
            if (!map.has(j.company)) {
                map.set(j.company, {
                    company: j.company,
                    portal_url: j.portal_url,
                    ctc_lpa: j.ctc_lpa,
                    stipend_pm: j.stipend_pm,
                    location: j.location,
                    track: j.notes?.split('.')[0]?.replace('Track: ', '') || 'Systems & Microservices',
                    skills: j.skills_required || [],
                    openingsCount: 1,
                });
            } else {
                const existing = map.get(j.company);
                existing.openingsCount += 1;
            }
        }
        return Array.from(map.values()).sort((a, b) => b.ctc_lpa - a.ctc_lpa);
    }, [jobs]);

    const confirmedJobs = useMemo(() => {
        return jobs.filter((j) => j.status === 'applied_confirmed' || j.status === 'manual_applied');
    }, [jobs]);

    const skippedJobs = useMemo(() => {
        return jobs.filter((j) => j.status === 'skipped');
    }, [jobs]);

    const appliedTodayCount = useMemo(() => {
        const todayStr = new Date().toISOString().slice(0, 10);
        return jobs.filter((j) => (j.status === 'manual_applied' || j.status === 'applied_confirmed') && j.applied_at && j.applied_at.startsWith(todayStr)).length;
    }, [jobs]);

    const todays20Jobs = useMemo(() => {
        const appliedStatuses = new Set(['manual_applied', 'applied_confirmed', 'skipped']);
        const pool = [];
        const seen = new Set();
        for (const j of approvedJobs) {
            if (!appliedStatuses.has(j.status) && !seen.has(j.id)) {
                pool.push({ ...j, isApproved: true });
                seen.add(j.id);
            }
        }
        for (const j of liveJobs) {
            if (!appliedStatuses.has(j.status) && !seen.has(j.id)) {
                pool.push(j);
                seen.add(j.id);
            }
        }
        for (const j of jobs) {
            if (!appliedStatuses.has(j.status) && !seen.has(j.id)) {
                pool.push(j);
                seen.add(j.id);
            }
        }
        const scoreRole = (j) => {
            if (j.role_type === 'fte') return 4;
            if (j.role_type === 'intern_6m') return 3;
            if (j.role_type === 'intern') return 2;
            const title = (j.role || '').toLowerCase();
            if (title.includes('fte') || title.includes('full time') || title.includes('graduate')) return 4;
            if (title.includes('6-month')) return 3;
            if (title.includes('intern')) return 2;
            return 1;
        };
        return pool.sort((a, b) => {
            const roleDiff = scoreRole(b) - scoreRole(a);
            if (roleDiff !== 0) return roleDiff;
            const scoreA = Number(a.match_score || 0);
            const scoreB = Number(b.match_score || 0);
            if (scoreB !== scoreA) return scoreB - scoreA;
            const dateA = a.discovered_at ? new Date(a.discovered_at).getTime() : 0;
            const dateB = b.discovered_at ? new Date(b.discovered_at).getTime() : 0;
            return dateB - dateA;
        }).slice(0, 20);
    }, [approvedJobs, liveJobs, jobs]);

    // Triggers
    const handleRunScan = async () => {
        setScanning(true);
        try {
            const res = await api('/jobs/scan', { method: 'POST', body: { batch_size: 12 } });
            play('bell', { force: true });
            const msg = res?.data ? `Scan complete: found ${res.data.found ?? 0} postings (${res.data.new ?? 0} new).` : (res?.message || 'Scan completed.');
            toast(msg, 'success');
            reload({ silent: true });
            if (liveApi?.reload) liveApi.reload({ silent: true });
            if (queueApi?.reload) queueApi.reload({ silent: true });
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

    const handleDispatchEmailAlert = async (job) => {
        setEmailingJobId(job.id);
        try {
            const res = await api('/jobs/dispatch-live-alert', { method: 'POST', body: { job_id: job.id } });
            play('combo', { force: true });
            toast(`Application packet & official apply link sent to ${profile?.email || 'sairaghava1318@gmail.com'}!`, 'success');
        } catch (e) {
            toast(e.message || 'Failed to dispatch email', 'error');
        } finally {
            setEmailingJobId(null);
        }
    };

    const handleCopyFullPacket = (job) => {
        const answers = job.ml_tailored_answers || {};
        const text = `
=== 1-CLICK APPLICATION PACKET ===
Candidate: ${profile?.full_name || 'Nandam Venkata Sai Raghava'}
Email: ${profile?.email || 'sairaghava1318@gmail.com'}
Phone: ${profile?.phone || ''}
Institution: National Institute of Technology, Rourkela (NIT Rourkela)
Degree: B.Tech Computer Science and Engineering (Class of 2027)
CGPA: ${profile?.cgpa || 8.99} / 10.0
LeetCode: ${profile?.leetcode || 'https://leetcode.com/u/Sairaghava1318/'}
Codeforces: ${profile?.codeforces || 'https://codeforces.com/profile/Raghavan_CP'}
GitHub: ${profile?.github || 'https://github.com/VeratrilS'}

--- SCREENING ANSWERS FOR ${job.company.toUpperCase()} ---
Role: ${job.role}
Portal: ${job.portal_url || job.url || ''}

Q: Why ${job.company}?
${answers.why_company || ''}

Q: Hardest Technical Concurrency / System Bug Solved?
${answers.biggest_technical_challenge || ''}

Q: Low-Level / Systems Experience?
${answers.low_level_systems_experience || ''}

Availability: ${answers.availability || 'Class of 2027 (NIT Rourkela CSE). Ready for 2026/2027 Internship and FTE conversion.'}
        `.trim();

        if (navigator.clipboard) {
            navigator.clipboard.writeText(text);
            play('pop', { force: true });
            toast(`Copied full application packet for ${job.company}! Paste directly into the portal.`, 'success');
        }
    };

    const handleConfirmSubmit = async () => {
        const target = confirmModalJob;
        if (!target) return;
        setConfirming(true);
        try {
            const res = await api('/jobs/manual-applied', {
                method: 'POST',
                body: {
                    job_id: target.id,
                    confirmation_ref: confirmRefInput.trim().slice(0, 100),
                    notes: confirmNotesInput.trim().slice(0, 500),
                },
            });
            play('combo', { force: true });
            toast(res.message || `Recorded: Applied to ${target.company}! 7d and 14d follow-ups scheduled.`, 'success');
            setConfirmModalJob(null);
            setConfirmRefInput('');
            setConfirmNotesInput('');
            reload({ silent: true });
            if (liveApi?.reload) liveApi.reload({ silent: true });
            if (queueApi?.reload) queueApi.reload({ silent: true });
        } catch (e) {
            if (e.message?.includes('Already') || e.status === 409) {
                toast('Already recorded as applied.', 'info');
                setConfirmModalJob(null);
            } else {
                toast(e.message || 'Failed to record application', 'error');
            }
        } finally {
            setConfirming(false);
        }
    };

    const handleUnmarkApplied = async (jobId, company) => {
        try {
            await api('/jobs/unmark-applied', { method: 'POST', body: { job_id: jobId } });
            toast(`Reset application status for ${company}.`, 'info');
            reload({ silent: true });
            if (liveApi?.reload) liveApi.reload({ silent: true });
            if (queueApi?.reload) queueApi.reload({ silent: true });
        } catch (e) {
            toast(e.message || 'Failed to reset status', 'error');
        }
    };

    return (
        <div className="space-y-6 animate-rise">
            {/* Header / Hero */}
            <header className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <div className="eyebrow flex items-center gap-1.5 text-emerald-400">
                        <Radio className="h-4 w-4 animate-pulse" />
                        <span>Hourly Career Radar & Autonomous Placement Copilot</span>
                    </div>
                    <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight text-fg">
                        2027 CSE Job Radar · ₹15+ LPA
                    </h1>
                    <p className="text-sm text-subtle mt-1 max-w-2xl">
                        Scans 51 premier tech career portals hourly for Batch 2027 CSE openings.
                        Generates grounded screening packets based on your verified NIT Rourkela projects, dispatches email alerts, and only records verified applications upon real portal submission.
                    </p>
                </div>

                <div className="flex flex-wrap items-center gap-2.5">
                    <Button
                        variant="secondary"
                        onClick={handleToggleAutoApply}
                        loading={toggling}
                        icon={summary?.auto_apply_enabled ? Pause : Play}
                        className={cx(
                            summary?.auto_apply_enabled
                                ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
                                : 'border-line text-subtle',
                        )}
                    >
                        {summary?.auto_apply_enabled ? 'Hourly Scanner: Active' : 'Hourly Scanner: Paused'}
                    </Button>

                    <Button
                        variant="primary"
                        icon={RefreshCw}
                        onClick={handleRunScan}
                        loading={scanning}
                        className="shadow-sm"
                    >
                        Hourly Check Now
                    </Button>
                </div>
            </header>

            {/* Candidate Verification & Authenticity Banner */}
            <Card className="card-pad border-emerald-500/30 bg-gradient-to-r from-surface via-surface to-emerald-950/20">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-start sm:items-center gap-3">
                        <div className="grid place-items-center h-11 w-11 rounded-2xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 shrink-0">
                            <GraduationCap className="h-6 w-6" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="font-bold text-base text-fg">{profile?.full_name || 'Nandam Venkata Sai Raghava'}</h3>
                                <span className="badge font-mono text-xs font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                    NIT Rourkela · 2027 CSE
                                </span>
                                <span className="badge font-mono text-xs font-bold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                                    CGPA: {profile?.cgpa || 8.99}
                                </span>
                                <span className="badge text-[10px] font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                                    ✓ Zero Mock Submissions Policy Active
                                </span>
                            </div>
                            <p className="text-xs text-subtle mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                                <span>🏆 LeetCode: <strong>1709</strong> (900+ Solved)</span>
                                <span>⚔️ Codeforces Specialist: <strong>1425</strong></span>
                                <span>⚙️ Ex-Intern: <strong>Maruti Suzuki (MSIL)</strong></span>
                                <span>🚀 Projects: <strong>Railway Kafka Microservices</strong> & <strong>C++ TCP Cache</strong></span>
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                        <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => setMlDrawerOpen(true)}
                            icon={Sparkles}
                            className="border-emerald-500/30 hover:border-emerald-500"
                        >
                            Skill Match Profile
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => navigate('placements')}
                            icon={Briefcase}
                        >
                            Placements Board
                        </Button>
                    </div>
                </div>
            </Card>

            {/* Form Autofill Bookmarklet Banner */}
            <Card className="card-pad border-amber-500/30 bg-gradient-to-r from-amber-950/20 via-surface to-surface">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    <div className="flex items-start gap-3">
                        <div className="grid place-items-center h-10 w-10 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-400 shrink-0">
                            <Zap className="h-5 w-5" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="font-bold text-sm text-fg">1-Click Job Form Autofill Bookmarklet</h3>
                                <span className="badge text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30">
                                    Greenhouse · Lever · Ashby · SmartRecruiters
                                </span>
                            </div>
                            <p className="text-xs text-subtle mt-0.5 max-w-xl">
                                Automatically fills your candidate information (NIT Rourkela, 8.99 CGPA, LeetCode, GitHub, Work Auth) on any external job portal and auto-attaches your resume PDF. Never submits automatically — you review and click submit.
                            </p>
                            <div className="flex items-center gap-2 flex-wrap mt-2">
                                {resumeInfo?.uploaded ? (
                                    <span className="badge text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                                        📄 Auto-attach PDF: {resumeInfo.filename} ({(resumeInfo.size / 1024).toFixed(0)} KB)
                                    </span>
                                ) : (
                                    <span className="badge text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30">
                                        ⚠️ No resume uploaded (upload PDF below to auto-attach on ATS forms)
                                    </span>
                                )}
                            </div>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted mt-2">
                                <span><b>1.</b> Copy Autofill Code</span>
                                <span>→</span>
                                <span><b>2.</b> Bookmark any page & paste code as URL (or press F12 → Console)</span>
                                <span>→</span>
                                <span><b>3.</b> Click bookmark on job portal</span>
                            </div>
                        </div>
                    </div>

                    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2.5 shrink-0">
                        <input
                            type="file"
                            ref={resumeFileInputRef}
                            accept=".pdf"
                            onChange={handleResumeUpload}
                            style={{ display: 'none' }}
                        />
                        <Button
                            size="sm"
                            variant="secondary"
                            icon={Upload}
                            loading={uploadingResume}
                            onClick={() => resumeFileInputRef.current?.click()}
                            title="Upload/replace candidate resume PDF (max 2 MB)"
                        >
                            {resumeInfo?.uploaded ? 'Replace Resume' : 'Upload Resume'}
                        </Button>
                        <Button
                            size="sm"
                            variant="primary"
                            icon={Copy}
                            onClick={handleCopyBookmarklet}
                            title="Copy JavaScript code for bookmarklet or console"
                            className="bg-amber-500 hover:bg-amber-400 text-black font-bold"
                        >
                            Copy Autofill Code
                        </Button>
                    </div>
                </div>
            </Card>

            {/* Live Metrics Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <Card className="card-pad text-center">
                    <div className="text-xs text-subtle mb-1">Verified 2027 Openings</div>
                    <div className="text-2xl sm:text-3xl font-mono font-bold text-fg tabular-nums">
                        {summary?.eligible_2027_count || jobs.length}
                    </div>
                    <div className="text-[11px] text-emerald-400 font-semibold mt-1">
                        ≥{minCtcFilter} LPA · CSE & Circuit
                    </div>
                </Card>

                <Card className="card-pad text-center">
                    <div className="text-xs text-subtle mb-1">Confirmed Applications</div>
                    <div className="text-2xl sm:text-3xl font-mono font-bold text-emerald-400 tabular-nums">
                        {confirmedJobs.length}
                    </div>
                    <div className="text-[11px] text-subtle font-medium mt-1">
                        Genuinely applied on portal
                    </div>
                </Card>

                <Card className="card-pad text-center">
                    <div className="text-xs text-subtle mb-1">Company Portals Tracked</div>
                    <div className="text-2xl sm:text-3xl font-mono font-bold text-cyan-400 tabular-nums">
                        {companyPortals.length || 51}
                    </div>
                    <div className="text-[11px] text-subtle font-medium mt-1">
                        Tier-1 Tech & Quant HFT
                    </div>
                </Card>

                <Card className="card-pad text-center">
                    <div className="text-xs text-subtle mb-1">Next Hourly Scan</div>
                    <div className="text-2xl sm:text-3xl font-mono font-bold text-fg tabular-nums">
                        {countdown || 'Scanning now…'}
                    </div>
                    <div className="text-[11px] text-subtle mt-1 flex items-center justify-center gap-1 font-mono">
                        <Clock className="h-3 w-3 text-emerald-400" />
                        <span>Hourly Cron Active</span>
                    </div>
                </Card>
            </div>

            {/* Navigation Tabs */}
            <div className="border-b border-line flex items-center justify-between gap-4 overflow-x-auto no-scrollbar">
                <div className="flex items-center gap-2 sm:gap-4">
                    <button
                        type="button"
                        onClick={() => setActiveTab('openings')}
                        className={cx(
                            'pb-3 text-sm font-semibold border-b-2 transition-all flex items-center gap-2 whitespace-nowrap',
                            activeTab === 'openings'
                                ? 'border-emerald-500 text-fg'
                                : 'border-transparent text-subtle hover:text-fg',
                        )}
                    >
                        <Briefcase className="h-4 w-4" />
                        <span>2027 CSE Opportunities ({filteredJobs.length})</span>
                    </button>

                    <button
                        type="button"
                        onClick={() => setActiveTab('portals')}
                        className={cx(
                            'pb-3 text-sm font-semibold border-b-2 transition-all flex items-center gap-2 whitespace-nowrap',
                            activeTab === 'portals'
                                ? 'border-emerald-500 text-fg'
                                : 'border-transparent text-subtle hover:text-fg',
                        )}
                    >
                        <Globe className="h-4 w-4" />
                        <span>Track All 51 Career Portals</span>
                    </button>

                    <button
                        type="button"
                        onClick={() => setActiveTab('confirmed')}
                        className={cx(
                            'pb-3 text-sm font-semibold border-b-2 transition-all flex items-center gap-2 whitespace-nowrap',
                            activeTab === 'confirmed'
                                ? 'border-emerald-500 text-fg'
                                : 'border-transparent text-subtle hover:text-fg',
                        )}
                    >
                        <CheckCheck className="h-4 w-4" />
                        <span>Confirmed Submissions ({confirmedJobs.length})</span>
                    </button>

                    <button
                        type="button"
                        onClick={() => setActiveTab('blueprints')}
                        className={cx(
                            'pb-3 text-sm font-semibold border-b-2 transition-all flex items-center gap-2 whitespace-nowrap',
                            activeTab === 'blueprints'
                                ? 'border-emerald-500 text-fg'
                                : 'border-transparent text-subtle hover:text-fg',
                        )}
                    >
                        <Cpu className="h-4 w-4" />
                        <span>OA & Technical Blueprints</span>
                    </button>
                </div>
            </div>

            {/* TAB 1: 2027 CSE OPPORTUNITIES */}
            {activeTab === 'openings' && (
                <div className="space-y-4">
                    {/* Control Bar & Filters */}
                    <div className="p-3.5 rounded-2xl bg-surface border border-line space-y-3">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-subtle" />
                                <input
                                    type="text"
                                    placeholder="Search by company, role, or tech stack (e.g. C++, Kafka, Redis, Uber)..."
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    className="input pl-9 text-xs w-full"
                                />
                            </div>

                            <div className="flex items-center gap-2 flex-wrap">
                                {/* CTC Filter Chips */}
                                <div className="flex items-center gap-1 bg-surface-2 p-1 rounded-xl border border-line">
                                    <span className="text-[11px] font-medium text-subtle px-2">Min CTC:</span>
                                    {[15, 20, 25, 30, 40].map((ctc) => (
                                        <button
                                            key={ctc}
                                            type="button"
                                            onClick={() => setMinCtcFilter(ctc)}
                                            className={cx(
                                                'px-2 py-0.5 rounded-lg text-xs font-mono font-bold transition-all',
                                                minCtcFilter === ctc
                                                    ? 'bg-emerald-500 text-black shadow-sm'
                                                    : 'text-subtle hover:text-fg',
                                            )}
                                        >
                                            ≥{ctc}L
                                        </button>
                                    ))}
                                </div>

                                <Segmented
                                    options={[
                                        { value: 'all', label: `All (${filteredJobs.length})` },
                                        { value: 'approved', label: `Approved (${approvedJobs.length})` },
                                        { value: 'ready', label: 'Ready to Apply' },
                                        { value: 'applied', label: `Applied (${confirmedJobs.length})` },
                                        { value: 'skipped', label: `Skipped (${skippedJobs.length})` },
                                    ]}
                                    value={statusFilter}
                                    onChange={setStatusFilter}
                                />
                            </div>
                        </div>

                        {/* Secondary Filters: Role Type & Location */}
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-line text-xs">
                            <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar">
                                <span className="text-subtle font-medium shrink-0">Role Type:</span>
                                {[
                                    { id: 'all', label: 'All Roles' },
                                    { id: 'intern', label: 'Internship' },
                                    { id: 'fte', label: 'Full-Time (FTE)' },
                                ].map((t) => (
                                    <button
                                        key={t.id}
                                        type="button"
                                        onClick={() => setRoleTypeFilter(t.id)}
                                        className={cx(
                                            'px-2.5 py-0.5 rounded-full border text-xs whitespace-nowrap transition-all',
                                            roleTypeFilter === t.id
                                                ? 'bg-surface-2 border-emerald-500/50 text-emerald-400 font-semibold'
                                                : 'bg-surface border-line text-subtle hover:text-fg',
                                        )}
                                    >
                                        {t.label}
                                    </button>
                                ))}
                            </div>

                            <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar">
                                <span className="text-subtle font-medium shrink-0">Location:</span>
                                {['all', 'Bengaluru', 'Hyderabad', 'Gurugram', 'Remote'].map((loc) => (
                                    <button
                                        key={loc}
                                        type="button"
                                        onClick={() => setLocationFilter(loc)}
                                        className={cx(
                                            'px-2.5 py-0.5 rounded-full border text-xs capitalize whitespace-nowrap transition-all',
                                            locationFilter === loc
                                                ? 'bg-surface-2 border-emerald-500/50 text-emerald-400 font-semibold'
                                                : 'bg-surface border-line text-subtle hover:text-fg',
                                        )}
                                    >
                                        {loc}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* TODAY'S 20: FAST-APPLY VIEW */}
                    {todays20Jobs.length > 0 && (
                        <div className="space-y-3 p-4 rounded-2xl bg-gradient-to-r from-surface via-surface to-amber-950/20 border-2 border-amber-500/40 shadow-sm">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                    <span className="grid place-items-center h-6 w-6 rounded-lg bg-amber-500/20 text-amber-400">
                                        <Flame className="h-4 w-4" />
                                    </span>
                                    <h3 className="font-bold text-sm text-fg">Today's 20 Priority Roles</h3>
                                    <span className="badge text-[10px] font-mono bg-amber-500/15 text-amber-300 border border-amber-500/30">
                                        Applied today: {appliedTodayCount} / 20
                                    </span>
                                </div>
                                <span className="text-xs text-subtle font-mono hidden sm:inline">
                                    FTE & 6-mo Intern first · 1-click apply assist
                                </span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {todays20Jobs.map((job) => (
                                    <div key={job.id} className="p-3.5 rounded-xl bg-surface-2 border border-line hover:border-amber-500/40 transition-all flex flex-col justify-between gap-3">
                                        <div>
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="font-bold text-sm text-fg truncate">{job.company}</span>
                                                <div className="flex items-center gap-1.5 shrink-0">
                                                    <span className="badge text-[10px] font-mono text-cyan-400 bg-surface border border-cyan-500/30 font-bold">
                                                        {fmtEstCtc(job)}
                                                    </span>
                                                    {job.isApproved && (
                                                        <span className="badge text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                                            Approved
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            <p className="text-xs text-muted font-medium mt-0.5 truncate">{job.role}</p>
                                            <div className="flex items-center gap-2 text-[11px] text-subtle mt-1 flex-wrap">
                                                <span className="badge text-[10px] uppercase font-mono bg-surface border border-line">
                                                    {job.board ? job.board.toUpperCase() : (job.source || 'Portal')}
                                                </span>
                                                {job.role_type === 'fte' && (
                                                    <span className="badge text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                                        FTE
                                                    </span>
                                                )}
                                                {job.role_type === 'intern_6m' && (
                                                    <span className="badge text-[10px] font-mono font-bold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                                                        6-Mo Intern
                                                    </span>
                                                )}
                                                {job.role_type === 'intern' && (
                                                    <span className="badge text-[10px] font-mono font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                                                        Intern
                                                    </span>
                                                )}
                                                <span>·</span>
                                                <span>{job.location || 'India'}</span>
                                                {(job.posted || job.discovered_at) && (
                                                    <>
                                                        <span>·</span>
                                                        <span className="text-[10px] font-mono text-muted flex items-center gap-1">
                                                            <Clock className="h-2.5 w-2.5 text-subtle" />
                                                            {job.posted ? `Posted ${job.posted}` : 'Discovered today'}
                                                        </span>
                                                    </>
                                                )}
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-1.5 pt-2 border-t border-line/60 flex-wrap">
                                            <a
                                                href={job.portal_url || job.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="btn btn-secondary btn-sm text-xs gap-1 flex-1 min-w-[110px] justify-center truncate"
                                                title="Launch official application portal"
                                            >
                                                <span>Open ↗</span>
                                            </a>

                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={handleCopyBookmarklet}
                                                className="text-xs py-1.5 px-2.5 border border-line text-subtle hover:text-fg"
                                                title="Copy ⚡ Autofill JavaScript snippet"
                                            >
                                                <Zap className="h-3 w-3 mr-1 text-amber-400" />
                                                Autofill
                                            </Button>

                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => handleOpenPack(job)}
                                                className="text-xs py-1.5 px-2.5 border border-emerald-500/30 text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20"
                                                title="Application pack (Answers & Highlights)"
                                            >
                                                <Sparkles className="h-3 w-3 mr-1" />
                                                Answers
                                            </Button>

                                            <Button
                                                size="sm"
                                                variant="primary"
                                                onClick={() => {
                                                    setConfirmModalJob(job);
                                                    setConfirmRefInput('');
                                                    setConfirmNotesInput('');
                                                }}
                                                className="text-xs py-1.5 px-3 shrink-0"
                                            >
                                                <Check className="h-3 w-3 mr-1" />
                                                I Applied
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Approved — to apply (From Email / Queue) */}
                    {approvedJobs.length > 0 && (
                        <div className="space-y-3 p-4 rounded-2xl bg-gradient-to-r from-surface via-surface to-emerald-950/20 border-2 border-emerald-500/40 shadow-sm">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                    <span className="grid place-items-center h-6 w-6 rounded-lg bg-emerald-500/20 text-emerald-400">
                                        <CheckCircle2 className="h-4 w-4" />
                                    </span>
                                    <h3 className="font-bold text-sm text-fg">Approved — To Apply ({approvedJobs.length} roles)</h3>
                                    <span className="badge text-[10px] font-mono bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                        Approved by you · Ready to submit
                                    </span>
                                </div>
                                <span className="text-xs text-subtle font-mono hidden sm:inline">
                                    Pre-generated packs · 1-click assist
                                </span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {approvedJobs.map((job) => (
                                    <div key={job.id} className="p-3.5 rounded-xl bg-surface-2 border border-emerald-500/30 flex flex-col justify-between gap-3">
                                        <div>
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="font-bold text-sm text-fg truncate">{job.company}</span>
                                                <div className="flex items-center gap-1.5 shrink-0">
                                                    <span className="badge text-[10px] font-mono text-emerald-400 bg-surface border border-emerald-500/30 font-bold">
                                                        {fmtEstCtc(job)}
                                                    </span>
                                                    <span className="badge text-[10px] font-mono bg-surface border border-line text-cyan-400 font-bold">
                                                        {job.match_score || 90}% Match
                                                    </span>
                                                </div>
                                            </div>
                                            <p className="text-xs text-muted font-medium mt-0.5 truncate">{job.role}</p>
                                            <div className="flex items-center gap-2 text-[11px] text-subtle mt-1 flex-wrap">
                                                <span className="badge text-[10px] uppercase font-mono bg-surface border border-line">{job.source || 'Portal'}</span>
                                                <span>·</span>
                                                <span>{job.location || 'India'}</span>
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-1.5 pt-2 border-t border-line/60 flex-wrap">
                                            <a
                                                href={job.portal_url || job.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="btn btn-secondary btn-sm text-xs gap-1 flex-1 min-w-[120px] justify-center truncate"
                                                title="Launch official application portal"
                                            >
                                                <span>Open Application</span>
                                                <ExternalLink className="h-3 w-3 shrink-0" />
                                            </a>

                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={handleCopyBookmarklet}
                                                className="text-xs py-1.5 px-2.5 border border-line text-subtle hover:text-fg"
                                                title="Copy ⚡ Autofill JavaScript snippet"
                                            >
                                                <Zap className="h-3 w-3 mr-1 text-amber-400" />
                                                Autofill
                                            </Button>

                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => handleOpenPack(job)}
                                                className="text-xs py-1.5 px-2.5 border border-emerald-500/30 text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20"
                                                title="Open application pack with tailored answers & highlights"
                                            >
                                                <Sparkles className="h-3 w-3 mr-1" />
                                                Pack
                                            </Button>

                                            <Button
                                                size="sm"
                                                variant="primary"
                                                onClick={() => {
                                                    setConfirmModalJob(job);
                                                    setConfirmRefInput('');
                                                    setConfirmNotesInput('');
                                                }}
                                                className="text-xs py-1.5 px-3 shrink-0"
                                            >
                                                <Check className="h-3 w-3 mr-1" />
                                                I Applied
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Live Career Board Feeds (Greenhouse, Lever, Ashby, SmartRecruiters) */}
                    {liveJobs.length > 0 && (
                        <div className="space-y-3 p-4 rounded-2xl bg-surface border border-emerald-500/30">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                    <span className="relative flex h-2.5 w-2.5">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                                    </span>
                                    <h3 className="font-bold text-sm text-fg">Live Career Page Feed ({liveJobs.length} active roles)</h3>
                                    <span className="badge text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                        Greenhouse · Lever · Ashby · SmartRecruiters
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        type="button"
                                        onClick={() => setLiveMinCtc15((prev) => !prev)}
                                        className={cx(
                                            'px-2.5 py-1 rounded-full text-xs font-semibold border transition-all flex items-center gap-1.5',
                                            liveMinCtc15
                                                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                                                : 'bg-surface-2 border-line text-subtle hover:text-fg'
                                        )}
                                        title="Toggle minimum CTC threshold >= 15 LPA for freshers"
                                    >
                                        <span>≥ 15 LPA</span>
                                        {liveMinCtc15 && <Check className="h-3 w-3" />}
                                    </button>
                                    <span className="text-xs text-subtle font-mono hidden sm:inline">
                                        Deterministic match ≥ 50
                                    </span>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {liveJobs.slice(0, 8).map((lj) => {
                                    const isNew = lj.discovered_at && (Date.now() - new Date(lj.discovered_at).getTime()) < 86400000;
                                    const isApplied = lj.status === 'manual_applied' || lj.status === 'applied_confirmed';

                                    return (
                                        <div key={lj.id} className="p-3 rounded-xl bg-surface-2 border border-line flex flex-col justify-between gap-2.5">
                                            <div>
                                                <div className="flex items-center justify-between gap-2">
                                                    <span className="font-bold text-sm text-fg truncate">{lj.company}</span>
                                                    <div className="flex items-center gap-1.5 shrink-0">
                                                        {isNew && (
                                                            <span className="badge text-[9px] font-bold bg-emerald-500 text-black px-1.5 py-0.2">
                                                                NEW
                                                            </span>
                                                        )}
                                                        <span className="badge text-[10px] font-mono bg-surface border border-line text-emerald-400 font-bold">
                                                            {lj.match_score}% Match
                                                        </span>
                                                    </div>
                                                </div>
                                                <p className="text-xs text-muted font-medium mt-0.5 truncate">{lj.role}</p>
                                                <div className="flex items-center gap-2 text-[11px] text-subtle mt-1 flex-wrap">
                                                    <span className="badge text-[10px] uppercase font-mono bg-surface border border-line">{lj.source}</span>
                                                    <span className="badge text-[10px] font-mono text-cyan-400 bg-surface border border-cyan-500/30 font-semibold">{fmtEstCtc(lj)}</span>
                                                    <span>·</span>
                                                    <span>{lj.location}</span>
                                                </div>
                                                <div className="flex flex-wrap gap-1 mt-2">
                                                    {(lj.skills || []).slice(0, 4).map((s, idx) => (
                                                        <span key={idx} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface border border-line text-subtle">
                                                            {s}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-1.5 pt-2 border-t border-line/60">
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() => handleOpenPack(lj)}
                                                    className="text-xs py-1.5 px-2.5 shrink-0 border border-emerald-500/30 text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20"
                                                    title="Prepare customized screening answers grounded in verified facts"
                                                >
                                                    <Sparkles className="h-3 w-3 mr-1" />
                                                    Pack
                                                </Button>
                                                <a
                                                    href={lj.url}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="flex-1 inline-flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg bg-surface hover:bg-surface-3 border border-line text-xs font-semibold text-fg transition-all truncate"
                                                >
                                                    <span>Open Portal</span>
                                                    <ExternalLink className="h-3 w-3 shrink-0" />
                                                </a>
                                                <Button
                                                    size="sm"
                                                    variant={isApplied ? 'ghost' : 'primary'}
                                                    onClick={() => {
                                                        setConfirmModalJob(lj);
                                                        setConfirmRefInput('');
                                                        setConfirmNotesInput('');
                                                    }}
                                                    className="text-xs py-1.5 px-2.5 shrink-0"
                                                >
                                                    {isApplied ? (
                                                        <>
                                                            <CheckCheck className="h-3 w-3 mr-1 text-emerald-400" />
                                                            Applied
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Check className="h-3 w-3 mr-1" />
                                                            I Applied
                                                        </>
                                                    )}
                                                </Button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    <div className="flex items-center justify-between pt-2">
                        <h3 className="font-bold text-sm text-fg flex items-center gap-2">
                            <span>Curated List (Not Live)</span>
                            <span className="badge text-[10px] font-mono bg-surface-2 border border-line text-subtle">
                                {filteredJobs.length} curated portals (≥{minCtcFilter} LPA)
                            </span>
                        </h3>
                    </div>

                    {/* Job Opportunities Grid */}
                    <div className="space-y-3">
                        {filteredJobs.length === 0 ? (
                            <Empty
                                icon={Briefcase}
                                title="No matching 2027 openings"
                                action={<Button size="sm" onClick={() => { setQuery(''); setMinCtcFilter(15); setStatusFilter('all'); setRoleTypeFilter('all'); }}>Reset filters</Button>}
                            >
                                Try lowering your CTC threshold to ≥15 LPA or resetting search keywords.
                            </Empty>
                        ) : (
                            filteredJobs.slice(0, visibleCount).map((job) => {
                                const isExpanded = expandedJobId === job.id;
                                const isApplied = job.status === 'applied_confirmed' || job.status === 'manual_applied';

                                return (
                                    <Card
                                        key={job.id}
                                        className={cx(
                                            'card-pad transition-all border',
                                            isApplied ? 'border-emerald-500/30 bg-surface' : 'border-line hover:border-line-strong',
                                        )}
                                    >
                                        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                                            <div className="min-w-0 flex-1">
                                                <div className="flex items-center gap-2.5 flex-wrap">
                                                    <div className="grid place-items-center h-9 w-9 rounded-xl bg-surface-2 border border-line text-fg font-bold text-sm shrink-0">
                                                        {job.company.slice(0, 2).toUpperCase()}
                                                    </div>
                                                    <div>
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <h3 className="font-bold text-base text-fg tracking-tight">{job.company}</h3>
                                                            <span className="badge font-mono font-bold text-xs bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                                                {fmtEstCtc(job)}
                                                            </span>
                                                            {job.stipend_pm && (
                                                                <span className="badge text-[11px] font-mono bg-surface-2 border border-line text-subtle">
                                                                    {job.stipend_pm}
                                                                </span>
                                                            )}
                                                            {job.eligible_batches && (
                                                                <span className="badge text-[10px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                                                                    Batch {job.eligible_batches}
                                                                </span>
                                                            )}
                                                            {job.role.toLowerCase().includes('fte') ? (
                                                                <span className="badge text-[10px] font-bold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                                                                    FTE
                                                                </span>
                                                            ) : job.role.toLowerCase().includes('intern') ? (
                                                                <span className="badge text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                                                    Intern
                                                                </span>
                                                            ) : null}
                                                        </div>
                                                        <p className="text-xs text-muted mt-0.5">{job.role} · <span className="text-subtle">{job.location}</span></p>
                                                    </div>
                                                </div>

                                                <div className="flex flex-wrap items-center gap-1.5 mt-3">
                                                    {(job.skills_required || []).map((skill, idx) => (
                                                        <span key={idx} className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-surface-2 border border-line text-subtle">
                                                            {skill}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Action Column */}
                                            <div className="flex flex-col sm:items-end justify-between sm:justify-start gap-2 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-line">
                                                {job.status === 'skipped' ? (
                                                    <div className="flex flex-col sm:items-end gap-1">
                                                        <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-subtle bg-surface-2 border border-line px-3 py-1 rounded-full">
                                                            <span>Skipped</span>
                                                        </div>
                                                        <button
                                                            type="button"
                                                            onClick={() => handleUnmarkApplied(job.id, job.company)}
                                                            className="text-[10px] text-muted hover:text-amber-400 underline"
                                                            title="Restore opening to discovered"
                                                        >
                                                            Undo Skip
                                                        </button>
                                                    </div>
                                                ) : isApplied ? (
                                                    <div className="flex flex-col sm:items-end gap-1">
                                                        <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-3 py-1 rounded-full">
                                                            <CheckCheck className="h-3.5 w-3.5" /> Confirmed Real Application
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                            {job.application_ref && (
                                                                <span className="font-mono text-[10px] text-subtle">
                                                                    Your ref: #{job.application_ref}
                                                                </span>
                                                            )}
                                                            <button
                                                                type="button"
                                                                onClick={() => handleUnmarkApplied(job.id, job.company)}
                                                                className="text-[10px] text-muted hover:text-amber-400 underline"
                                                                title="Reset status if marked by mistake"
                                                            >
                                                                Undo
                                                            </button>
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="flex items-center gap-1.5 flex-wrap">
                                                        <a
                                                            href={job.portal_url || job.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="btn btn-primary btn-sm text-xs gap-1.5"
                                                            title="Launch official careers portal"
                                                        >
                                                            <span>Open Official Portal</span>
                                                            <ExternalLink className="h-3.5 w-3.5" />
                                                        </a>

                                                        <Button
                                                            size="sm"
                                                            variant="secondary"
                                                            onClick={() => {
                                                                setConfirmModalJob(job);
                                                                setConfirmRefInput('');
                                                                setConfirmNotesInput('');
                                                            }}
                                                            icon={Check}
                                                            className="text-xs border-emerald-500/30 hover:border-emerald-500"
                                                            title="Mark as applied after submitting on portal"
                                                        >
                                                            Mark Applied
                                                        </Button>
                                                    </div>
                                                )}

                                                <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => handleOpenPack(job)}
                                                        className="text-xs h-7 px-2.5 gap-1 border border-emerald-500/30 text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20"
                                                        title="Open application pack with tailored cover note, answers, and highlights"
                                                    >
                                                        <Sparkles className="h-3 w-3" />
                                                        <span>Prepare Answers</span>
                                                    </Button>

                                                    <button
                                                        type="button"
                                                        onClick={() => handleCopyFullPacket(job)}
                                                        className="btn btn-ghost btn-sm text-xs gap-1"
                                                        title="Copy full credentials and tailored answers to clipboard"
                                                    >
                                                        <Copy className="h-3.5 w-3.5" />
                                                        <span>Copy Packet</span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        onClick={() => handleDispatchEmailAlert(job)}
                                                        disabled={emailingJobId === job.id}
                                                        className="btn btn-ghost btn-sm text-xs gap-1 text-emerald-400"
                                                        title="Send full packet & official apply link to your email"
                                                    >
                                                        <Mail className="h-3.5 w-3.5" />
                                                        <span>{emailingJobId === job.id ? 'Sending…' : 'Email Me'}</span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                                                        className="btn btn-ghost btn-sm text-xs gap-1"
                                                        aria-expanded={isExpanded}
                                                    >
                                                        <span>{isExpanded ? 'Hide' : 'Answers'}</span>
                                                        <ChevronDown className={cx('h-3.5 w-3.5 transition-transform', isExpanded && 'rotate-180')} />
                                                    </button>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Expanded Drawer with ML Mimic Answers & Hiring Workflow */}
                                        {isExpanded && (
                                            <div className="mt-4 pt-3 border-t border-line space-y-3 text-xs animate-rise">
                                                <div className="grid sm:grid-cols-2 gap-3">
                                                    <div className="p-3 rounded-xl bg-surface-2/60 border border-line">
                                                        <div className="font-semibold text-fg flex items-center gap-1.5 mb-1.5">
                                                            <Clock className="h-3.5 w-3.5 text-accent" />
                                                            <span>Hiring Workflow & Rounds</span>
                                                        </div>
                                                        <p className="text-subtle leading-relaxed">{job.hiring_workflow}</p>
                                                    </div>

                                                    <div className="p-3 rounded-xl bg-surface-2/60 border border-line">
                                                        <div className="font-semibold text-fg flex items-center gap-1.5 mb-1.5">
                                                            <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
                                                            <span>Why Sai Qualifies (8.99 CGPA NIT Rourkela)</span>
                                                        </div>
                                                        <p className="text-subtle leading-relaxed">{job.notes}</p>
                                                    </div>
                                                </div>

                                                {job.ml_tailored_answers && (
                                                    <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-500/25 space-y-2">
                                                        <div className="flex items-center justify-between">
                                                            <div className="font-semibold text-emerald-400 flex items-center gap-1.5">
                                                                <Bot className="h-4 w-4" />
                                                                <span>Tailored Screening Answers (Ready to Paste)</span>
                                                            </div>
                                                            <button
                                                                type="button"
                                                                onClick={() => handleCopyFullPacket(job)}
                                                                className="btn btn-ghost btn-sm h-6 text-[10px] gap-1 text-emerald-400"
                                                            >
                                                                <Copy className="h-3 w-3" /> Copy All
                                                            </button>
                                                        </div>

                                                        <div className="space-y-2 text-subtle text-[11px] leading-relaxed">
                                                            <div>
                                                                <strong className="text-fg">Q: Why {job.company}?</strong>
                                                                <p className="mt-0.5 italic">"{job.ml_tailored_answers.why_company}"</p>
                                                            </div>
                                                            <div>
                                                                <strong className="text-fg">Q: Hardest technical concurrency challenge solved?</strong>
                                                                <p className="mt-0.5 italic">"{job.ml_tailored_answers.biggest_technical_challenge}"</p>
                                                            </div>
                                                            <div>
                                                                <strong className="text-fg">Q: Low-level systems & C++ background?</strong>
                                                                <p className="mt-0.5 italic">"{job.ml_tailored_answers.low_level_systems_experience}"</p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </Card>
                                );
                            })
                        )}

                        {visibleCount < filteredJobs.length && (
                            <div className="text-center pt-3 pb-2">
                                <Button
                                    variant="secondary"
                                    onClick={() => setVisibleCount((prev) => prev + 30)}
                                    className="text-xs"
                                >
                                    Load More Openings ({filteredJobs.length - visibleCount} remaining)
                                </Button>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* TAB 2: TRACK ALL 51 CAREER PORTALS */}
            {activeTab === 'portals' && (
                <div className="space-y-4">
                    <div className="p-4 rounded-2xl border border-emerald-500/30 bg-emerald-950/15 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div className="flex items-center gap-2.5">
                            <Globe className="h-5 w-5 text-emerald-400 shrink-0" />
                            <div>
                                <h3 className="font-bold text-sm text-fg">Continuous Career Portal Radar Directory</h3>
                                <p className="text-xs text-subtle">
                                    Actively tracking 51 premier tech career portals for new Batch 2027 CSE postings offering ≥15.0 LPA.
                                </p>
                            </div>
                        </div>
                        <Button
                            size="sm"
                            variant="primary"
                            onClick={handleRunScan}
                            loading={scanning}
                            icon={RefreshCw}
                        >
                            Trigger Radar Check
                        </Button>
                    </div>

                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {companyPortals.map((cp, idx) => (
                            <Card key={idx} className="card-pad border-line hover:border-emerald-500/40 transition-all flex flex-col justify-between">
                                <div>
                                    <div className="flex items-start justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                            <div className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line font-bold text-xs">
                                                {cp.company.slice(0, 2).toUpperCase()}
                                            </div>
                                            <div>
                                                <h4 className="font-bold text-sm text-fg leading-tight">{cp.company}</h4>
                                                <span className="text-[10px] text-emerald-400 flex items-center gap-1 font-mono">
                                                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                                    Active Hourly Check
                                                </span>
                                            </div>
                                        </div>

                                        <span className="badge text-[11px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                            {fmtCtc(cp.ctc_lpa)}
                                        </span>
                                    </div>

                                    <div className="mt-3 text-xs text-subtle space-y-1">
                                        <div><strong>Track:</strong> {cp.track}</div>
                                        <div><strong>Stipend:</strong> {cp.stipend_pm || '₹1,00,000/mo avg'}</div>
                                        <div><strong>Location:</strong> {cp.location}</div>
                                    </div>
                                </div>

                                <div className="mt-4 pt-3 border-t border-line flex items-center justify-between gap-2">
                                    <a
                                        href={cp.portal_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="btn btn-secondary btn-sm text-xs gap-1 flex-1 text-center justify-center"
                                    >
                                        <span>Official Careers</span>
                                        <ExternalLink className="h-3 w-3" />
                                    </a>
                                </div>
                            </Card>
                        ))}
                    </div>
                </div>
            )}

            {/* TAB 3: CONFIRMED APPLICATIONS */}
            {activeTab === 'confirmed' && (
                <div className="space-y-4">
                    <div className="p-4 rounded-2xl border border-emerald-500/30 bg-emerald-950/15 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2.5">
                            <ShieldCheck className="h-5 w-5 text-emerald-400 shrink-0" />
                            <div>
                                <h3 className="font-bold text-sm text-fg">Confirmed Real Applications</h3>
                                <p className="text-xs text-subtle">
                                    Applications you have genuinely submitted on the company careers portal and entered into your tracker.
                                </p>
                            </div>
                        </div>
                        <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => navigate('placements')}
                            icon={Briefcase}
                        >
                            Open Placements Kanban
                        </Button>
                    </div>

                    {confirmedJobs.length === 0 ? (
                        <Empty
                            icon={CheckCircle2}
                            title="No confirmed applications yet"
                            action={<Button size="sm" onClick={() => setActiveTab('openings')}>Browse 2027 Openings</Button>}
                        >
                            When you submit an application on an official company portal, click "Mark Applied" and enter your confirmation reference to track it here.
                        </Empty>
                    ) : (
                        <div className="grid sm:grid-cols-2 gap-4">
                            {confirmedJobs.map((cj) => (
                                <Card key={cj.id} className="card-pad border-line hover:border-emerald-500/40 transition-all flex flex-col justify-between">
                                    <div>
                                        <div className="flex items-start justify-between gap-2 mb-2">
                                            <div className="flex items-center gap-2">
                                                <div className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line font-bold text-xs">
                                                    {cj.company.slice(0, 2).toUpperCase()}
                                                </div>
                                                <div>
                                                    <h4 className="font-bold text-sm text-fg leading-tight">{cj.company}</h4>
                                                    <div className="text-[11px] text-emerald-400 font-medium">✓ Real Portal Submission Confirmed</div>
                                                </div>
                                            </div>
                                            <span className="badge text-[11px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                                {fmtCtc(cj.ctc_lpa)}
                                            </span>
                                        </div>

                                        <div className="p-2.5 rounded-xl bg-surface-2 border border-line my-2.5">
                                            <div className="text-[11px] text-subtle font-medium">Your reference:</div>
                                            <div className="font-mono font-bold text-sm text-fg flex items-center justify-between mt-0.5">
                                                <span>{cj.application_ref ? `#${cj.application_ref}` : 'None provided'}</span>
                                                {cj.application_ref && (
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            if (navigator.clipboard) {
                                                                navigator.clipboard.writeText(cj.application_ref);
                                                                toast('Copied reference ID', 'success');
                                                            }
                                                        }}
                                                        className="text-subtle hover:text-fg text-xs flex items-center gap-1"
                                                    >
                                                        <Copy className="h-3.5 w-3.5" />
                                                    </button>
                                                )}
                                            </div>
                                        </div>

                                        <p className="text-xs text-subtle leading-relaxed">
                                            Role: <strong>{cj.role}</strong> · {cj.location}
                                        </p>
                                    </div>

                                    <div className="mt-4 pt-3 border-t border-line flex items-center justify-between gap-2">
                                        <a
                                            href={cj.portal_url || cj.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="btn btn-ghost btn-sm text-xs gap-1"
                                        >
                                            <ExternalLink className="h-3 w-3" />
                                            <span>Portal Link</span>
                                        </a>

                                        <button
                                            type="button"
                                            onClick={() => handleUnmarkApplied(cj.id, cj.company)}
                                            className="btn btn-ghost btn-sm text-xs text-muted hover:text-amber-400"
                                        >
                                            Reset Status
                                        </button>
                                    </div>
                                </Card>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* TAB 4: OA & TECHNICAL BLUEPRINTS */}
            {activeTab === 'blueprints' && (
                <div className="space-y-4">
                    <div className="p-4 rounded-2xl border border-cyan-500/30 bg-cyan-950/15 flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2.5">
                            <Cpu className="h-5 w-5 text-cyan-400 shrink-0" />
                            <div>
                                <h3 className="font-bold text-sm text-fg">Technical Interview & OA Blueprints</h3>
                                <p className="text-xs text-subtle">
                                    Assessment platform specifications, test durations, and high-frequency topics for each target company.
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {blueprints.map((bp, idx) => (
                            <Card key={idx} className="card-pad border-line hover:border-cyan-500/40 transition-all flex flex-col justify-between">
                                <div>
                                    <div className="flex items-start justify-between gap-2">
                                        <div>
                                            <h4 className="font-bold text-sm text-fg">{bp.company}</h4>
                                            <p className="text-xs text-muted">{bp.role}</p>
                                        </div>
                                        <span className="badge text-[11px] font-mono font-bold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                                            {fmtCtc(bp.ctc_lpa)}
                                        </span>
                                    </div>

                                    <div className="mt-3 p-2.5 rounded-xl bg-surface-2 border border-line text-xs space-y-1.5">
                                        <div>
                                            <strong className="text-fg">OA Platform:</strong>{' '}
                                            <span className="font-semibold text-emerald-400">{bp.oa_platform}</span>
                                        </div>
                                        <div>
                                            <strong className="text-fg">Timeline:</strong> {bp.oa_timeline}
                                        </div>
                                    </div>

                                    <div className="mt-2.5 text-xs">
                                        <div className="font-semibold text-fg mb-1">High-Frequency Topics:</div>
                                        <div className="flex flex-wrap gap-1">
                                            {(bp.core_topics || []).map((t, i) => (
                                                <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface border border-line text-subtle">
                                                    {t}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                <div className="mt-4 pt-3 border-t border-line">
                                    <a
                                        href={bp.portal_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="btn btn-secondary btn-sm text-xs gap-1 w-full justify-center"
                                    >
                                        <span>Check Official Careers</span>
                                        <ExternalLink className="h-3 w-3" />
                                    </a>
                                </div>
                            </Card>
                        ))}
                    </div>
                </div>
            )}

            {/* Live Hourly Scan Audit Terminal */}
            <Card className="overflow-hidden border-line">
                <button
                    type="button"
                    onClick={() => setTerminalOpen(!terminalOpen)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-surface-2 text-xs font-semibold text-fg hover:bg-surface-2/80 transition-colors"
                >
                    <div className="flex items-center gap-2 font-mono">
                        <Terminal className="h-4 w-4 text-emerald-400" />
                        <span>Background Hourly Scanner & Portal Radar Audit Log</span>
                    </div>
                    <span className="text-subtle">{terminalOpen ? 'Collapse' : 'Expand'}</span>
                </button>

                {terminalOpen && (
                    <div className="p-4 bg-black/90 font-mono text-[11px] text-emerald-400 space-y-1.5 max-h-60 overflow-y-auto no-scrollbar border-t border-line">
                        {recentLogs.flatMap((log) => log.log_details || []).map((item, idx) => (
                            <div key={idx} className="flex items-start gap-2">
                                <span className="text-subtle shrink-0">[{item.time}]</span>
                                <span className={cx(item.event.includes('Applied') || item.event.includes('Confirmed') ? 'text-cyan-300 font-bold' : 'text-emerald-400/90')}>
                                    {item.event}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </Card>

            {/* CONFIRM REAL APPLICATION MODAL */}
            <Sheet
                open={Boolean(confirmModalJob)}
                onClose={() => setConfirmModalJob(null)}
                title="Confirm Real Application Submission"
            >
                {confirmModalJob && (
                    <div className="space-y-4 text-xs">
                        <div className="p-4 rounded-2xl bg-surface-2 border border-line space-y-2">
                            <h3 className="text-base font-bold text-fg">
                                Record Submission for {confirmModalJob.company}
                            </h3>
                            <p className="text-subtle">
                                Position: <strong>{confirmModalJob.role}</strong> · {fmtCtc(confirmModalJob.ctc_lpa)}
                            </p>
                            <p className="text-muted leading-relaxed">
                                In adherence to your strict integrity rule, this will officially record your real application in your database and sync it directly into your Placements Kanban pipeline.
                            </p>
                        </div>

                        <div className="space-y-3">
                            <div>
                                <label className="block font-semibold text-fg mb-1">
                                    Your Confirmation Reference (Optional):
                                </label>
                                <input
                                    type="text"
                                    placeholder="e.g. UBER-104928, or leave blank if none"
                                    value={confirmRefInput}
                                    onChange={(e) => setConfirmRefInput(e.target.value)}
                                    maxLength={100}
                                    className="input text-xs w-full font-mono"
                                />
                                <span className="text-[11px] text-muted mt-1 block">
                                    Optional reference number from the confirmation screen or email from {confirmModalJob.company}.
                                </span>
                            </div>

                            <div>
                                <label className="block font-semibold text-fg mb-1">
                                    Notes (Optional):
                                </label>
                                <textarea
                                    rows={2}
                                    placeholder="e.g. Applied with resume version v2; referral through alumnus..."
                                    value={confirmNotesInput}
                                    onChange={(e) => setConfirmNotesInput(e.target.value)}
                                    maxLength={500}
                                    className="input text-xs w-full"
                                />
                            </div>
                        </div>

                        <div className="pt-2 flex items-center justify-end gap-2">
                            <Button
                                variant="ghost"
                                onClick={() => setConfirmModalJob(null)}
                            >
                                Cancel
                            </Button>
                            <Button
                                variant="primary"
                                onClick={handleConfirmSubmit}
                                loading={confirming}
                                icon={CheckCheck}
                            >
                                Save Real Application
                            </Button>
                        </div>
                    </div>
                )}
            </Sheet>

            {/* Candidate Profile Diagnostics Modal */}
            <Sheet
                open={mlDrawerOpen}
                onClose={() => setMlDrawerOpen(false)}
                title="Candidate Profile & Skill Diagnostics"
            >
                <div className="space-y-4 text-xs">
                    <p className="text-subtle leading-relaxed">
                        Candidate profile representation for <strong>Nandam Venkata Sai Raghava</strong> based on verified
                        resume metrics, technical project facts, and CP credentials. Used to answer custom screening questions
                        accurately reflecting Sai's real technical implementations.
                    </p>

                    <div className="space-y-2">
                        <h4 className="font-bold text-fg uppercase tracking-wider text-[11px]">Feature Weights & Competencies</h4>
                        <div className="space-y-1.5">
                            {[
                                { name: 'Tier 1 Institution (NIT Rourkela)', val: '1.00', desc: 'Auto-passes Tier-1 campus screening filters' },
                                { name: 'High CGPA (8.99 / 10.0)', val: '0.90', desc: 'Clears all 7.5+ & 8.0+ cutoffs (DE Shaw, Uber)' },
                                { name: 'Competitive Programming (LC 1709, CF 1425)', val: '0.85', desc: 'Solves 900+ LC, strong graph & DP accuracy' },
                                { name: 'Distributed Systems & Microservices', val: '0.96', desc: 'Kafka 13 topics, Redis Lua locks, Saga rollback' },
                                { name: 'Systems Concurrency (C++ Cache Server)', val: '0.94', desc: 'Raw TCP sockets, RESP parser, mutex thread pool' },
                                { name: 'Enterprise Production Experience (MSIL)', val: '0.92', desc: '13 React pages, 120+ REST APIs, JWT, RBAC' },
                            ].map((feat, i) => (
                                <div key={i} className="p-2.5 rounded-lg bg-surface-2 border border-line flex items-center justify-between">
                                    <div>
                                        <div className="font-semibold text-fg">{feat.name}</div>
                                        <div className="text-[10px] text-subtle">{feat.desc}</div>
                                    </div>
                                    <span className="font-mono text-emerald-400 font-bold text-xs">{feat.val}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <Button variant="primary" onClick={() => setMlDrawerOpen(false)} className="w-full">
                        Close Inspector
                    </Button>
                </div>
            </Sheet>

            {/* Application Pack Drawer (Grounded in Verified Resume Facts) */}
            <Sheet
                open={!!packDrawerJob}
                onClose={() => { setPackDrawerJob(null); setPackData(null); }}
                wide={true}
            >
                <div className="space-y-5 p-4 sm:p-6 text-xs">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-3 pb-3 border-b border-line">
                        <div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-bold text-base text-fg tracking-tight">
                                    {packDrawerJob?.company}
                                </span>
                                <span className="badge text-xs font-mono font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30">
                                    {fmtEstCtc(packDrawerJob)}
                                </span>
                                {packData?.model === 'template' ? (
                                    <span className="badge text-[10px] font-mono bg-amber-500/10 text-amber-400 border border-amber-500/30">
                                        ⚡ Deterministic Template (Verified Facts)
                                    </span>
                                ) : (
                                    <span className="badge text-[10px] font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                                        ✨ {packData?.model || 'LLM Tailored'}
                                    </span>
                                )}
                            </div>
                            <p className="text-xs text-muted mt-0.5">
                                {packDrawerJob?.role} · <span className="text-subtle">{packDrawerJob?.location}</span>
                            </p>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0">
                            <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => handleOpenPack(packDrawerJob, true)}
                                loading={packLoading}
                                icon={RefreshCw}
                                className="text-xs"
                                title="Regenerate application pack"
                            >
                                Regenerate
                            </Button>
                            <button
                                type="button"
                                onClick={() => { setPackDrawerJob(null); setPackData(null); }}
                                className="p-1 rounded-lg text-subtle hover:text-fg hover:bg-surface-2 transition-all"
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                    </div>

                    {/* Disclaimer Note to Sai */}
                    <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-2.5 text-amber-300">
                        <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" />
                        <div className="text-[11px] leading-relaxed">
                            <strong>Candidate Notice:</strong> Every technical claim here comes directly from your verified NIT Rourkela projects (Railway microservices, C++ cache server) and CP rating. <em>Availability and relocation answers are grounded defaults</em> — please review them before submitting on the official portal.
                        </div>
                    </div>

                    {/* Action Toolbar */}
                    <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-xl bg-surface-2 border border-line">
                        <div className="flex items-center gap-2">
                            <Button
                                size="sm"
                                variant="primary"
                                onClick={handleCopyFullPack}
                                icon={copiedField === 'full_pack' ? CheckCheck : Copy}
                                className="text-xs"
                            >
                                {copiedField === 'full_pack' ? 'Copied Full Pack!' : 'Copy Full Pack'}
                            </Button>
                            {(packData?.url || packDrawerJob?.portal_url || packDrawerJob?.url) && (
                                <a
                                    href={packData?.url || packDrawerJob?.portal_url || packDrawerJob?.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="btn btn-secondary btn-sm text-xs gap-1"
                                >
                                    <span>Open Official Portal</span>
                                    <ExternalLink className="h-3 w-3" />
                                </a>
                            )}
                        </div>

                        <span className="text-[11px] font-mono text-subtle">
                            {packData?.cached ? 'Cached' : 'Freshly Generated'}
                        </span>
                    </div>

                    {packError && (
                        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 space-y-2">
                            <div className="flex items-center gap-2 font-semibold text-sm">
                                <AlertCircle className="h-4 w-4 text-red-400" />
                                <span>Could not load application pack</span>
                            </div>
                            <p className="text-xs text-subtle">{packError}</p>
                            <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => handleOpenPack(packDrawerJob, true)}
                                icon={RefreshCw}
                                className="text-xs mt-1"
                            >
                                Retry
                            </Button>
                        </div>
                    )}

                    {packLoading && !packData ? (
                        <div className="space-y-4 py-8 text-center">
                            <Skeleton className="h-20 w-full rounded-xl" />
                            <Skeleton className="h-28 w-full rounded-xl" />
                            <Skeleton className="h-24 w-full rounded-xl" />
                        </div>
                    ) : packData ? (
                        <div className="space-y-5">
                            {/* 1. Cover Note */}
                            <div className="p-3.5 rounded-xl bg-surface-2 border border-line space-y-2">
                                <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2">
                                        <FileText className="h-4 w-4 text-emerald-400" />
                                        <h4 className="font-bold text-fg text-xs uppercase tracking-wider">Tailored Cover Note</h4>
                                        <span className="badge text-[10px] font-mono bg-surface border border-line text-subtle">
                                            {countWords(packData.cover_note)} words
                                        </span>
                                    </div>
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => handleCopyField('Cover Note', packData.cover_note)}
                                        icon={copiedField === 'Cover Note' ? Check : Copy}
                                        className="text-xs h-7 px-2"
                                    >
                                        {copiedField === 'Cover Note' ? 'Copied' : 'Copy Note'}
                                    </Button>
                                </div>
                                <div className="p-3 rounded-lg bg-surface border border-line text-fg font-sans leading-relaxed text-xs whitespace-pre-wrap select-all">
                                    {packData.cover_note}
                                </div>
                            </div>

                            {/* 2. Why Company */}
                            <div className="p-3.5 rounded-xl bg-surface-2 border border-line space-y-2">
                                <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2">
                                        <Building2 className="h-4 w-4 text-cyan-400" />
                                        <h4 className="font-bold text-fg text-xs uppercase tracking-wider">Why {packData.company}?</h4>
                                        <span className="badge text-[10px] font-mono bg-surface border border-line text-subtle">
                                            {countWords(packData.why_company)} words
                                        </span>
                                    </div>
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => handleCopyField(`Why ${packData.company}`, packData.why_company)}
                                        icon={copiedField === `Why ${packData.company}` ? Check : Copy}
                                        className="text-xs h-7 px-2"
                                    >
                                        {copiedField === `Why ${packData.company}` ? 'Copied' : 'Copy Answer'}
                                    </Button>
                                </div>
                                <div className="p-3 rounded-lg bg-surface border border-line text-fg font-sans leading-relaxed text-xs whitespace-pre-wrap select-all">
                                    {packData.why_company}
                                </div>
                            </div>

                            {/* 3. Screening Q&A */}
                            <div className="space-y-3">
                                <div className="flex items-center gap-2">
                                    <Target className="h-4 w-4 text-purple-400" />
                                    <h4 className="font-bold text-fg text-xs uppercase tracking-wider">Screening Answers ({packData.answers?.length || 0})</h4>
                                </div>

                                {(packData.answers || []).map((item, idx) => (
                                    <div key={idx} className="p-3 rounded-xl bg-surface-2 border border-line space-y-2">
                                        <div className="flex items-start justify-between gap-2">
                                            <div className="font-semibold text-fg text-xs pr-2">
                                                {item.question}
                                            </div>
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => handleCopyField(`Answer ${idx + 1}`, item.answer)}
                                                icon={copiedField === `Answer ${idx + 1}` ? Check : Copy}
                                                className="text-xs h-6 px-2 shrink-0"
                                            >
                                                {copiedField === `Answer ${idx + 1}` ? 'Copied' : 'Copy'}
                                            </Button>
                                        </div>
                                        <div className="p-2.5 rounded-lg bg-surface border border-line text-muted text-xs leading-relaxed select-all">
                                            {item.answer}
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* 4. Resume Highlights */}
                            <div className="p-3.5 rounded-xl bg-surface-2 border border-line space-y-2.5">
                                <div>
                                    <div className="flex items-center gap-2">
                                        <Award className="h-4 w-4 text-amber-400" />
                                        <h4 className="font-bold text-fg text-xs uppercase tracking-wider">Matched Resume Highlights</h4>
                                    </div>
                                    <p className="text-[10px] text-subtle mt-0.5">
                                        Selected based on skill overlap with {packData.company}
                                    </p>
                                </div>
                                <div className="space-y-2">
                                    {(packData.resume_highlights || []).map((bullet, idx) => (
                                        <div key={idx} className="p-2.5 rounded-lg bg-surface border border-line flex items-start justify-between gap-2 text-xs">
                                            <div className="leading-relaxed text-muted select-all">• {bullet}</div>
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={() => handleCopyField(`Highlight ${idx + 1}`, bullet)}
                                                icon={copiedField === `Highlight ${idx + 1}` ? Check : Copy}
                                                className="text-[11px] h-6 px-2 shrink-0"
                                            >
                                                {copiedField === `Highlight ${idx + 1}` ? 'Copied' : 'Copy'}
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* 5. Matched Skills */}
                            {packData.matched_skills?.length > 0 && (
                                <div className="flex flex-wrap items-center gap-1.5 pt-2">
                                    <span className="text-subtle font-medium text-[11px]">Matched Skills:</span>
                                    {packData.matched_skills.map((s, idx) => (
                                        <span key={idx} className="badge text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                            {s}
                                        </span>
                                    ))}
                                </div>
                            )}

                            {/* Footer Submit confirmation */}
                            <div className="pt-3 border-t border-line flex items-center justify-between gap-3">
                                <a
                                    href={packData.url || packDrawerJob?.portal_url || packDrawerJob?.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="btn btn-secondary text-xs gap-1.5"
                                >
                                    <span>Open Portal</span>
                                    <ExternalLink className="h-3.5 w-3.5" />
                                </a>

                                <Button
                                    variant="primary"
                                    onClick={() => {
                                        const jobToConfirm = packDrawerJob;
                                        setPackDrawerJob(null);
                                        setPackData(null);
                                        setConfirmModalJob(jobToConfirm);
                                        setConfirmRefInput('');
                                        setConfirmNotesInput('');
                                    }}
                                    icon={CheckCheck}
                                    className="text-xs"
                                >
                                    I Submitted On Portal
                                </Button>
                            </div>
                        </div>
                    ) : null}
                </div>
            </Sheet>
        </div>
    );
}
