import { Component, lazy, Suspense, useEffect } from 'react';
import { Sun, Moon, Code2, Swords, FileText, Settings as SettingsIcon, House, Flame, GraduationCap, Search, RotateCcw } from 'lucide-react';
import { useTheme } from './themes/ThemeContext';
import { useApi, useHashRoute, navigate } from './lib/hooks';
import { cx, Spinner } from './components/ui';
import CommandPalette from './components/CommandPalette';
import Today from './pages/Today';
import Problems from './pages/Problems';

const Codeforces = lazy(() => import('./pages/Codeforces'));
const Study = lazy(() => import('./pages/Study'));
const PdfStudio = lazy(() => import('./pages/PdfStudio'));
const Settings = lazy(() => import('./pages/Settings'));

const NAV = [
    { id: 'today', label: 'Today', icon: House },
    { id: 'problems', label: 'DSA', long: 'DSA Problems', icon: Code2 },
    { id: 'study', label: 'Study', long: 'End-sem Prep', icon: GraduationCap },
    { id: 'cf', label: 'Codeforces', short: 'CF', icon: Swords },
    { id: 'pdf', label: 'PDF Studio', short: 'PDF', icon: FileText },
    { id: 'settings', label: 'Settings', icon: SettingsIcon, desktopOnly: true },
];

const openPalette = () => window.dispatchEvent(new CustomEvent('open-command-palette'));
const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

// Keeps one broken widget (e.g. an odd AI response) from blanking the whole app
class ErrorBoundary extends Component {
    state = { error: null };
    static getDerivedStateFromError(error) { return { error }; }
    componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); }
    render() {
        if (!this.state.error) return this.props.children;
        return (
            <div className="card card-pad text-center py-12">
                <p className="font-semibold">Something went wrong on this page.</p>
                <p className="text-sm text-subtle mt-1">{String(this.state.error.message || this.state.error)}</p>
                <button className="btn btn-secondary mt-4" onClick={() => this.setState({ error: null })}><RotateCcw className="h-4 w-4" /> Try again</button>
            </div>
        );
    }
}

function Logo() {
    return (
        <div className="flex items-center gap-2.5">
            <div className="grid place-items-center h-8 w-8 rounded-[10px] bg-accent text-accent-fg shadow-[0_6px_20px_-6px_var(--accent)]">
                <Flame className="h-[18px] w-[18px]" strokeWidth={2.5} />
            </div>
            <div className="leading-none">
                <div className="text-[15px] font-bold tracking-tight">Daily</div>
                <div className="text-[10.5px] text-subtle mt-0.5 font-medium">keep the streak alive</div>
            </div>
        </div>
    );
}

function ThemeButton() {
    const { isDark, toggleTheme } = useTheme();
    return (
        <button onClick={toggleTheme} className="btn btn-ghost btn-icon" aria-label="Toggle theme" title="Toggle theme">
            {isDark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
        </button>
    );
}

function StreakPill({ streak }) {
    if (streak == null) return null;
    return (
        <div className={cx('inline-flex items-center gap-1.5 rounded-full px-2.5 h-7 text-xs font-semibold border',
            streak > 0 ? 'bg-accent-soft border-accent/30 text-accent' : 'bg-surface-2 border-line text-subtle')}
            title="Days in a row with at least one solved problem">
            <Flame className="h-3.5 w-3.5" /> {streak} day{streak === 1 ? '' : 's'}
        </div>
    );
}

export default function App() {
    const [page, ...rest] = useHashRoute();
    const current = NAV.some((n) => n.id === page) ? page : 'today';
    const stats = useApi('/stats', { deps: [current] });
    const streak = stats.data?.streak;

    // Keyboard shortcuts 1-6 switch sections (ignored while typing)
    useEffect(() => {
        const onKey = (e) => {
            if (e.metaKey || e.ctrlKey || e.altKey || /input|textarea|select/i.test(e.target.tagName) || e.target.isContentEditable) return;
            const idx = Number(e.key) - 1;
            if (idx >= 0 && idx < NAV.length) navigate(NAV[idx].id);
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    useEffect(() => { window.scrollTo({ top: 0 }); }, [current]);

    return (
        <div className="min-h-dvh">
            <CommandPalette />

            {/* Desktop sidebar */}
            <aside className="hidden lg:flex fixed inset-y-0 left-0 w-60 flex-col border-r border-line bg-surface/60 backdrop-blur-xl px-3 py-5 z-40">
                <div className="px-2 mb-5"><Logo /></div>
                <button onClick={openPalette} className="mx-1 mb-5 flex items-center gap-2 h-9 px-3 rounded-xl border border-line bg-surface-2/70 text-sm text-subtle hover:text-fg hover:border-line-strong transition-colors">
                    <Search className="h-4 w-4" />
                    <span className="flex-1 text-left truncate">Search…</span>
                    <kbd className="text-[10.5px] font-mono border border-line rounded px-1.5 py-0.5 bg-surface">{isMac ? '⌘' : 'Ctrl'} K</kbd>
                </button>
                <nav className="flex flex-col gap-0.5">
                    {NAV.map((n, i) => (
                        <a
                            key={n.id}
                            href={`#/${n.id}`}
                            className={cx(
                                'group flex items-center gap-3 rounded-xl px-3 h-10 text-sm font-medium transition-colors',
                                current === n.id ? 'bg-surface-2 text-fg border border-line' : 'text-muted hover:text-fg hover:bg-surface-2/60 border border-transparent',
                            )}
                        >
                            <n.icon className={cx('h-[18px] w-[18px]', current === n.id && 'text-accent')} />
                            <span className="flex-1">{n.long || n.label}</span>
                            <kbd className="hidden group-hover:inline text-[10px] font-mono text-subtle border border-line rounded px-1">{i + 1}</kbd>
                        </a>
                    ))}
                </nav>
                <div className="mt-auto flex items-center justify-between px-1">
                    <StreakPill streak={streak} />
                    <ThemeButton />
                </div>
            </aside>

            {/* Mobile top bar */}
            <header className="lg:hidden sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur-xl pt-[env(safe-area-inset-top)]">
                <div className="flex items-center justify-between h-14 px-4">
                    <Logo />
                    <div className="flex items-center gap-0.5">
                        <StreakPill streak={streak} />
                        <button onClick={openPalette} className="btn btn-ghost btn-icon" aria-label="Search"><Search className="h-[18px] w-[18px]" /></button>
                        <a href="#/settings" className={cx('btn btn-ghost btn-icon', current === 'settings' && 'text-accent')} aria-label="Settings"><SettingsIcon className="h-[18px] w-[18px]" /></a>
                        <ThemeButton />
                    </div>
                </div>
            </header>

            <main className="lg:pl-60">
                <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-10 pt-5 sm:pt-8 pb-28 lg:pb-16">
                    <ErrorBoundary resetKey={current}>
                        <Suspense fallback={<div className="grid place-items-center py-24 text-subtle"><Spinner className="h-5 w-5" /></div>}>
                            {current === 'today' && <Today stats={stats} />}
                            {current === 'problems' && <Problems openId={rest[0]} onChange={() => stats.reload({ silent: true })} />}
                            {current === 'study' && <Study />}
                            {current === 'cf' && <Codeforces />}
                            {current === 'pdf' && <PdfStudio />}
                            {current === 'settings' && <Settings />}
                        </Suspense>
                    </ErrorBoundary>
                </div>
            </main>

            {/* Mobile bottom tabs */}
            <nav className="lg:hidden fixed bottom-0 inset-x-0 z-50 border-t border-line bg-bg/85 backdrop-blur-xl safe-bottom">
                <div className="grid grid-cols-5 h-16">
                    {NAV.filter((n) => !n.desktopOnly).map((n) => (
                        <a
                            key={n.id}
                            href={`#/${n.id}`}
                            className={cx('flex flex-col items-center justify-center gap-1 text-[10.5px] font-medium transition-colors',
                                current === n.id ? 'text-accent' : 'text-subtle active:text-fg')}
                        >
                            <n.icon className="h-[21px] w-[21px]" strokeWidth={current === n.id ? 2.4 : 2} />
                            {n.short || n.label}
                        </a>
                    ))}
                </div>
            </nav>
        </div>
    );
}
