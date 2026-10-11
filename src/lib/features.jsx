import { createContext, lazy, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
    ChartLine, Dumbbell, Sparkles, HeartPulse, Sunrise, Moon, Medal, Briefcase, Timer, MessagesSquare, Layers,
    Bug, Zap, Wand2, GraduationCap, CalendarRange,
} from 'lucide-react';
import { api } from './api';

// Feature files may or may not exist yet (built in waves). Globbing means a missing
// file just hides that feature instead of breaking the build.
// Only finished features are listed; partial files from interrupted work are never bundled.
const PAGE_FILES = import.meta.glob([
    '../pages/Insights.jsx', '../pages/Gym.jsx', '../pages/Cards.jsx',
    '../pages/Placements.jsx', '../pages/OA.jsx', '../pages/Interview.jsx', '../pages/Mistakes.jsx',
    '../pages/Weekly.jsx',
]);
const COMPONENT_FILES = import.meta.glob([
    '../components/InsightsCard.jsx', '../components/BriefCard.jsx', '../components/RingsCard.jsx',
    '../components/BossCard.jsx', '../components/HabitsCard.jsx', '../components/CardsCard.jsx',
    '../components/PlacementsCard.jsx', '../components/QuickCapture.jsx',
]);

const lazyFrom = (files, name) => {
    const loader = files[name];
    return loader ? lazy(loader) : null;
};
const page = (name) => lazyFrom(PAGE_FILES, `../pages/${name}.jsx`);
const comp = (name) => lazyFrom(COMPONENT_FILES, `../components/${name}.jsx`);

/**
 * Every new feature starts as Beta and only joins the main nav / Today once approved in the Beta Lab.
 * page: route component; cards: Today widgets; global: always-mounted helpers (overlays).
 */
export const FEATURES = [
    { id: 'insights', label: 'Insights', icon: ChartLine, desc: 'Exam readiness, study-hour split, Monte Carlo finish odds, LeetCode topic Elo, Codeforces rating.', page: page('Insights'), cards: [comp('InsightsCard')] },
    { id: 'now', label: 'Now card', icon: Sunrise, desc: 'Time-aware hero on Today: morning briefing, deep work, wind-down.', cards: [] },
    { id: 'shutdown', label: 'Shutdown ritual', icon: Moon, desc: 'Evening close-the-day: mood, win, blocker, tomorrow’s top 3.', cards: [] },
    { id: 'ranks', label: 'Ippo ranks & XP', icon: Medal, desc: 'Rookie → World Champion based on everything you do.', cards: [] },
    { id: 'brief', label: 'AI daily brief', icon: Sparkles, desc: 'Gemini plans your day as a timeline from your real data.', cards: [comp('BriefCard')] },
    { id: 'gym', label: 'Gym', icon: Dumbbell, desc: 'Three rings, weekly Ippo boss fights, daily quests, personal records.', page: page('Gym'), cards: [comp('RingsCard'), comp('BossCard')] },
    { id: 'habits', label: 'Body habits', icon: HeartPulse, desc: 'Sleep, water, exercise and a daily body score.', cards: [comp('HabitsCard')] },
    { id: 'cards', label: 'Fundamentals', icon: Layers, desc: 'OS / DBMS / CN / OOP / SQL flashcards with spaced repetition.', page: page('Cards'), cards: [comp('CardsCard')] },
    { id: 'placements', label: 'Placements', icon: Briefcase, desc: 'Kanban pipeline from wishlist to offer with deadlines.', page: page('Placements'), cards: [comp('PlacementsCard')] },
    { id: 'oa', label: 'OA Simulator', icon: Timer, desc: 'Timed online-assessment sets, auto-verified via LeetCode/CF.', page: page('OA'), cards: [] },
    { id: 'interview', label: 'Interview Lab', icon: MessagesSquare, desc: 'AI mock interviewer (DSA / behavioral / system design) with rubric.', page: page('Interview'), cards: [] },
    { id: 'mistakes', label: 'Mistake journal', icon: Bug, desc: 'Log what went wrong; AI tags it; get a personal pre-submit checklist.', page: page('Mistakes'), cards: [] },
    { id: 'capture', label: 'Quick capture', icon: Zap, desc: 'Press C anywhere (or share from Android) to capture tasks and links.', global: comp('QuickCapture') },
    { id: 'tutor', label: 'AI tutor & code review', icon: Wand2, desc: 'Socratic tutor and solution reviewer inside each problem.', cards: [] },
    { id: 'weekly', label: 'Weekly report', icon: CalendarRange, desc: 'Sunday 7:30 PM email recapping your week: solves, Apple sheet, videos, focus, vs last week. Emails start once approved.', page: page('Weekly'), cards: [] },
    { id: 'pdfextract', label: 'PDF → topics & cards', icon: GraduationCap, desc: 'Extract syllabus topics and flashcards from lecture PDFs.', cards: [] },
].map((f) => ({ ...f, cards: (f.cards || []).filter(Boolean), available: !!(f.page || f.global || f.cards?.some(Boolean) || ['now', 'shutdown', 'ranks', 'tutor', 'pdfextract'].includes(f.id)) }));

const FeaturesCtx = createContext({ status: () => 'beta', setStatus: () => {}, isOn: () => false, loaded: false });
export const useFeatures = () => useContext(FeaturesCtx);

export function FeaturesProvider({ children }) {
    const [flags, setFlags] = useState({});
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        api('/features').then((r) => setFlags(r.data || {})).catch(() => {}).finally(() => setLoaded(true));
    }, []);

    const setStatus = useCallback(async (id, status) => {
        setFlags((f) => ({ ...f, [id]: status }));
        try { await api(`/features/${id}`, { method: 'PUT', body: { status } }); } catch { /* optimistic; next load re-syncs */ }
    }, []);

    const value = useMemo(() => ({
        loaded,
        status: (id) => flags[id] || 'beta',
        isOn: (id) => flags[id] === 'approved',
        setStatus,
    }), [flags, loaded, setStatus]);

    return <FeaturesCtx.Provider value={value}>{children}</FeaturesCtx.Provider>;
}
