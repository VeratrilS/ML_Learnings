import { useState } from 'react';
import { Check, Flame, MonitorPlay, PartyPopper, Play, Library, RotateCw } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, Empty, ProgressBar, Skeleton, cx, useToast } from './ui';

// Optimistically flip one lesson and recompute what the cards show (server stays the source of truth).
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

function fmtLeft(sec) {
    if (!sec) return null;
    const h = Math.floor(sec / 3600);
    const m = Math.round((sec % 3600) / 60);
    return h ? `${h}h ${m}m left` : `${m}m left`;
}

/** Today's count against the daily minimum. A minimum, never a cap. */
function TodayPill({ count, min }) {
    const met = count >= min;
    return (
        <span
            className={cx(
                'inline-flex items-center gap-1.5 rounded-full border px-2.5 h-7 text-xs font-semibold whitespace-nowrap transition-colors',
                met ? 'bg-ok/10 border-ok/25 text-ok' : 'bg-surface-2 border-line text-muted',
            )}
        >
            {met ? (
                <><Check className="h-3.5 w-3.5" strokeWidth={3} /> Today: {count} · keep going?</>
            ) : (
                <>Today: {count} / {min} min</>
            )}
        </span>
    );
}

function Thumb({ lesson, className }) {
    return (
        <a
            href={lesson.url}
            target="_blank"
            rel="noreferrer"
            aria-label={`Watch #${lesson.position} on YouTube`}
            className={cx('group relative block aspect-video overflow-hidden rounded-xl bg-surface-2 border border-line shrink-0', className)}
        >
            <img src={lesson.thumbnail} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]" />
            <span className="absolute inset-0 grid place-items-center bg-black/10 group-hover:bg-black/25 transition-colors">
                <span className="grid place-items-center h-10 w-10 rounded-full bg-black/60 text-white backdrop-blur-sm transition-transform group-hover:scale-110">
                    <Play className="h-4 w-4 fill-current translate-x-px" />
                </span>
            </span>
            {lesson.duration && (
                <span className="absolute bottom-1.5 right-1.5 rounded-md bg-black/75 px-1.5 py-px text-[11px] font-semibold text-white font-mono">{lesson.duration}</span>
            )}
        </a>
    );
}

/**
 * Daily learning card for the Today page.
 * Props: onChange() after a lesson is marked/unmarked.
 * The Learn page reuses it as its hero: pass `state` (a useApi('/learning') result) to share data, and `hero`.
 */
export default function LearnCard({ onChange, state, hero = false }) {
    const own = useApi(state ? null : '/learning');
    const { data, loading, error, setData, reload } = state || own;
    const [busy, setBusy] = useState(false);
    const [opened, setOpened] = useState(false);
    const toast = useToast();

    const course = data?.courses?.find((c) => c.is_active) || data?.courses?.[0];

    const setDone = async (lesson, done, { quiet } = {}) => {
        setBusy(true);
        setData((d) => patchLesson(d, lesson.id, done));
        try {
            await api(`/learning/lessons/${lesson.id}`, { method: 'PUT', body: { done } });
            setOpened(false);
            if (done && !quiet) {
                toast(`#${lesson.position} done. Nice work.`, 'success', { action: { label: 'Undo', onClick: () => setDone(lesson, false, { quiet: true }) } });
            }
            onChange?.();
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setBusy(false);
            reload({ silent: true }); // refresh streak / server truth
        }
    };

    if (loading && !data) {
        return (
            <Card className="card-pad">
                <Skeleton className="h-3 w-28" />
                <div className="mt-4 flex gap-3">
                    <Skeleton className={cx('aspect-video rounded-xl shrink-0', hero ? 'w-40 sm:w-64' : 'w-32')} />
                    <div className="flex-1 space-y-2"><Skeleton className="h-3 w-16" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-2/3" /></div>
                </div>
                <Skeleton className="h-10 w-full mt-5" />
            </Card>
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
    if (!course) {
        return (
            <Card>
                <Empty icon={Library} title="Nothing to learn yet">Your playlist will show up here.</Empty>
            </Card>
        );
    }

    const next = course.today.lesson;
    const count = data.done_today || 0;
    const min = data.daily_min || 1;
    const met = count >= min;
    const streak = data.streak || 0;
    const left = fmtLeft(course.remaining_seconds);

    return (
        <Card className={cx('relative overflow-hidden', hero && 'animate-rise')}>
            <div
                aria-hidden
                className={cx('pointer-events-none absolute -top-24 -right-20 h-64 w-64 rounded-full opacity-[0.13] blur-3xl transition-colors duration-700', met ? 'bg-ok' : 'bg-accent')}
            />
            <div className="relative card-pad">
                <div className="flex items-center justify-between gap-3">
                    <div className="eyebrow flex items-center gap-1.5 min-w-0">
                        <MonitorPlay className="h-3.5 w-3.5 shrink-0" /> <span className="truncate">{hero ? 'Up next' : 'Daily lesson'}</span>
                    </div>
                    <TodayPill count={count} min={min} />
                </div>
                {!hero && (
                    <button
                        type="button"
                        onClick={() => navigate('learn')}
                        className="mt-1.5 block max-w-full text-left text-[17px] font-semibold tracking-tight truncate hover:text-accent transition-colors"
                    >
                        {course.title}
                    </button>
                )}

                {next ? (
                    <>
                        <div className={cx('flex gap-3 sm:gap-4', hero ? 'mt-3 flex-col sm:flex-row sm:items-center' : 'mt-4 items-start')}>
                            <Thumb lesson={next} className={hero ? 'w-full sm:w-72' : 'w-28 sm:w-36'} />
                            <div className="min-w-0 flex-1">
                                <div className="text-xs font-medium text-subtle">
                                    Lesson <span className="font-mono text-fg font-semibold">{next.position}</span> / {course.total}
                                    {next.duration && <> · {next.duration}</>}
                                </div>
                                <a
                                    href={next.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    onClick={() => setOpened(true)}
                                    className={cx(
                                        'mt-1 block font-semibold tracking-tight leading-snug hover:text-accent transition-colors line-clamp-3 wrap-break-word',
                                        hero ? 'text-lg sm:text-xl' : 'text-[15px]',
                                    )}
                                >
                                    {next.title}
                                </a>
                                {hero && <p className="mt-1 text-xs text-subtle truncate">{course.channel} · {course.title}</p>}
                            </div>
                        </div>

                        <div className="mt-4 flex flex-wrap gap-2">
                            <a
                                href={next.url}
                                target="_blank"
                                rel="noreferrer"
                                onClick={() => setOpened(true)}
                                className={cx('btn btn-primary flex-1 sm:flex-none', hero && 'btn-lg')}
                            >
                                <Play className="h-4 w-4 fill-current" /> {met ? 'Watch another' : 'Watch'}
                            </a>
                            <Button
                                size={hero ? 'lg' : undefined}
                                variant={opened ? 'primary' : 'secondary'}
                                icon={Check}
                                loading={busy}
                                onClick={() => setDone(next, true)}
                                className={cx('flex-1 sm:flex-none', opened && 'animate-rise')}
                            >
                                Mark done
                            </Button>
                        </div>
                    </>
                ) : (
                    <div className="mt-4 flex items-center gap-3 rounded-xl bg-ok/10 border border-ok/25 px-3 py-3">
                        <PartyPopper className="h-5 w-5 text-ok shrink-0" />
                        <span className="text-sm">All {course.total} videos watched. Course complete!</span>
                    </div>
                )}

                <div className="mt-5">
                    <div className="flex items-center justify-between gap-3 text-xs">
                        <span className="text-muted">
                            <span className="font-semibold text-fg font-mono">{course.done}</span> / {course.total} watched
                            <span className="text-subtle"> · {course.progress}%</span>
                        </span>
                        <span className="flex items-center gap-2 text-subtle min-w-0">
                            {left && <span className="hidden min-[400px]:inline truncate">{left}</span>}
                            <span
                                className={cx('inline-flex items-center gap-1 font-semibold whitespace-nowrap', streak ? 'text-accent' : 'text-subtle')}
                                title="Days in a row with at least one video"
                            >
                                <Flame className="h-3.5 w-3.5" /> {streak}d
                            </span>
                        </span>
                    </div>
                    <ProgressBar value={course.progress} className="mt-2" color={course.progress >= 100 ? 'var(--ok)' : 'var(--accent)'} />
                </div>
            </div>
        </Card>
    );
}
