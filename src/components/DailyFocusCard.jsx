import { useState, useMemo, useCallback, useEffect } from 'react';
import {
    Target, RefreshCw, CheckCircle2, ChevronDown, ChevronRight, Code2, ExternalLink,
    Sparkles, BookOpen, Layers, Check, Bookmark, Zap, Brain, RotateCcw,
    Compass, Lightbulb, Clock, Shuffle, CheckCheck
} from 'lucide-react';
import { Card, ProgressBar, cx } from './ui';

/**
 * High-Impact Pattern Revision Knowledge Base
 * Maps DSA subtopics to their core mental models, identifying clues, and tricks.
 */
export const PATTERN_CHEATSHEETS = {
    'Merge Sort': {
        pattern: 'Divide & Conquer (Split Inversions)',
        coreTrick: 'Divide array in halves; count cross-inversions or rank elements while merging two sorted halves in O(N log N).',
        clue: 'Inversion counting (nums[i] > 2*nums[j]), smaller numbers after self, reverse pairs.',
        complexity: 'Time: O(N log N) · Space: O(N)',
    },
    'Quick Sort': {
        pattern: 'Quickselect & In-Place Partitioning',
        coreTrick: 'Pick pivot, partition in O(N). Recurse only into the target branch to find Kth element in O(N) average.',
        clue: 'Kth largest/smallest element, custom Dutch-National-Flag 3-way partition.',
        complexity: 'Time: O(N) avg, O(N²) worst · Space: O(1)',
    },
    'Two Pointer on Arrays': {
        pattern: 'Shrinking Search Space / Opposing Pointers',
        coreTrick: 'Sort array; move left/right pointers inward based on sum comparison vs target.',
        clue: 'Sorted array pair/triplet sums (3Sum, 4Sum, Container With Most Water, 2Sum II).',
        complexity: 'Time: O(N log N) or O(N) · Space: O(1)',
    },
    'Two Pointer on Strings': {
        pattern: 'Symmetry & Fast-Slow In-Place Scan',
        coreTrick: 'Scan from edges inward for palindrome checks, or slow/fast pointers for in-place token compaction.',
        clue: 'Palindrome substrings, sentence similarity, reverse words, string compression.',
        complexity: 'Time: O(N) · Space: O(1)',
    },
    'Prefix Sum': {
        pattern: 'Running Accumulator & Remainder Hashing',
        coreTrick: 'Subarray sum(i..j) = pref[j] - pref[i-1]. Store {pref_sum: count/index} in hashmap to find sum = K in O(1).',
        clue: 'Continuous subarrays summing to K, divisible by K, or range sum queries.',
        complexity: 'Time: O(N) · Space: O(N)',
    },
    'Line Sweep': {
        pattern: 'Interval Event Points & Difference Array',
        coreTrick: 'Mark +1 at interval start, -1 at interval end+1. Sort events chronologically and accumulate.',
        clue: 'Overlapping intervals, car pooling capacity, meeting rooms, rectangle area overlap.',
        complexity: 'Time: O(N log N) · Space: O(N)',
    },
    'Matrix Transformation and Modification': {
        pattern: 'In-Place State Markers & Cyclic Rotation',
        coreTrick: 'Use 0th row & 0th column as in-place markers. 4-way coordinate rotation: (r, c) -> (c, N-1-r).',
        clue: 'Set matrix zeroes in O(1) space, rotate matrix 90 degrees clockwise.',
        complexity: 'Time: O(M × N) · Space: O(1)',
    },
    'Fixed Size Sliding-Window': {
        pattern: 'Rolling Window of Length K',
        coreTrick: 'Maintain window of exact size K: add incoming element at right, subtract outgoing element at left in O(1).',
        clue: 'Maximum sum subarray of length K, sliding window median, anagram occurrences.',
        complexity: 'Time: O(N) · Space: O(1) to O(K)',
    },
    'Dynamic Size Sliding-Window': {
        pattern: 'Expand-Contract Window (Two Pointers)',
        coreTrick: 'Expand right pointer while condition holds; contract left pointer until validity is restored.',
        clue: 'Shortest subarray with sum >= S, longest substring with at most K distinct characters.',
        complexity: 'Time: O(N) · Space: O(distinct elements)',
    },
    'Parentheses Problem': {
        pattern: 'LIFO Matching & Greedy Counters',
        coreTrick: 'Push opening bracket index; pop on matching close. When only one bracket type, an integer counter suffices.',
        clue: 'Longest valid parentheses, minimum remove to make valid, score of parentheses.',
        complexity: 'Time: O(N) · Space: O(N) or O(1)',
    },
    'Advance Stack Problems': {
        pattern: 'Monotonic Stack (Next Greater / Smaller)',
        coreTrick: 'Keep stack strictly monotonic. Pop when incoming element breaks monotonicity; the popped element finds its boundary!',
        clue: 'Next Greater Element, Daily Temperatures, Largest Rectangle in Histogram, Trapping Rain Water.',
        complexity: 'Time: O(N) · Space: O(N)',
    },
    'Introductory Problems': {
        pattern: 'Monotonic Binary Search on Answer',
        coreTrick: 'Determine search range [low, high]. Write a monotonic check(mid) boolean function. Halve search space.',
        clue: 'Minimize the maximum, Koko eating bananas, capacity to ship packages, split array largest sum.',
        complexity: 'Time: O(N log(Range)) · Space: O(1)',
    },
    'Basic Bit Concepts': {
        pattern: 'Bitwise Masking & Parity Cancellation',
        coreTrick: 'x ^ x = 0, x ^ 0 = x (cancels duplicates). x & (x - 1) clears lowest set bit. 1 << k sets bit k.',
        clue: 'Single Number, counting set bits, power of two, bitmask subsets.',
        complexity: 'Time: O(1) · Space: O(1)',
    },
    'Properties of trees': {
        pattern: 'Post-Order Subtree Synthesis',
        coreTrick: 'Compute left and right subtree metrics recursively; combine at root (height = 1 + max(L, R)).',
        clue: 'Diameter of tree, balanced binary tree, maximum path sum, subtree sizes.',
        complexity: 'Time: O(N) · Space: O(H)',
    },
    'Introductory Questions': {
        pattern: 'Dual-Heap & Top-K Streaming',
        coreTrick: 'Min-Heap of size K maintains top K largest elements. Two heaps (max-heap left, min-heap right) for dynamic median.',
        clue: 'Find median from data stream, Kth largest element in a stream, merge K sorted lists.',
        complexity: 'Time: O(N log K) · Space: O(K)',
    },
    'Linear DP': {
        pattern: '1D Optimal Substructure & Space Rolling',
        coreTrick: 'dp[i] represents optimal solution up to index i. If dp[i] depends only on last k steps, roll state in O(1) space.',
        clue: 'House Robber, Coin Change, Longest Increasing Subsequence (LIS), Jump Game.',
        complexity: 'Time: O(N) · Space: O(1) to O(N)',
    },
    '2 Dimensional DP': {
        pattern: 'Grid Paths & Dual Sequence Alignment',
        coreTrick: 'dp[i][j] = solution for prefixes of length i and j. Match character: dp[i-1][j-1] + 1; mismatch: branch.',
        clue: 'Longest Common Subsequence (LCS), Edit Distance, Unique Paths, Distinct Subsequences.',
        complexity: 'Time: O(M × N) · Space: O(N) with space optimization',
    },
    'DFS and BFS on Graphs': {
        pattern: 'Connected Components & Level-Order Queue',
        coreTrick: 'BFS with queue gives shortest unweighted distance. DFS with visited array explores connected components & cycles.',
        clue: 'Number of islands, rotting oranges, word ladder, shortest path in binary matrix.',
        complexity: 'Time: O(V + E) · Space: O(V)',
    },
    'Cycle Detection': {
        pattern: 'Topological Sort (Kahn’s) & 3-Color DFS',
        coreTrick: 'Compute in-degrees; push in-degree 0 into queue. If processed count < total nodes, a cycle exists!',
        clue: 'Course Schedule I & II, Alien Dictionary, Detect cycle in directed graph.',
        complexity: 'Time: O(V + E) · Space: O(V)',
    },
    'Fenwick Tree': {
        pattern: 'Binary Indexed Tree (BIT)',
        coreTrick: 'Update: i += (i & -i). Query prefix: i -= (i & -i). Prefix sums and point updates in O(log N).',
        clue: 'Point update range sum query, inversion count on large coordinate ranges.',
        complexity: 'Time: O(log N) · Space: O(N)',
    },
};

/**
 * Pure Fast Algorithmic Selector (NO LLM, 0ms latency)
 * Selects ~25 problems covering ALL 24 topics with balanced 1-Medium / 1-Hard focus.
 * REVOLVES TO THE NEXT SUBTOPICS on each batch!
 * Solved problems (p.done === true) are strictly excluded and never suggested again.
 */
export function selectDailyFocusProblems(problems = [], modules = [], targetCount = 25, cursors = {}) {
    const unsolved = problems.filter((p) => !p.done);
    if (unsolved.length === 0) return { problems: [], nextCursors: cursors };

    const selected = [];
    const selectedIds = new Set();
    const newCursors = { ...cursors };

    // Build subtopics list per module in exact appearance order
    const subtopicsByMod = new Map();
    modules.forEach((m) => subtopicsByMod.set(m.id, []));

    problems.forEach((p) => {
        const modId = p.module_id || p.mod_id;
        const sub = p.submodule_name || p.sub_name || '';
        if (sub && subtopicsByMod.has(modId)) {
            const subs = subtopicsByMod.get(modId);
            if (!subs.includes(sub)) {
                subs.push(sub);
            }
        }
    });

    // Group unsolved problems by (modId, subName)
    const probsByModSub = new Map();
    unsolved.forEach((p) => {
        const modId = p.module_id || p.mod_id;
        const sub = p.submodule_name || p.sub_name || '';
        const key = `${modId}:::${sub}`;
        if (!probsByModSub.has(key)) {
            probsByModSub.set(key, []);
        }
        probsByModSub.get(key).push(p);
    });

    // Pass 1: Select 1 problem for each of the 24 modules, revolving through subtopics
    modules.forEach((m, idx) => {
        const modId = m.id;
        const subs = subtopicsByMod.get(modId) || [];
        if (!subs.length) {
            // Fallback for module without subtopics: pick from all unsolved in this module
            const modProblems = unsolved.filter((p) => (p.module_id || p.mod_id) === modId && !selectedIds.has(p.id));
            if (modProblems.length > 0) {
                const preferredDiff = idx % 2 === 0 ? 'Medium' : 'Hard';
                let cand = modProblems.find((p) => p.difficulty === preferredDiff);
                if (!cand) cand = modProblems[0];
                selected.push(cand);
                selectedIds.add(cand.id);
            }
            return;
        }

        const startSubIdx = (cursors[modId] || 0) % subs.length;
        const preferredDiff = idx % 2 === 0 ? 'Medium' : 'Hard';

        let foundProblem = null;
        let pickedSubIdx = startSubIdx;

        // Iterate through subtopics starting from the cursor
        for (let offset = 0; offset < subs.length; offset++) {
            const currSubIdx = (startSubIdx + offset) % subs.length;
            const subName = subs[currSubIdx];
            const key = `${modId}:::${subName}`;
            const subProbs = (probsByModSub.get(key) || []).filter((p) => !selectedIds.has(p.id));
            if (!subProbs.length) continue;

            let cand = subProbs.find((p) => p.difficulty === preferredDiff);
            if (!cand) cand = subProbs[0];

            if (cand) {
                foundProblem = cand;
                pickedSubIdx = currSubIdx;
                break;
            }
        }

        if (foundProblem) {
            selected.push(foundProblem);
            selectedIds.add(foundProblem.id);
            // Revolve cursor to next subtopic for the next generation
            newCursors[modId] = (pickedSubIdx + 1) % subs.length;
        }
    });

    // Pass 2: Pick complementary problem (1 Med + 1 Hard) from heavy priority modules
    // until reaching targetCount (e.g. 25)
    const priorityModules = [18, 19, 10, 15, 8, 1, 4, 13, 6, 5];
    for (const modId of priorityModules) {
        if (selected.length >= targetCount) break;
        const subs = subtopicsByMod.get(modId) || [];
        if (!subs.length) continue;

        const startSubIdx = (newCursors[modId] || 0) % subs.length;
        const alreadyInBatch = selected.filter((p) => (p.module_id || p.mod_id) === modId);
        const compDiff = alreadyInBatch.some((p) => p.difficulty === 'Medium') ? 'Hard' : 'Medium';

        for (let offset = 0; offset < subs.length; offset++) {
            const currSubIdx = (startSubIdx + offset) % subs.length;
            const subName = subs[currSubIdx];
            const key = `${modId}:::${subName}`;
            const subProbs = (probsByModSub.get(key) || []).filter((p) => !selectedIds.has(p.id));
            if (!subProbs.length) continue;

            let cand = subProbs.find((p) => p.difficulty === compDiff);
            if (!cand) cand = subProbs[0];

            if (cand) {
                selected.push(cand);
                selectedIds.add(cand.id);
                newCursors[modId] = (currSubIdx + 1) % subs.length;
                break;
            }
        }
    }

    // Sort by module ID and position for clean structured presentation
    const sorted = selected.sort((a, b) => {
        const modA = a.module_id || a.mod_id || 0;
        const modB = b.module_id || b.mod_id || 0;
        if (modA !== modB) return modA - modB;
        return (a.position || 0) - (b.position || 0);
    });

    return { problems: sorted, nextCursors: newCursors };
}

export default function DailyFocusCard({
    problems = [],
    modules = [],
    onProblemToggle,
    revisions = [],
    onToggleBookmark,
    activeDailyIds = [],
    onUpdateDailyIds,
}) {
    const [isOpen, setIsOpen] = useState(true);
    const [viewMode, setViewMode] = useState('daily'); // 'daily' | 'revision'
    const [diffFilter, setDiffFilter] = useState('all'); // all, medium, hard
    const [revisionSearch, setRevisionSearch] = useState('');
    const [shuffledRevLimit, setShuffledRevLimit] = useState(0);

    // Retrieve active daily problem list
    const dailyProblems = useMemo(() => {
        if (!problems.length) return [];
        const idSet = new Set(activeDailyIds);
        return problems.filter((p) => idSet.has(p.id));
    }, [problems, activeDailyIds]);

    // Initial population if activeDailyIds is empty
    useEffect(() => {
        if (problems.length > 0 && modules.length > 0 && (!activeDailyIds || activeDailyIds.length === 0)) {
            const savedCursors = (() => {
                try {
                    const item = localStorage.getItem('sheet:learnyard:subtopic_cursors');
                    return item ? JSON.parse(item) : {};
                } catch {
                    return {};
                }
            })();

            const { problems: fresh, nextCursors } = selectDailyFocusProblems(problems, modules, 25, savedCursors);
            if (fresh.length > 0) {
                onUpdateDailyIds(fresh.map((p) => p.id));
                try {
                    localStorage.setItem('sheet:learnyard:subtopic_cursors', JSON.stringify(nextCursors));
                } catch {
                    // ignore
                }
            }
        }
    }, [problems, modules, activeDailyIds, onUpdateDailyIds]);

    // Regenerate a brand new daily set (revolving to NEXT subtopics and excluding all solved)
    const handleRegenerate = useCallback(() => {
        const savedCursors = (() => {
            try {
                const item = localStorage.getItem('sheet:learnyard:subtopic_cursors');
                return item ? JSON.parse(item) : {};
            } catch {
                return {};
            }
        })();

        const { problems: fresh, nextCursors } = selectDailyFocusProblems(problems, modules, 25, savedCursors);
        if (fresh.length > 0) {
            onUpdateDailyIds(fresh.map((p) => p.id));
            try {
                localStorage.setItem('sheet:learnyard:subtopic_cursors', JSON.stringify(nextCursors));
            } catch {
                // ignore
            }
        }
    }, [problems, modules, onUpdateDailyIds]);

    // --- ENCOUNTERED PATTERNS REVISION ENGINE ---
    // All problems the user has encountered (solved or bookmarked, plus current active daily set)
    const encounteredPatterns = useMemo(() => {
        if (!problems.length) return [];
        const revSet = new Set(revisions);
        const dailySet = new Set(activeDailyIds);

        // Group encountered problems by subtopic
        const groups = new Map();

        problems.forEach((p) => {
            const isSolved = Boolean(p.done);
            const isBookmarked = revSet.has(p.id);
            const isDaily = dailySet.has(p.id);

            // An encountered problem is solved, bookmarked, or in active daily batch
            if (isSolved || isBookmarked || isDaily) {
                const sub = p.submodule_name || p.sub_name || 'General';
                const mod = p.module_name || (modules.find((m) => m.id === (p.module_id || p.mod_id))?.name) || 'Topic';
                const key = `${mod}:::${sub}`;

                if (!groups.has(key)) {
                    groups.set(key, {
                        key,
                        module: mod,
                        subtopic: sub,
                        cheatsheet: PATTERN_CHEATSHEETS[sub] || null,
                        problems: [],
                        solvedCount: 0,
                    });
                }

                const g = groups.get(key);
                g.problems.push(p);
                if (isSolved) g.solvedCount += 1;
            }
        });

        return Array.from(groups.values());
    }, [problems, revisions, activeDailyIds, modules]);

    // Filtered encountered patterns for revision
    const filteredPatterns = useMemo(() => {
        let list = encounteredPatterns;
        if (revisionSearch.trim()) {
            const q = revisionSearch.toLowerCase().trim();
            list = list.filter((g) =>
                g.subtopic.toLowerCase().includes(q) ||
                g.module.toLowerCase().includes(q) ||
                g.cheatsheet?.coreTrick?.toLowerCase().includes(q) ||
                g.problems.some((p) => p.title.toLowerCase().includes(q))
            );
        }
        if (shuffledRevLimit > 0) {
            return list.slice(0, shuffledRevLimit);
        }
        return list;
    }, [encounteredPatterns, revisionSearch, shuffledRevLimit]);

    // Daily Stats
    const totalCount = dailyProblems.length;
    const solvedCount = dailyProblems.filter((p) => p.done).length;
    const medCount = dailyProblems.filter((p) => p.difficulty === 'Medium').length;
    const hardCount = dailyProblems.filter((p) => p.difficulty === 'Hard').length;
    const topicsCovered = new Set(dailyProblems.map((p) => p.module_id || p.mod_id)).size;
    const progressPct = totalCount ? Math.round((solvedCount / totalCount) * 100) : 0;
    const isCompleted = totalCount > 0 && solvedCount === totalCount;

    const filteredProblems = useMemo(() => {
        if (diffFilter === 'all') return dailyProblems;
        return dailyProblems.filter((p) => p.difficulty?.toLowerCase() === diffFilter.toLowerCase());
    }, [dailyProblems, diffFilter]);

    if (!problems.length || !modules.length) return null;

    return (
        <Card className="relative overflow-hidden card-pad space-y-3.5 border-2 border-accent/40 bg-surface-1 shadow-md animate-rise">
            {/* Header: Title + Mode Tabs + Progress + Action Buttons */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-line/70">
                <div className="flex items-center gap-3">
                    <button
                        type="button"
                        onClick={() => setIsOpen((v) => !v)}
                        className="p-1 text-subtle hover:text-accent transition-colors rounded hover:bg-surface-2"
                        title={isOpen ? 'Collapse Daily Set' : 'Expand Daily Set'}
                    >
                        {isOpen ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4" />}
                    </button>

                    <div>
                        <div className="flex items-center gap-2 flex-wrap">
                            <h2 className="text-sm sm:text-base font-extrabold tracking-tight text-fg flex items-center gap-1.5">
                                <Target className="h-4 w-4 text-accent" />
                                <span>Daily 25 &amp; Pattern Revision Engine</span>
                            </h2>

                            {/* View Mode Switcher Pills */}
                            <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5 ml-1">
                                <button
                                    type="button"
                                    onClick={() => setViewMode('daily')}
                                    className={cx(
                                        'px-2 py-0.5 text-xs font-semibold rounded-md transition-colors flex items-center gap-1',
                                        viewMode === 'daily' ? 'bg-accent text-accent-fg shadow-xs' : 'text-subtle hover:text-fg'
                                    )}
                                >
                                    <Target className="h-3 w-3" />
                                    <span>Daily 25 Batch</span>
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setViewMode('revision')}
                                    className={cx(
                                        'px-2 py-0.5 text-xs font-semibold rounded-md transition-colors flex items-center gap-1',
                                        viewMode === 'revision' ? 'bg-accent text-accent-fg shadow-xs' : 'text-subtle hover:text-fg'
                                    )}
                                >
                                    <Brain className="h-3 w-3" />
                                    <span>Revise Encountered Patterns</span>
                                    {encounteredPatterns.length > 0 && (
                                        <span className="badge bg-surface-1 text-accent font-mono text-[10px] px-1 py-0 ml-0.5">
                                            {encounteredPatterns.length}
                                        </span>
                                    )}
                                </button>
                            </div>

                            {viewMode === 'daily' && isCompleted && (
                                <span className="badge bg-ok/20 text-ok border border-ok/30 text-[11px] font-bold flex items-center gap-1">
                                    <CheckCircle2 className="h-3 w-3" /> Set Completed!
                                </span>
                            )}
                        </div>

                        <p className="text-[11px] sm:text-xs text-subtle mt-0.5">
                            {viewMode === 'daily'
                                ? 'Fast algorithmic selection covering all 24 topics (1-Med / 1-Hard balance). Automatically revolves to next subtopics on each batch.'
                                : 'High-impact pattern recall: revise all encountered techniques, core tricks, and clues across problems you have practiced.'}
                        </p>
                    </div>
                </div>

                {/* Progress & Actions */}
                <div className="flex items-center gap-3 shrink-0 flex-wrap sm:flex-nowrap">
                    {/* Solved Progress Bar */}
                    <div className="min-w-[130px] space-y-1">
                        <div className="flex items-center justify-between text-xs font-semibold">
                            <span className="text-subtle font-mono text-[11px]">
                                <span className="text-fg font-bold">{solvedCount}</span> / {totalCount} solved
                            </span>
                            <span className="text-accent font-bold font-mono text-[11px]">{progressPct}%</span>
                        </div>
                        <ProgressBar value={progressPct} className="h-1.5" color={progressPct >= 100 ? 'var(--ok)' : 'var(--accent)'} />
                    </div>

                    {/* Regenerate Set Button (Revolves to next subtopics) */}
                    <button
                        type="button"
                        onClick={handleRegenerate}
                        className="btn btn-secondary btn-sm text-xs font-semibold flex items-center gap-1.5 hover:border-accent/40 transition-colors"
                        title="Revolve to the next subtopics across all 24 topics (solved problems are strictly excluded)"
                    >
                        <RefreshCw className="h-3.5 w-3.5 text-accent" />
                        <span>Revolve Next Set</span>
                    </button>
                </div>
            </div>

            {/* Content: When Open */}
            {isOpen && (
                <div className="space-y-3">
                    {/* MODE 1: DAILY 25 BATCH */}
                    {viewMode === 'daily' && (
                        <>
                            {/* Sub-bar: Difficulty mix & Quick filters */}
                            <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
                                <div className="flex items-center gap-2">
                                    <span className="badge bg-accent/15 text-accent font-semibold text-[11px] flex items-center gap-1">
                                        <Layers className="h-3 w-3" /> {topicsCovered} Topics Covered
                                    </span>
                                    <span className="badge bg-amber-500/10 text-amber-600 dark:text-amber-400 font-mono text-[11px]">
                                        {medCount} Medium
                                    </span>
                                    <span className="badge bg-rose-500/10 text-rose-600 dark:text-rose-400 font-mono text-[11px]">
                                        {hardCount} Hard
                                    </span>
                                    <span className="badge bg-surface-2 text-subtle text-[11px] font-mono">
                                        Circular Subtopic Rotation Active
                                    </span>
                                </div>

                                {/* Quick filter pills */}
                                <div className="flex items-center gap-1">
                                    {['all', 'medium', 'hard'].map((d) => (
                                        <button
                                            key={d}
                                            type="button"
                                            onClick={() => setDiffFilter(d)}
                                            className={cx(
                                                'px-2 py-0.5 rounded text-[11px] font-semibold transition-colors',
                                                diffFilter === d
                                                    ? 'bg-accent text-accent-fg'
                                                    : 'bg-surface-2 text-subtle hover:text-fg'
                                            )}
                                        >
                                            {d.charAt(0).toUpperCase() + d.slice(1)}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Problems List */}
                            <div className="rounded-xl border border-line/70 overflow-hidden bg-surface-2/20">
                                {/* Table Header */}
                                <div className="hidden md:flex items-center justify-between px-4 py-2 bg-surface-2/60 border-b border-line/60 text-[10px] font-bold tracking-wider uppercase text-subtle">
                                    <div className="flex-1 max-w-[50%] pl-8">Problem &amp; Rotating Subtopic</div>
                                    <div className="flex items-center gap-4 shrink-0">
                                        <div className="w-20 text-center">Difficulty</div>
                                        <div className="w-32 text-center">Practice (LeetCode)</div>
                                        <div className="w-20 text-center">Editorial</div>
                                        <div className="w-8 text-center">Link</div>
                                    </div>
                                </div>

                                {/* Problems Rows */}
                                <ul className="divide-y divide-line/40">
                                    {filteredProblems.map((p) => {
                                        const isLeetCode = !p.platform || p.platform.toLowerCase() === 'leetcode' || (p.practice_url && p.practice_url.includes('leetcode.com'));
                                        const platformLabel = isLeetCode ? 'LeetCode' : p.platform || 'LeetCode';
                                        const modLabel = p.module_name || (modules.find((m) => m.id === (p.module_id || p.mod_id))?.name) || 'Topic';
                                        const subLabel = p.submodule_name || p.sub_name || '';

                                        return (
                                            <li
                                                key={p.id}
                                                className={cx(
                                                    'px-3 sm:px-4 py-2.5 transition-colors flex items-center justify-between gap-3 text-xs',
                                                    p.done ? 'bg-surface-2/40' : 'hover:bg-surface-2/30'
                                                )}
                                            >
                                                {/* Left: Checkbox + Title + Topic Badges */}
                                                <div className="flex items-center gap-3 min-w-0 flex-1">
                                                    <button
                                                        type="button"
                                                        onClick={() => onProblemToggle(p, !p.done)}
                                                        className={cx(
                                                            'h-4 w-4 shrink-0 rounded border transition-colors flex items-center justify-center',
                                                            p.done
                                                                ? 'bg-ok border-ok text-white'
                                                                : 'border-line-strong hover:border-accent bg-surface-1'
                                                        )}
                                                        title={p.done ? 'Mark as unsolved' : 'Mark as solved'}
                                                    >
                                                        {p.done && <Check className="h-3 w-3 stroke-[3]" />}
                                                    </button>

                                                    <div className="min-w-0 flex-1">
                                                        <div className="flex items-center gap-2">
                                                            <a
                                                                href={p.practice_url || p.url}
                                                                target="_blank"
                                                                rel="noreferrer"
                                                                className={cx(
                                                                    'font-semibold hover:text-accent transition-colors truncate',
                                                                    p.done ? 'line-through text-subtle font-normal' : 'text-fg'
                                                                )}
                                                                title={p.title}
                                                            >
                                                                <span className="font-mono text-subtle font-normal mr-1">#{p.position}.</span>
                                                                {p.title}
                                                            </a>
                                                            {onToggleBookmark && (
                                                                <button
                                                                    type="button"
                                                                    onClick={() => onToggleBookmark(p.id)}
                                                                    className={cx(
                                                                        'p-0.5 rounded transition-colors shrink-0',
                                                                        revisions.includes(p.id) ? 'text-accent' : 'text-subtle/50 hover:text-subtle'
                                                                    )}
                                                                    title="Toggle revision bookmark"
                                                                >
                                                                    <Bookmark className={cx('h-3 w-3', revisions.includes(p.id) && 'fill-accent')} />
                                                                </button>
                                                            )}
                                                        </div>

                                                        <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-subtle truncate">
                                                            <span className="font-semibold text-fg/80">{modLabel}</span>
                                                            {subLabel && (
                                                                <>
                                                                    <span>·</span>
                                                                    <span className="truncate text-accent font-medium">{subLabel}</span>
                                                                </>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Right: Difficulty + Practice Button + Editorial + External Link */}
                                                <div className="flex items-center gap-2 sm:gap-4 shrink-0">
                                                    <div className="w-16 sm:w-20 text-center">
                                                        <span
                                                            className={cx(
                                                                'inline-block px-1.5 py-0.5 rounded text-[10px] font-bold font-mono uppercase',
                                                                p.difficulty?.toLowerCase() === 'hard'
                                                                    ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                                                                    : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                                                            )}
                                                        >
                                                            {p.difficulty}
                                                        </span>
                                                    </div>

                                                    <div className="hidden sm:flex w-28 sm:w-32 justify-center">
                                                        <a
                                                            href={p.practice_url || p.url}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            className="inline-flex items-center gap-1 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-semibold text-[11px] px-2 py-0.5 transition-colors"
                                                            title={`Solve on ${platformLabel}`}
                                                        >
                                                            <Code2 className="h-3 w-3" />
                                                            <span>{platformLabel}</span>
                                                        </a>
                                                    </div>

                                                    <div className="hidden md:flex w-20 justify-center">
                                                        {p.article_url ? (
                                                            <a
                                                                href={p.article_url}
                                                                target="_blank"
                                                                rel="noreferrer"
                                                                className="inline-flex items-center gap-1 rounded bg-surface-2 hover:bg-surface-3 text-fg text-[11px] px-1.5 py-0.5 transition-colors"
                                                                title="Read Editorial"
                                                            >
                                                                <BookOpen className="h-2.5 w-2.5 text-subtle" />
                                                                <span>Read</span>
                                                            </a>
                                                        ) : (
                                                            <span className="text-[11px] text-subtle font-mono">-</span>
                                                        )}
                                                    </div>

                                                    <div className="w-6 flex justify-center">
                                                        <a
                                                            href={p.practice_url || p.url}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            className="text-subtle hover:text-accent transition-colors p-1"
                                                            title="Open directly"
                                                        >
                                                            <ExternalLink className="h-3.5 w-3.5" />
                                                        </a>
                                                    </div>
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </div>
                        </>
                    )}

                    {/* MODE 2: IMPACTFUL ENCOUNTERED PATTERNS REVISION */}
                    {viewMode === 'revision' && (
                        <div className="space-y-3 pt-1">
                            {/* Revision Controls Bar */}
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 bg-surface-2/40 p-2.5 rounded-xl border border-line/60">
                                <div className="flex items-center gap-2 flex-1">
                                    <input
                                        type="text"
                                        value={revisionSearch}
                                        onChange={(e) => setRevisionSearch(e.target.value)}
                                        placeholder="Search encountered patterns (e.g. Inversions, Sliding Window, DP)..."
                                        className="input h-8 text-xs flex-1 max-w-sm"
                                    />
                                    <span className="text-xs text-subtle font-mono">
                                        {filteredPatterns.length} pattern{filteredPatterns.length === 1 ? '' : 's'}
                                    </span>
                                </div>

                                <div className="flex items-center gap-2 shrink-0">
                                    <button
                                        type="button"
                                        onClick={() => setShuffledRevLimit((curr) => (curr === 5 ? 0 : 5))}
                                        className={cx(
                                            'btn btn-sm text-xs font-semibold flex items-center gap-1.5',
                                            shuffledRevLimit === 5 ? 'btn-primary' : 'btn-secondary'
                                        )}
                                        title="Focus on 5 random patterns for a quick mental recall sprint"
                                    >
                                        <Shuffle className="h-3.5 w-3.5" />
                                        <span>{shuffledRevLimit === 5 ? 'Show All Patterns' : 'Shuffle 5 Patterns'}</span>
                                    </button>
                                </div>
                            </div>

                            {/* Patterns Deck Cards */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {filteredPatterns.map((g) => {
                                    const cs = g.cheatsheet;
                                    return (
                                        <div
                                            key={g.key}
                                            className="p-3 sm:p-3.5 rounded-xl border border-line/70 bg-surface-2/30 space-y-2.5 hover:border-accent/40 transition-colors shadow-xs"
                                        >
                                            {/* Pattern Title & Tag */}
                                            <div className="flex items-start justify-between gap-2">
                                                <div>
                                                    <div className="flex items-center gap-1.5">
                                                        <Lightbulb className="h-3.5 w-3.5 text-accent shrink-0" />
                                                        <h3 className="font-bold text-xs sm:text-sm text-fg leading-tight">
                                                            {cs?.pattern || g.subtopic}
                                                        </h3>
                                                    </div>
                                                    <p className="text-[10px] text-subtle mt-0.5">
                                                        <span className="font-semibold text-fg/80">{g.module}</span> · {g.subtopic}
                                                    </p>
                                                </div>

                                                <span className="badge bg-accent/10 text-accent font-mono text-[10px] shrink-0 font-bold">
                                                    {g.solvedCount}/{g.problems.length} Solved
                                                </span>
                                            </div>

                                            {/* Core Trick & Identifying Clue */}
                                            {cs && (
                                                <div className="bg-surface-1 border border-line/50 rounded-lg p-2.5 space-y-1.5 text-xs">
                                                    <div>
                                                        <span className="text-[10px] uppercase font-bold text-accent tracking-wider block">
                                                            Core Mental Model / Heuristic:
                                                        </span>
                                                        <p className="text-fg/90 font-medium leading-relaxed mt-0.5">
                                                            {cs.coreTrick}
                                                        </p>
                                                    </div>
                                                    <div className="pt-1 border-t border-line/40 flex items-center justify-between text-[10px] text-subtle">
                                                        <span><strong>Clue:</strong> {cs.clue}</span>
                                                        <span className="font-mono shrink-0 ml-2 text-fg/80">{cs.complexity}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Encountered Problems for this pattern */}
                                            <div className="space-y-1">
                                                <span className="text-[10px] uppercase font-bold text-subtle tracking-wider block">
                                                    Encountered Problems:
                                                </span>
                                                <ul className="space-y-1 max-h-36 overflow-y-auto pr-1">
                                                    {g.problems.map((p) => (
                                                        <li
                                                            key={p.id}
                                                            className="flex items-center justify-between gap-2 text-[11px] p-1.5 rounded bg-surface-1 border border-line/40"
                                                        >
                                                            <div className="flex items-center gap-2 min-w-0">
                                                                <button
                                                                    type="button"
                                                                    onClick={() => onProblemToggle(p, !p.done)}
                                                                    className={cx(
                                                                        'h-3.5 w-3.5 shrink-0 rounded border flex items-center justify-center transition-colors',
                                                                        p.done ? 'bg-ok border-ok text-white' : 'border-line hover:border-accent'
                                                                    )}
                                                                    title={p.done ? 'Mark unsolved' : 'Mark solved'}
                                                                >
                                                                    {p.done && <Check className="h-2.5 w-2.5 stroke-[3]" />}
                                                                </button>
                                                                <a
                                                                    href={p.practice_url || p.url}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    className={cx(
                                                                        'font-semibold hover:text-accent truncate transition-colors',
                                                                        p.done ? 'line-through text-subtle' : 'text-fg'
                                                                    )}
                                                                >
                                                                    #{p.position}. {p.title}
                                                                </a>
                                                            </div>

                                                            <div className="flex items-center gap-1.5 shrink-0">
                                                                <span
                                                                    className={cx(
                                                                        'px-1 py-0.2 rounded text-[9px] font-bold font-mono uppercase',
                                                                        p.difficulty?.toLowerCase() === 'hard'
                                                                            ? 'bg-rose-500/10 text-rose-500'
                                                                            : 'bg-amber-500/10 text-amber-500'
                                                                    )}
                                                                >
                                                                    {p.difficulty}
                                                                </span>
                                                                <a
                                                                    href={p.practice_url || p.url}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    className="btn btn-ghost btn-icon p-0.5 text-subtle hover:text-accent"
                                                                    title="Open LeetCode problem directly"
                                                                >
                                                                    <ExternalLink className="h-3 w-3" />
                                                                </a>
                                                            </div>
                                                        </li>
                                                    ))}
                                                </ul>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
}
