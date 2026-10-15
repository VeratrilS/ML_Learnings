import { useMemo, useState, useEffect, useCallback, useRef } from 'react';
import {
    Bookmark, BookOpen, Check, ChevronDown, ChevronRight, ChevronsDownUp,
    ChevronsUpDown, Code2, ExternalLink, Flame, Layers, ListChecks,
    RotateCw, Search, Sparkles
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi, useLocalStorage } from '../lib/hooks';
import { Button, Card, Checkbox, Empty, ProgressBar, Segmented, Skeleton, cx, useToast } from './ui';
import { TodayPill } from './LearnCard';
import SprintRunway from './SprintRunway';
import DailyFocusCard from './DailyFocusCard';

// Optimistically flip one problem and recompute totals
function patchProblem(data, id, done) {
    let delta = 0;
    const problems = data.problems.map((p) => {
        if (p.id !== id || p.done === done) return p;
        if (done) delta += 1;
        else if (p.done_day === data.day) delta -= 1;
        return { ...p, done, done_day: done ? data.day : null, done_at: done ? new Date().toISOString() : null };
    });
    const solved = problems.filter((p) => p.done);
    const by_difficulty = Object.fromEntries(Object.entries(data.by_difficulty || {}).map(([d, v]) => [
        d, { ...v, done: solved.filter((p) => p.difficulty === d).length },
    ]));
    return {
        ...data, problems, by_difficulty,
        done: solved.length,
        progress: data.total ? Math.round((100 * solved.length) / data.total) : 0,
        next: problems.find((p) => !p.done) || null,
        done_today: Math.max(0, (data.done_today || 0) + delta),
    };
}

// Difficulty pill style
function DifficultyPill({ difficulty }) {
    const diff = String(difficulty || '').toLowerCase();
    let style = 'bg-slate-500/10 text-slate-400 border border-slate-500/20';
    let label = 'Medium';

    if (diff === 'medium') {
        style = 'bg-amber-500/10 text-amber-500 dark:text-amber-400 border border-amber-500/20';
        label = 'Medium';
    } else if (diff === 'hard') {
        style = 'bg-rose-500/10 text-rose-500 dark:text-rose-400 border border-rose-500/20';
        label = 'Hard';
    }

    return (
        <span className={cx('inline-flex shrink-0 items-center justify-center rounded px-2 py-0.5 text-[11px] font-semibold tracking-wide', style)}>
            {label}
        </span>
    );
}

// Problem row with intact direct LeetCode links and detailed topic tags:
// PROBLEM | DIFFICULTY | PRACTICE (LeetCode) | READ | LINK
function ProblemRow({
    problem, isNext, isBookmarked, onToggle, onToggleBookmark
}) {
    const leetcodeUrl = problem.practice_url || problem.url || (problem.leetcode_id ? `https://leetcode.com/problems/${problem.slug}/` : null);
    const platformLabel = problem.platform || 'LeetCode';
    const isLeetCode = platformLabel.toLowerCase() === 'leetcode';

    return (
        <li className={cx(
            'flex flex-col md:flex-row md:items-center justify-between gap-3 px-3.5 sm:px-6 py-3 transition-colors border-b border-line/40 last:border-b-0 hover:bg-surface-2/40',
            problem.done && 'bg-surface-1/40',
            isNext && 'bg-accent-soft/30 hover:bg-accent-soft/40'
        )}>
            {/* Column 1: Checkbox + Bookmark + Position + Title + Detailed Topics */}
            <div className="flex items-start gap-3 min-w-0 flex-1 md:max-w-[52%]">
                <div className="pt-0.5">
                    <Checkbox
                        checked={problem.done}
                        onChange={(v) => onToggle(problem, v)}
                        label={problem.done ? `Unmark ${problem.title}` : `Mark ${problem.title} solved`}
                    />
                </div>

                <button
                    type="button"
                    onClick={() => onToggleBookmark(problem.id)}
                    className={cx(
                        'p-1 mt-0.5 rounded transition-colors shrink-0',
                        isBookmarked ? 'text-amber-500 hover:text-amber-600' : 'text-subtle hover:text-fg'
                    )}
                    title={isBookmarked ? 'Remove from revision' : 'Mark for revision'}
                    aria-label={isBookmarked ? 'Remove from revision' : 'Mark for revision'}
                >
                    <Bookmark className={cx('h-3.5 w-3.5', isBookmarked && 'fill-amber-500')} />
                </button>

                <div className="min-w-0 flex-1">
                    <a
                        href={leetcodeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className={cx(
                            'block text-[13px] sm:text-sm font-medium leading-snug truncate hover:text-accent transition-colors',
                            problem.done ? 'text-muted line-through' : 'text-fg font-semibold'
                        )}
                        title={`Open ${problem.title} on ${platformLabel}`}
                    >
                        <span className="font-mono text-subtle text-xs mr-1 font-normal">#{problem.position}.</span>
                        {problem.title}
                    </a>

                    {/* Up next badge if applicable (no topic spoilers) */}
                    {isNext && (
                        <div className="mt-1">
                            <span className="badge bg-accent text-accent-fg text-[10px] font-semibold">
                                Up next
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Right side columns: DIFFICULTY | PRACTICE (LeetCode) | READ | LINK */}
            <div className="flex items-center justify-between md:justify-end gap-2 sm:gap-4 shrink-0 pl-9 md:pl-0">
                {/* Column 2: DIFFICULTY */}
                <div className="w-16 sm:w-20 text-center shrink-0">
                    <DifficultyPill difficulty={problem.difficulty} />
                </div>

                {/* Column 3: PRACTICE (Direct LeetCode Link) */}
                <div className="w-28 sm:w-32 shrink-0 flex justify-center">
                    <a
                        href={leetcodeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className={cx(
                            'inline-flex items-center gap-1.5 rounded font-semibold text-[11px] px-2.5 py-1 transition-colors',
                            isLeetCode
                                ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                                : 'bg-accent/10 hover:bg-accent/20 text-accent'
                        )}
                        title={`Solve on ${platformLabel}`}
                    >
                        <Code2 className="h-3 w-3" />
                        <span>{platformLabel}</span>
                    </a>
                </div>

                {/* Column 4: READ (📖 Editorial or Article) */}
                <div className="w-20 sm:w-24 shrink-0 flex justify-center">
                    {problem.article_url ? (
                        <a
                            href={problem.article_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 rounded bg-surface-2 hover:bg-surface-3 text-fg font-medium text-[11px] px-2 py-1 transition-colors"
                            title="Read Editorial"
                        >
                            <BookOpen className="h-3 w-3 text-subtle" />
                            <span>Editorial</span>
                        </a>
                    ) : (
                        <span className="text-[11px] text-subtle font-mono">-</span>
                    )}
                </div>

                {/* Column 5: LINK (Direct external icon to LeetCode) */}
                <div className="w-8 shrink-0 flex justify-center">
                    {leetcodeUrl ? (
                        <a
                            href={leetcodeUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1.5 text-subtle hover:text-accent transition-colors rounded hover:bg-surface-2"
                            title={`Open directly on ${platformLabel}`}
                            aria-label={`Open directly on ${platformLabel}`}
                        >
                            <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                    ) : (
                        <span className="text-[11px] text-subtle font-mono">-</span>
                    )}
                </div>
            </div>
        </li>
    );
}

/** Level 2: Submodule Pattern Accordion — collapsed by default when module opens */
function SubmoduleAccordion({
    submodule, isOpen, onToggle, onProblemToggle, nextId,
    revisions, onToggleBookmark
}) {
    const isComplete = submodule.total > 0 && submodule.done === submodule.total;

    return (
        <div className="border-t border-line/60 first:border-t-0">
            {/* Submodule header button: collapsed by default, click to open */}
            <button
                type="button"
                onClick={onToggle}
                className={cx(
                    'w-full flex items-center justify-between gap-3 pl-6 sm:pl-10 pr-4 sm:pr-6 py-2.5 text-left transition-colors',
                    isOpen ? 'bg-surface-2/60 font-semibold' : 'bg-surface-2/20 hover:bg-surface-2/50'
                )}
                aria-expanded={isOpen}
            >
                <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-subtle shrink-0">
                        {isOpen ? <ChevronDown className="h-3.5 w-3.5 text-accent" /> : <ChevronRight className="h-3.5 w-3.5" />}
                    </span>
                    <span className="font-semibold text-xs sm:text-[13px] text-fg truncate">
                        {submodule.name}
                    </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                    {isComplete ? (
                        <span className="badge bg-ok/15 text-ok text-[11px] font-semibold flex items-center gap-1">
                            <Check className="h-2.5 w-2.5" /> {submodule.total} done
                        </span>
                    ) : (
                        <span className="badge bg-surface-1 font-mono text-[11px] text-subtle">
                            <span className={submodule.done > 0 ? 'text-fg font-semibold' : ''}>{submodule.done}</span> / {submodule.total}
                        </span>
                    )}
                    {submodule.problems.length !== submodule.total && (
                        <span className="badge bg-accent-soft text-accent text-[11px]">
                            {submodule.problems.length} shown
                        </span>
                    )}
                </div>
            </button>

            {/* Submodule Problems Table — ONLY shown when user clicks to open this specific subtopic */}
            {isOpen && (
                <div>
                    {/* Column Headers */}
                    <div className="hidden md:flex items-center justify-between px-6 py-1.5 bg-surface-2/40 border-y border-line/50 text-[10px] font-bold tracking-wider uppercase text-subtle">
                        <div className="flex-1 max-w-[52%] pl-10">Problem &amp; Pattern</div>
                        <div className="flex items-center gap-4 shrink-0">
                            <div className="w-20 text-center">Difficulty</div>
                            <div className="w-32 text-center">Practice (LeetCode)</div>
                            <div className="w-24 text-center">Read</div>
                            <div className="w-8 text-center">Link</div>
                        </div>
                    </div>

                    <ul className="bg-surface-1/40 divide-y divide-line/30">
                        {submodule.problems.map((p) => (
                            <ProblemRow
                                key={p.id}
                                problem={p}
                                isNext={p.id === nextId}
                                isBookmarked={revisions.includes(p.id)}
                                onToggle={onProblemToggle}
                                onToggleBookmark={onToggleBookmark}
                            />
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

/** Level 1: Module Accordion */
function ModuleAccordion({
    module, isOpen, onToggle, onProblemToggle, nextId,
    openSubmodules, onToggleSubmodule, revisions, onToggleBookmark
}) {
    const isComplete = module.total > 0 && module.done === module.total;

    // Group problems by submodule in exact order
    const submodules = useMemo(() => {
        const order = [];
        const map = new Map();
        const allInMod = module.allProblems || [];

        allInMod.forEach((p) => {
            const name = p.sub_name || p.submodule_name || 'General';
            if (!map.has(name)) {
                map.set(name, { name, all: [], filtered: [] });
                order.push(name);
            }
            map.get(name).all.push(p);
        });

        module.problems.forEach((p) => {
            const name = p.sub_name || p.submodule_name || 'General';
            if (map.has(name)) {
                map.get(name).filtered.push(p);
            }
        });

        return order.map((name) => {
            const item = map.get(name);
            return {
                key: `${module.id}:${name}`,
                name,
                problems: item.filtered,
                total: item.all.length,
                done: item.all.filter((p) => p.done).length,
            };
        });
    }, [module]);

    return (
        <div className="border-b border-line last:border-b-0">
            {/* Module header button */}
            <button
                type="button"
                onClick={onToggle}
                className={cx(
                    'w-full flex items-center justify-between gap-3 px-4 sm:px-6 py-3.5 text-left transition-colors',
                    isOpen ? 'bg-surface-2/80 font-bold' : 'hover:bg-surface-2/40',
                )}
                aria-expanded={isOpen}
            >
                <div className="flex items-center gap-3.5 min-w-0">
                    <span className="text-subtle shrink-0">
                        {isOpen ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4" />}
                    </span>
                    <span className="font-mono text-xs text-subtle font-semibold shrink-0">
                        {String(module.id).padStart(2, '0')}
                    </span>
                    <span className="font-bold text-sm text-fg truncate">
                        {module.name}
                    </span>
                </div>

                <div className="flex items-center gap-2.5 shrink-0">
                    <span className="text-xs text-subtle hidden sm:inline">
                        {module.submoduleCount ? `${module.submoduleCount} sub-modules` : ''}
                    </span>
                    {isComplete ? (
                        <span className="badge bg-ok/15 text-ok font-semibold text-xs flex items-center gap-1">
                            <Check className="h-3 w-3" /> {module.total} done
                        </span>
                    ) : (
                        <span className="badge bg-surface-2 font-mono text-xs text-subtle">
                            <span className={module.done > 0 ? 'text-fg font-semibold' : ''}>{module.done}</span> / {module.total}
                        </span>
                    )}
                    {module.problems.length !== module.total && (
                        <span className="badge bg-accent-soft text-accent text-xs">
                            {module.problems.length} shown
                        </span>
                    )}
                </div>
            </button>

            {/* When module is opened: ONLY subtopics are shown, all subtopics start collapsed */}
            {isOpen && (
                <div className="bg-surface-1/40">
                    {submodules.length > 0 ? (
                        submodules
                            .filter((sub) => sub.problems.length > 0)
                            .map((sub) => (
                                <SubmoduleAccordion
                                    key={sub.key}
                                    submodule={sub}
                                    isOpen={openSubmodules.has(sub.key)}
                                    onToggle={() => onToggleSubmodule(sub.key)}
                                    onProblemToggle={onProblemToggle}
                                    nextId={nextId}
                                    revisions={revisions}
                                    onToggleBookmark={onToggleBookmark}
                                />
                            ))
                    ) : (
                        <div className="py-4 text-center text-xs text-subtle">
                            No matching problems in this topic.
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/** Fraz's All DSA Patterns Sheet (1,019 Medium & Hard Problems across 24 Modules in Exact Fraz Order) */
export default function SheetTracker({ sheet = 'learnyard' }) {
    const activeSheetKey = sheet || 'learnyard';
    const { data, loading, error, setData, reload } = useApi(`/sheets/${activeSheetKey}`);
    const [filter, setFilter] = useLocalStorage(`sheet:${activeSheetKey}:filter_v7`, 'all');
    const [diff, setDiff] = useLocalStorage(`sheet:${activeSheetKey}:diff_v7`, 'all');
    const [revisionOnly, setRevisionOnly] = useState(false);
    const [revisions, setRevisions] = useLocalStorage(`sheet:${activeSheetKey}:revisions`, []);
    const [dailyIds, setDailyIds] = useLocalStorage(`sheet:${activeSheetKey}:daily25_ids`, []);
    const [q, setQ] = useState('');
    const [busy, setBusy] = useState(false);
    const toast = useToast();

    // Clean initial state: ALL modules start collapsed on page load so user can open their own wanted topic
    const [openModulesList, setOpenModulesList] = useState([]);
    // All submodules start collapsed too! Clicking a subtopic opens only that subtopic
    const [openSubmodulesList, setOpenSubmodulesList] = useState([]);

    const openModules = useMemo(() => new Set(openModulesList || []), [openModulesList]);
    const openSubmodules = useMemo(() => new Set(openSubmodulesList || []), [openSubmodulesList]);

    const problems = useMemo(() => data?.problems || [], [data]);
    const hasModules = Boolean(data?.modules?.length);

    const toggleBookmark = (id) => {
        setRevisions((prev) => {
            const list = Array.isArray(prev) ? prev : [];
            const next = list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
            toast(list.includes(id) ? 'Removed from revision list' : 'Added to revision list', 'info');
            return next;
        });
    };

    const shown = useMemo(() => {
        const needle = q.trim().toLowerCase();
        return problems.filter((p) =>
            (filter === 'todo' ? !p.done : filter === 'done' ? p.done : true)
            && (diff === 'all' || p.difficulty?.toLowerCase() === diff?.toLowerCase())
            && (!revisionOnly || revisions.includes(p.id))
            && (!needle || p.title.toLowerCase().includes(needle) || String(p.leetcode_id) === needle
                || p.topics.some((t) => t.toLowerCase().includes(needle))
                || (p.sub_name && p.sub_name.toLowerCase().includes(needle))
                || (p.mod_name && p.mod_name.toLowerCase().includes(needle))));
    }, [problems, filter, diff, revisionOnly, revisions, q]);

    // Group problems by module in exact Fraz order (1..24)
    const moduleGroups = useMemo(() => {
        if (!hasModules || !data?.modules) return null;

        return data.modules.map((m) => {
            const modProblems = shown.filter((p) => p.module_id === m.id || p.mod_id === m.id || (p.topics && p.topics[0] === m.name));
            const allModProblems = problems.filter((p) => p.module_id === m.id || p.mod_id === m.id || (p.topics && p.topics[0] === m.name));
            const doneCount = allModProblems.filter((p) => p.done).length;

            return {
                id: m.id,
                name: m.name,
                submoduleCount: m.submoduleCount,
                total: allModProblems.length || m.rowCount,
                done: doneCount,
                problems: modProblems,
                allProblems: allModProblems,
            };
        });
    }, [hasModules, data?.modules, shown, problems]);

    // Auto-expand matching modules & submodules ONLY when actively typing a new search query
    const prevQRef = useRef(q);
    useEffect(() => {
        const query = q.trim();
        if (query && query !== prevQRef.current && moduleGroups) {
            const matchingModIds = [];
            const matchingSubKeys = [];
            moduleGroups.forEach((m) => {
                if (m.problems.length > 0) {
                    matchingModIds.push(m.id);
                    m.problems.forEach((p) => {
                        const subName = p.sub_name || p.submodule_name || 'General';
                        matchingSubKeys.push(`${m.id}:${subName}`);
                    });
                }
            });
            if (matchingModIds.length > 0) {
                setOpenModulesList((prev) => Array.from(new Set([...(prev || []), ...matchingModIds])));
                setOpenSubmodulesList((prev) => Array.from(new Set([...(prev || []), ...matchingSubKeys])));
            }
        }
        prevQRef.current = query;
    }, [q, moduleGroups]);

    // Toggle single module: when opening, ensure its subtopics start collapsed
    const toggleModule = useCallback((modId) => {
        setOpenModulesList((prev) => {
            const list = Array.isArray(prev) ? prev : [];
            return list.includes(modId) ? list.filter((id) => id !== modId) : [...list, modId];
        });
        // Always reset this module's subtopics to collapsed so only subtopic names are shown
        setOpenSubmodulesList((prev) => {
            const list = Array.isArray(prev) ? prev : [];
            return list.filter((k) => !k.startsWith(`${modId}:`));
        });
    }, []);

    // Toggle single submodule: expands or collapses ONLY this specific subtopic
    const toggleSubmodule = useCallback((subKey) => {
        setOpenSubmodulesList((prev) => {
            const list = Array.isArray(prev) ? prev : [];
            return list.includes(subKey)
                ? list.filter((k) => k !== subKey)
                : [...list, subKey];
        });
    }, []);

    // Expand all modules (keeps all subtopics collapsed so only subtopics are listed, not all problems at once)
    const expandAll = useCallback(() => {
        if (data?.modules) {
            setOpenModulesList(data.modules.map((m) => m.id));
            setOpenSubmodulesList([]);
        }
    }, [data?.modules]);

    // Collapse all modules and all submodules
    const collapseAll = useCallback(() => {
        setOpenModulesList([]);
        setOpenSubmodulesList([]);
    }, []);

    const toggle = async (problem, done, { quiet } = {}) => {
        setBusy(true);
        setData((d) => patchProblem(d, problem.id, done));
        try {
            await api(`/sheets/problems/${problem.id}`, { method: 'PUT', body: { done } });
            if (done && !quiet) {
                toast(`${problem.title} solved. Streak updated!`, 'success', {
                    action: { label: 'Undo', onClick: () => toggle(problem, false, { quiet: true }) },
                });
            }
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setBusy(false);
            reload({ silent: true });
        }
    };

    if (loading && !data) {
        return (
            <div className="space-y-5 animate-pulse">
                <Card className="card-pad space-y-3">
                    <Skeleton className="h-6 w-1/3" />
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-2 w-full mt-2" />
                </Card>
                <Card className="p-4 space-y-3">
                    <Skeleton className="h-9 w-full rounded-md" />
                    <Skeleton className="h-20 w-full rounded-md" />
                </Card>
            </div>
        );
    }
    if (error && !data) {
        return (
            <Card className="card-pad flex items-center justify-between gap-3">
                <span className="text-sm text-danger min-w-0">{error}</span>
                <Button size="sm" icon={RotateCw} onClick={() => reload()}>Retry</Button>
            </Card>
        );
    }
    if (!data) return null;

    const todo = data.total - data.done;
    const statusOptions = [
        { value: 'all', label: `All ${data.total}` },
        { value: 'todo', label: `To solve ${todo}` },
        { value: 'done', label: `Solved ${data.done}` },
    ];

    const byDiff = data.by_difficulty || {};
    const med = byDiff.Medium || { done: 0, total: 0 };
    const hard = byDiff.Hard || { done: 0, total: 0 };

    const diffOptions = [
        { value: 'all', label: `Any ${data.total}` },
        { value: 'medium', label: `Medium ${med.total}` },
        { value: 'hard', label: `Hard ${hard.total}` },
    ];

    const totalModules = data.modules?.length || 0;
    const isAllExpanded = totalModules > 0 && openModulesList.length === totalModules;
    const isAllCollapsed = openModulesList.length === 0;

    return (
        <div className="space-y-5 sm:space-y-6">
            {/* Header: DSA Sheet — All 1,019 Medium & Hard Problems in Fraz's Exact Order */}
            <header className="space-y-1">
                <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-fg flex items-center gap-2.5">
                    <span>Fraz&apos;s All DSA Patterns</span>
                    <span className="rounded-full bg-accent/10 border border-accent/20 px-2.5 py-0.5 text-xs font-mono font-bold text-accent">
                        {data.total} Problems
                    </span>
                </h1>
                <p className="text-xs sm:text-sm text-subtle">
                    All {data.total} Medium &amp; Hard pattern problems across {totalModules} modules in Fraz&apos;s exact order. Select any topic to practice.
                </p>
            </header>

            {/* Non-Stop Study Sprint Runway: Oct 15 – 25 with Live Ticking Clock and Today Pointer */}
            <SprintRunway
                doneToday={data.done_today || 0}
                totalDone={data.done || 0}
                totalProbs={data.total || 1019}
            />

            {/* Clean Progress Overview Card (Only progress & sprint goal, no leaderboard or clutter) */}
            <Card className="relative overflow-hidden card-pad space-y-4 shadow-sm border border-line">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    {/* Overall Solved & Progress Bar */}
                    <div className="flex-1 min-w-[240px] space-y-2">
                        <div className="flex items-center justify-between gap-3">
                            <span className="text-xs uppercase tracking-wider font-bold text-fg flex items-center gap-1.5">
                                <Layers className="h-3.5 w-3.5 text-accent" /> Overall Progress
                            </span>
                            <span className="text-xs font-mono font-semibold text-muted">
                                <span className="text-fg font-bold">{data.done}</span> / {data.total} solved
                                <span className="text-accent font-bold ml-1.5">({data.progress}%)</span>
                            </span>
                        </div>
                        <ProgressBar value={data.progress} className="h-2.5" color={data.progress >= 100 ? 'var(--ok)' : 'var(--accent)'} />
                    </div>

                    {/* Sprint Goal & Streak Info */}
                    <div className="flex flex-wrap items-center gap-3 shrink-0">
                        {data.target_days && (
                            <div className="flex items-center gap-2 bg-accent/5 border border-accent/20 rounded-lg px-3 py-1.5">
                                <Sparkles className="h-3.5 w-3.5 text-accent shrink-0" />
                                <div className="text-xs">
                                    <span className="font-semibold text-fg">{data.target_days}-Day Sprint</span>
                                    <span className="text-subtle font-mono ml-1.5">({data.daily_min}/day)</span>
                                </div>
                                <div className="ml-1">
                                    <TodayPill count={data.done_today || 0} min={data.daily_min} />
                                </div>
                            </div>
                        )}

                        <div
                            className={cx(
                                'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold',
                                data.streak ? 'border-accent/30 bg-accent/10 text-accent' : 'border-line bg-surface-2 text-subtle'
                            )}
                            title="Days in a row with at least one problem solved"
                        >
                            <Flame className="h-3.5 w-3.5" />
                            <span>{data.streak || 0}d streak</span>
                        </div>
                    </div>
                </div>

                {/* Difficulty Breakdown Bars (Medium & Hard only) */}
                <div className="grid grid-cols-2 gap-4 pt-3 border-t border-line/60">
                    <div className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-semibold">
                            <span className="text-amber-500">Medium</span>
                            <span className="font-mono text-subtle">{med.done} / {med.total}</span>
                        </div>
                        <ProgressBar value={med.total ? (100 * med.done) / med.total : 0} color="#f59e0b" className="h-1.5" />
                    </div>

                    <div className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-semibold">
                            <span className="text-rose-500">Hard</span>
                            <span className="font-mono text-subtle">{hard.done} / {hard.total}</span>
                        </div>
                        <ProgressBar value={hard.total ? (100 * hard.done) / hard.total : 0} color="#ef4444" className="h-1.5" />
                    </div>
                </div>

                {/* Up Next Inline Launcher */}
                {data.next && (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-line/60 bg-surface-2/30 -mx-4 -mb-4 px-4 py-2.5">
                        <div className="flex items-center gap-2.5 min-w-0">
                            <span className="badge bg-accent text-accent-fg text-[10px] font-bold shrink-0">
                                UP NEXT
                            </span>
                            <a
                                href={data.next.practice_url || data.next.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs font-semibold text-fg hover:text-accent truncate transition-colors"
                                title="Solve next problem directly on LeetCode"
                            >
                                <span className="font-mono text-subtle font-normal mr-1">#{data.next.position}.</span>
                                {data.next.title}
                            </a>
                            <DifficultyPill difficulty={data.next.difficulty} />
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                            <a
                                href={data.next.practice_url || data.next.url}
                                target="_blank"
                                rel="noreferrer"
                                className="btn btn-secondary btn-sm text-xs font-semibold"
                            >
                                <Code2 className="h-3.5 w-3.5 text-accent" />
                                <span>Solve on LeetCode</span>
                            </a>
                            <Button
                                size="sm"
                                variant="primary"
                                icon={Check}
                                loading={busy}
                                onClick={() => toggle(data.next, true)}
                            >
                                Mark solved
                            </Button>
                        </div>
                    </div>
                )}
            </Card>

            {/* Daily 25 Focus Set Card: Algorithmic selection across all 24 topics with 1-Med / 1-Hard focus */}
            <DailyFocusCard
                problems={problems}
                modules={data.modules || []}
                onProblemToggle={toggle}
                revisions={revisions}
                onToggleBookmark={toggleBookmark}
                activeDailyIds={dailyIds}
                onUpdateDailyIds={setDailyIds}
            />

            {/* Controls Card: Search + Filters + Expand/Collapse + Revision List */}
            <Card className="p-3 sm:p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    {/* Search Input */}
                    <div className="relative flex-1 min-w-[220px]">
                        <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
                        <input
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            placeholder="Search 1,019 problems by title, topic, pattern..."
                            className="input h-9 pl-9 w-full text-xs"
                        />
                    </div>

                    {/* Quick Action Buttons */}
                    <div className="flex items-center gap-2 shrink-0 flex-wrap">
                        {hasModules && (
                            <>
                                <button
                                    type="button"
                                    onClick={expandAll}
                                    disabled={isAllExpanded}
                                    className="btn btn-secondary btn-sm text-xs font-medium disabled:opacity-40"
                                    title="Expand all modules"
                                >
                                    <ChevronsUpDown className="h-3.5 w-3.5" /> Expand all
                                </button>
                                <button
                                    type="button"
                                    onClick={collapseAll}
                                    disabled={isAllCollapsed}
                                    className="btn btn-secondary btn-sm text-xs font-medium disabled:opacity-40"
                                    title="Collapse all modules"
                                >
                                    <ChevronsDownUp className="h-3.5 w-3.5" /> Collapse
                                </button>
                            </>
                        )}

                        {/* Revision List Toggle */}
                        <button
                            type="button"
                            onClick={() => setRevisionOnly((v) => !v)}
                            className={cx(
                                'btn btn-sm text-xs inline-flex items-center gap-1.5 transition-colors',
                                revisionOnly ? 'btn-primary' : 'btn-secondary'
                            )}
                            title="Show only problems marked for revision"
                        >
                            <Bookmark className={cx('h-3.5 w-3.5', revisionOnly && 'fill-white')} />
                            <span>Revision List</span>
                            {revisions.length > 0 && (
                                <span className="badge bg-white/20 text-white font-mono text-[10px] ml-0.5">
                                    {revisions.length}
                                </span>
                            )}
                        </button>
                    </div>
                </div>

                {/* Segmented Filter Pills */}
                <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-line/60">
                    <Segmented options={statusOptions} value={filter} onChange={setFilter} />
                    <Segmented options={diffOptions} value={diff} onChange={setDiff} />
                </div>
            </Card>

            {/* Modules & Submodules Dropdown Accordions List in Exact Fraz Order (All 1,019 problems displayed 100%) */}
            <Card className="overflow-hidden">
                {hasModules && moduleGroups ? (
                    <div>
                        {moduleGroups
                            .filter((m) => (q.trim() || revisionOnly ? m.problems.length > 0 : true))
                            .map((m) => (
                                <ModuleAccordion
                                    key={m.id}
                                    module={m}
                                    isOpen={openModules.has(m.id)}
                                    onToggle={() => toggleModule(m.id)}
                                    onProblemToggle={toggle}
                                    nextId={data.next?.id}
                                    openSubmodules={openSubmodules}
                                    onToggleSubmodule={toggleSubmodule}
                                    revisions={revisions}
                                    onToggleBookmark={toggleBookmark}
                                />
                            ))}

                        {shown.length === 0 && (
                            <Empty icon={ListChecks} title={revisionOnly ? "No problems in revision list" : "No matching problems"}>
                                {revisionOnly
                                    ? "Click the bookmark icon on any problem to add it to your revision list."
                                    : "Try a different search term or difficulty filter."}
                            </Empty>
                        )}
                    </div>
                ) : (
                    <div>
                        {shown.length ? (
                            <ul className="divide-y divide-line">
                                {shown.map((p) => (
                                    <ProblemRow
                                        key={p.id}
                                        problem={p}
                                        isNext={p.id === data.next?.id}
                                        isBookmarked={revisions.includes(p.id)}
                                        onToggle={toggle}
                                        onToggleBookmark={toggleBookmark}
                                    />
                                ))}
                            </ul>
                        ) : (
                            <Empty icon={ListChecks} title={filter === 'done' ? 'Nothing solved yet' : 'All caught up'}>
                                {filter === 'done' ? 'Problems you mark solved will show up here.' : `You've solved all ${data.total} problems.`}
                            </Empty>
                        )}
                    </div>
                )}
            </Card>
        </div>
    );
}
