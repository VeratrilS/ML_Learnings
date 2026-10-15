import { useMemo } from 'react';
import { Apple, ExternalLink, FileSpreadsheet, Layers, ListChecks, MonitorPlay, Play } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, useLocalStorage } from '../lib/hooks';
import { Card, Checkbox, Empty, Segmented, Skeleton, cx, useToast } from '../components/ui';
import LearnCard from '../components/LearnCard';
import AppleSheetTracker from '../components/AppleSheetTracker';
import SheetTracker from '../components/SheetTracker';

// Same optimistic update as LearnCard (kept local so each file only exports components).
function patchLesson(data, id, done) {
    let delta = 0;
    const courses = data.courses.map((c) => {
        if (!c.lessons.some((l) => l.id === id)) return c;
        const lessons = c.lessons.map((l) => {
            if (l.id !== id || l.done === done) return l;
            if (done) delta += 1;
            else if (l.done_day === data.day) delta -= 1;
            return { ...l, done, done_day: done ? data.day : null, done_at: done ? new Date().toISOString() : null };
        });
        const n = lessons.filter((l) => l.done).length;
        return {
            ...c, lessons, done: n,
            progress: c.total ? Math.round((100 * n) / c.total) : 0,
            today: { lesson: lessons.find((l) => !l.done) || null, done_today: lessons.filter((l) => l.done && l.done_day === data.day) },
        };
    });
    return { ...data, courses, done_today: Math.max(0, (data.done_today || 0) + delta) };
}

const fmtDay = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '');

function LessonRow({ lesson, isNext, onToggle }) {
    return (
        <li
            className={cx(
                'flex items-center gap-3 px-3 sm:px-4 py-2.5 row-hover',
                isNext && 'bg-accent-soft hover:bg-accent-soft',
            )}
        >
            <Checkbox checked={lesson.done} onChange={(v) => onToggle(lesson, v)} label={lesson.done ? `Unmark #${lesson.position}` : `Mark #${lesson.position} done`} />
            <span className={cx('w-6 text-right font-mono text-xs tabular-nums shrink-0', isNext ? 'text-accent font-semibold' : 'text-subtle')}>
                {lesson.position}
            </span>
            <a
                href={lesson.url}
                target="_blank"
                rel="noreferrer"
                tabIndex={-1}
                aria-hidden
                className="hidden sm:block relative w-24 aspect-video overflow-hidden rounded-lg bg-surface-2 border border-line shrink-0"
            >
                <img src={lesson.thumbnail} alt="" loading="lazy" decoding="async" className={cx('h-full w-full object-cover', lesson.done && 'opacity-50')} />
            </a>
            <div className="min-w-0 flex-1">
                <a
                    href={lesson.url}
                    target="_blank"
                    rel="noreferrer"
                    className={cx(
                        'block text-sm leading-snug line-clamp-2 wrap-break-word hover:text-accent transition-colors',
                        lesson.done ? 'text-muted' : 'text-fg font-medium',
                    )}
                >
                    {lesson.title}
                </a>
                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-subtle">
                    {isNext && <span className="badge bg-accent text-accent-fg">Up next</span>}
                    {lesson.duration && <span className="font-mono">{lesson.duration}</span>}
                    {lesson.done && lesson.done_day && <span className="text-ok truncate">· watched {fmtDay(lesson.done_day)}</span>}
                </div>
            </div>
            <a
                href={lesson.url}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost btn-icon shrink-0"
                aria-label={`Watch #${lesson.position} on YouTube`}
                title="Watch on YouTube"
            >
                <Play className="h-4 w-4" />
            </a>
        </li>
    );
}

const TABS = [
    { value: 'learnyard', label: <span className="inline-flex items-center gap-1.5"><Layers className="h-3.5 w-3.5 text-accent" /> Fraz&apos;s DSA Sheet (1,019 · 11d)</span> },
    { value: 'apple', label: <span className="inline-flex items-center gap-1.5"><Apple className="h-3.5 w-3.5" /> Apple sheet (130)</span> },
    { value: 'videos', label: <span className="inline-flex items-center gap-1.5"><MonitorPlay className="h-3.5 w-3.5" /> System Design</span> },
];

export default function Learn() {
    const [tab, setTab] = useLocalStorage('learn:tab', 'learnyard');
    const isSheet = tab === 'learnyard' || tab === 'apple';
    const videos = tab === 'videos';
    const state = useApi(videos ? '/learning' : null);
    const { data, loading, setData, reload } = state;
    const [filter, setFilter] = useLocalStorage('learn:filter', 'all');
    const toast = useToast();

    const course = data?.courses?.find((c) => c.is_active) || data?.courses?.[0];
    const lessons = useMemo(() => course?.lessons || [], [course]);
    const nextId = course?.today?.lesson?.id;
    const shown = useMemo(
        () => lessons.filter((l) => (filter === 'todo' ? !l.done : filter === 'done' ? l.done : true)),
        [lessons, filter],
    );

    const toggle = async (lesson, done) => {
        setData((d) => patchLesson(d, lesson.id, done));
        try {
            await api(`/learning/lessons/${lesson.id}`, { method: 'PUT', body: { done } });
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            reload({ silent: true });
        }
    };

    const todo = course ? course.total - course.done : 0;
    const options = [
        { value: 'all', label: `All${course ? ` ${course.total}` : ''}` },
        { value: 'todo', label: `To watch${course ? ` ${todo}` : ''}` },
        { value: 'done', label: `Done${course ? ` ${course.done}` : ''}` },
    ];

    return (
        <div className="space-y-5 sm:space-y-6">
            {/* Top Navigation between DSA Practice Sheets and System Design */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-line pb-3">
                <div className="max-w-full overflow-x-auto no-scrollbar">
                    <Segmented options={TABS} value={tab} onChange={setTab} />
                </div>

                {videos && course?.playlist_url && (
                    <a href={course.playlist_url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm text-xs shrink-0 self-start sm:self-auto">
                        <ExternalLink className="h-3.5 w-3.5" /> Open playlist
                    </a>
                )}
            </div>

            {tab === 'apple' ? (
                <AppleSheetTracker sheet="apple" />
            ) : tab === 'learnyard' ? (
                <SheetTracker sheet="learnyard" />
            ) : (
                <LearnCard state={state} hero />
            )}

            {isSheet ? null : loading && !data ? (
                <Card className="divide-y divide-line">
                    {[0, 1, 2, 3, 4].map((i) => (
                        <div key={i} className="flex items-center gap-3 px-4 py-3">
                            <Skeleton className="h-5 w-5 rounded-md" />
                            <Skeleton className="h-4 w-6" />
                            <Skeleton className="hidden sm:block h-[54px] w-24" />
                            <div className="flex-1 space-y-1.5"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-16" /></div>
                        </div>
                    ))}
                </Card>
            ) : videos && course && (
                <section className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <h2 className="text-[15px] font-semibold tracking-tight flex items-center gap-2">
                            <ListChecks className="h-4 w-4 text-subtle" /> All videos
                        </h2>
                        <div className="max-w-full overflow-x-auto no-scrollbar">
                            <Segmented options={options} value={filter} onChange={setFilter} />
                        </div>
                    </div>

                    <Card className="overflow-hidden">
                        {shown.length ? (
                            <ul className="divide-y divide-line">
                                {shown.map((l) => (
                                    <LessonRow key={l.id} lesson={l} isNext={l.id === nextId} onToggle={toggle} />
                                ))}
                            </ul>
                        ) : (
                            <Empty icon={ListChecks} title={filter === 'done' ? 'Nothing watched yet' : 'All caught up'}>
                                {filter === 'done' ? 'Videos you mark done show up here.' : `You've watched all ${course.total} videos.`}
                            </Empty>
                        )}
                    </Card>
                </section>
            )}
        </div>
    );
}
