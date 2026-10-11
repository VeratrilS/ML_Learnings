import { useEffect, useState } from 'react';
import { Play, Check, Undo2, Tv, PartyPopper, Clock } from 'lucide-react';
import { api } from '../lib/api';
import { useApi, navigate } from '../lib/hooks';
import { Button, Card, Empty, ProgressBar, Skeleton, Spinner, useToast } from './ui';

const IST_OFFSET = 5.5 * 3600 * 1000;
const msToIstMidnight = () => 86400000 - ((Date.now() + IST_OFFSET) % 86400000);

function useCountdown() {
    const [ms, setMs] = useState(msToIstMidnight);
    useEffect(() => {
        const t = setInterval(() => setMs(msToIstMidnight()), 30000);
        return () => clearInterval(t);
    }, []);
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    return `${h}h ${m}m`;
}

export default function EpisodeCard({ onChange }) {
    const { data, loading, setData } = useApi('/watch');
    const [busy, setBusy] = useState(false);
    const [opened, setOpened] = useState(false);
    const toast = useToast();
    const countdown = useCountdown();
    const s = data?.find((x) => x.is_active) || data?.[0];

    const update = (next) => setData((all) => all.map((x) => (x.id === next.id ? next : x)));

    const mark = async (undo = false) => {
        setBusy(true);
        try {
            const res = await api(`/watch/${s.id}/watched`, { method: undo ? 'DELETE' : 'POST' });
            update(res.data);
            setOpened(false);
            toast(undo ? 'Undone' : `Episode ${s.next_episode} done. Keep that fighting spirit!`);
            onChange?.();
        } catch (e) {
            toast(e.message, 'error');
        } finally {
            setBusy(false);
        }
    };

    if (loading && !data) {
        return <Card className="card-pad"><Skeleton className="h-4 w-32 mb-4" /><Skeleton className="h-12 w-40 mb-4" /><Skeleton className="h-10 w-full" /></Card>;
    }
    if (!s) {
        return (
            <Card>
                <Empty icon={Tv} title="No series yet" action={<Button size="sm" onClick={() => navigate('settings')}>Add a series</Button>}>
                    Add a show to watch one episode a day.
                </Empty>
            </Card>
        );
    }

    const doneToday = s.watched_today.length > 0;
    const watchedEp = s.watched_today[s.watched_today.length - 1];

    return (
        <Card className="relative overflow-hidden">
            <div aria-hidden className="pointer-events-none absolute -top-24 -right-20 h-64 w-64 rounded-full bg-accent opacity-[0.13] blur-3xl" />
            <div className="relative card-pad">
                <div className="flex items-center justify-between gap-3">
                    <div className="eyebrow flex items-center gap-1.5"><Tv className="h-3.5 w-3.5" /> Daily episode</div>
                    <span className="text-xs text-subtle">{s.progress}% complete</span>
                </div>
                <h3 className="mt-1.5 text-[17px] font-semibold tracking-tight">{s.title}</h3>

                <div className="mt-4 flex items-end gap-2">
                    {s.finished ? (
                        <div className="text-3xl font-bold tracking-tight">Season complete</div>
                    ) : (
                        <>
                            <div className="text-5xl font-extrabold tracking-tighter leading-none font-mono">
                                {doneToday ? watchedEp : s.next_episode}
                            </div>
                            <div className="pb-1 text-sm text-subtle font-medium">/ {s.total_episodes} episodes</div>
                        </>
                    )}
                </div>
                <ProgressBar value={s.progress} className="mt-4" />

                <div className="mt-5">
                    {s.finished ? (
                        <div className="flex flex-wrap items-center gap-3">
                            <PartyPopper className="h-5 w-5 text-accent" />
                            <span className="text-sm text-muted">You finished it. Add the next season to keep going.</span>
                            <Button size="sm" onClick={() => navigate('settings')}>Add next season</Button>
                        </div>
                    ) : doneToday ? (
                        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                            <div className="flex items-center gap-2.5 flex-1 rounded-xl bg-ok/10 border border-ok/25 px-3 py-2.5">
                                <Check className="h-4 w-4 text-ok shrink-0" strokeWidth={3} />
                                <span className="text-sm">
                                    Done for today. <span className="text-muted">Ep {s.next_episode} unlocks in </span>
                                    <span className="font-semibold inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{countdown}</span>
                                </span>
                            </div>
                            <div className="flex items-center gap-1">
                                <a href={s.next_url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">Watch next anyway</a>
                                <button className="btn btn-ghost btn-sm btn-icon" onClick={() => mark(true)} disabled={busy} title="Undo" aria-label="Undo">
                                    {busy ? <Spinner /> : <Undo2 className="h-4 w-4" />}
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="flex flex-col sm:flex-row gap-2">
                            <a
                                href={s.next_url}
                                target="_blank"
                                rel="noreferrer"
                                onClick={() => setOpened(true)}
                                className="btn btn-primary btn-lg"
                            >
                                <Play className="h-4 w-4 fill-current" /> Watch episode {s.next_episode}
                            </a>
                            <Button
                                size="lg"
                                variant={opened ? 'primary' : 'secondary'}
                                icon={Check}
                                loading={busy}
                                onClick={() => mark(false)}
                                className={opened ? 'animate-rise' : ''}
                            >
                                Mark watched
                            </Button>
                        </div>
                    )}
                </div>
            </div>
        </Card>
    );
}
