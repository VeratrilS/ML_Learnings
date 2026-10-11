import { useEffect, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { Card, CardHeader, Skeleton } from './ui';

const LEVEL_OPACITY = [0, 0.35, 0.6, 0.8, 1];
const ICE = '#38bdf8'; // streak-freeze tint

function cellTitle(d) {
    const parts = [`${d.count} solved`];
    if (d.focus) parts.push(`${d.focus} min focus`);
    if (d.frozen) parts.push('❄ freeze used');
    if (d.rest) parts.push('rest day (exam)');
    return `${parts.join(' · ')} · ${new Date(d.date + 'T00:00:00').toDateString()}`;
}

function cellStyle(d, lv) {
    const style = { background: lv ? `color-mix(in srgb, var(--accent) ${LEVEL_OPACITY[lv] * 100}%, transparent)` : 'var(--surface-3)' };
    if (d.frozen && !lv) style.background = `color-mix(in srgb, ${ICE} 28%, var(--surface-3))`;
    if (d.rest) {
        style.outline = '1px dotted var(--muted)';
        style.outlineOffset = '-1px';
    }
    return style;
}
const level = (n) => (n <= 0 ? 0 : n === 1 ? 1 : n === 2 ? 2 : n <= 4 ? 3 : 4);

// Fewer weeks on small screens so cells stay readable
function useWeeks() {
    const pick = () => (window.matchMedia('(min-width: 1024px)').matches ? 53 : window.matchMedia('(min-width: 640px)').matches ? 30 : 18);
    const [weeks, setWeeks] = useState(pick);
    useEffect(() => {
        const onResize = () => setWeeks(pick());
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);
    return weeks;
}

// `freezes` = stats.freezes_available (optional): shown as a chip in the header.
export default function Heatmap({ days: allDays, freezes }) {
    const nWeeks = useWeeks();
    if (!allDays) {
        return <Card className="card-pad"><Skeleton className="h-4 w-40 mb-4" /><Skeleton className="h-28 w-full" /></Card>;
    }
    const days = allDays.slice(-nWeeks * 7);
    // Pad the front so each column is a Monday..Sunday week
    const first = new Date(days[0].date + 'T00:00:00');
    const pad = (first.getDay() + 6) % 7;
    const cells = [...Array(pad).fill(null), ...days];
    const weeks = [];
    for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
    const total = days.reduce((a, d) => a + d.count, 0);
    const active = days.filter((d) => d.count > 0).length;
    const anyRest = days.some((d) => d.rest);

    const months = weeks.map((w, i) => {
        const d = w.find(Boolean);
        if (!d) return '';
        const m = new Date(d.date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short' });
        const prev = weeks[i - 1]?.find(Boolean);
        return !prev || new Date(prev.date + 'T00:00:00').getMonth() !== new Date(d.date + 'T00:00:00').getMonth() ? m : '';
    });

    return (
        <Card className="card-pad">
            <CardHeader
                title="Consistency"
                subtitle={`${total} solved · ${active} active days in the last ${weeks.length} weeks`}
                icon={CalendarDays}
                action={freezes != null && (
                    <span
                        className="badge tabular-nums"
                        style={{ color: ICE, background: `color-mix(in srgb, ${ICE} 14%, transparent)` }}
                        title="Streak freezes: earn one per 7 days in a row (max 2). A missed day uses one automatically."
                    >
                        ❄ {freezes} freeze{freezes === 1 ? '' : 's'}
                    </span>
                )}
            />
            <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}>
                {months.map((m, i) => <div key={`m${i}`} className="text-[10px] text-subtle h-4 overflow-visible whitespace-nowrap">{m}</div>)}
                {weeks.map((w, wi) => (
                    <div key={wi} className="grid grid-rows-7 gap-[3px]">
                        {Array.from({ length: 7 }).map((_, di) => {
                            const d = w[di];
                            if (!d) return <div key={di} className="aspect-square" />;
                            const lv = level(d.count);
                            return (
                                <div
                                    key={di}
                                    title={cellTitle(d)}
                                    className="aspect-square rounded-[3px]"
                                    style={cellStyle(d, lv)}
                                />
                            );
                        })}
                    </div>
                ))}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-1.5 mt-3 text-[10.5px] text-subtle">
                <span className="inline-flex items-center gap-1 mr-auto">
                    <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: `color-mix(in srgb, ${ICE} 28%, var(--surface-3))` }} />
                    ❄ freeze used
                    {anyRest && (
                        <>
                            <span className="h-2.5 w-2.5 rounded-[3px] ml-2" style={{ background: 'var(--surface-3)', outline: '1px dotted var(--muted)', outlineOffset: '-1px' }} />
                            exam rest day
                        </>
                    )}
                </span>
                Less
                {LEVEL_OPACITY.map((o, i) => (
                    <span key={i} className="h-2.5 w-2.5 rounded-[3px]" style={{ background: i ? `color-mix(in srgb, var(--accent) ${o * 100}%, transparent)` : 'var(--surface-3)' }} />
                ))}
                More
            </div>
        </Card>
    );
}
