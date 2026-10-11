import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Check, Loader2, X, AlertCircle, CheckCircle2, Info } from 'lucide-react';

export const cx = (...c) => c.filter(Boolean).join(' ');

export function Spinner({ className = 'h-4 w-4' }) {
    return <Loader2 className={cx('animate-spin', className)} aria-hidden />;
}

export function Button({ variant = 'secondary', size, loading, icon: Icon, children, className, ...props }) {
    return (
        <button
            className={cx('btn', `btn-${variant}`, size && `btn-${size}`, className)}
            disabled={loading || props.disabled}
            {...props}
        >
            {loading ? <Spinner /> : Icon ? <Icon className="h-4 w-4 shrink-0" aria-hidden /> : null}
            {children}
        </button>
    );
}

export function Card({ className, children, ...props }) {
    return <section className={cx('card', className)} {...props}>{children}</section>;
}

export function CardHeader({ title, subtitle, icon: Icon, action, className }) {
    return (
        <div className={cx('flex items-start justify-between gap-3 mb-4', className)}>
            <div className="flex items-center gap-2.5 min-w-0">
                {Icon && (
                    <div className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line text-muted shrink-0">
                        <Icon className="h-4 w-4" />
                    </div>
                )}
                <div className="min-w-0">
                    <h2 className="text-[15px] font-semibold tracking-tight truncate">{title}</h2>
                    {subtitle && <p className="text-xs text-subtle truncate">{subtitle}</p>}
                </div>
            </div>
            {action && <div className="flex items-center gap-1.5 shrink-0">{action}</div>}
        </div>
    );
}

const DIFF = {
    Easy: 'text-easy bg-easy/10',
    Medium: 'text-medium bg-medium/10',
    Hard: 'text-hard bg-hard/10',
};
export function DifficultyBadge({ value, className }) {
    if (!value) return null;
    return <span className={cx('badge', DIFF[value] || 'text-muted bg-surface-2', className)}>{value}</span>;
}

// Codeforces rank colours by rating
export function cfColor(rating) {
    const r = Number(rating);
    if (r < 1200) return '#8c8c8c';
    if (r < 1400) return '#22a34a';
    if (r < 1600) return '#03a89e';
    if (r < 1900) return '#3b5bdb';
    if (r < 2100) return '#aa00aa';
    if (r < 2400) return '#f08c00';
    return '#e03131';
}
export function RatingBadge({ rating }) {
    const c = cfColor(rating);
    return <span className="badge font-mono" style={{ color: c, background: `${c}1f` }}>{rating}</span>;
}

export function Checkbox({ checked, onChange, label, className }) {
    return (
        <button
            type="button"
            role="checkbox"
            aria-checked={checked}
            aria-label={label}
            onClick={(e) => { e.stopPropagation(); onChange(!checked); }}
            className={cx(
                'grid place-items-center h-5 w-5 rounded-md border transition-all shrink-0',
                checked ? 'bg-ok border-ok text-white scale-100' : 'border-line-strong hover:border-ok/70 bg-surface',
                className,
            )}
        >
            {checked && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
        </button>
    );
}

export function Toggle({ checked, onChange, label }) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            aria-label={label}
            onClick={() => onChange(!checked)}
            className={cx('relative h-6 w-11 rounded-full transition-colors shrink-0', checked ? 'bg-accent' : 'bg-surface-3 border border-line-strong')}
        >
            <span className={cx('absolute top-1/2 -translate-y-1/2 h-[18px] w-[18px] rounded-full bg-white shadow transition-all', checked ? 'left-[22px]' : 'left-[3px]')} />
        </button>
    );
}

export function Segmented({ options, value, onChange, className }) {
    return (
        <div className={cx('inline-flex p-0.5 rounded-xl bg-surface-2 border border-line', className)}>
            {options.map((o) => {
                const v = typeof o === 'string' ? o : o.value;
                const l = typeof o === 'string' ? o : o.label;
                return (
                    <button
                        key={v}
                        type="button"
                        onClick={() => onChange(v)}
                        className={cx(
                            'px-3 h-8 rounded-[10px] text-[13px] font-medium transition-all whitespace-nowrap',
                            value === v ? 'bg-surface text-fg shadow-sm border border-line' : 'text-muted hover:text-fg',
                        )}
                    >
                        {l}
                    </button>
                );
            })}
        </div>
    );
}

export function Empty({ icon: Icon, title, children, action }) {
    return (
        <div className="flex flex-col items-center text-center py-10 px-4">
            {Icon && (
                <div className="grid place-items-center h-11 w-11 rounded-2xl bg-surface-2 border border-line text-subtle mb-3">
                    <Icon className="h-5 w-5" />
                </div>
            )}
            <p className="text-sm font-medium">{title}</p>
            {children && <p className="text-[13px] text-subtle mt-1 max-w-sm">{children}</p>}
            {action && <div className="mt-4">{action}</div>}
        </div>
    );
}

export function Skeleton({ className }) {
    return <div className={cx('animate-pulse rounded-lg bg-surface-2', className)} />;
}

export function ProgressRing({ value, max, size = 56, stroke = 6, children }) {
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const pct = max ? Math.min(value / max, 1) : 0;
    return (
        <div className="relative shrink-0" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
                <circle
                    cx={size / 2} cy={size / 2} r={r} fill="none"
                    stroke={pct >= 1 ? 'var(--ok)' : 'var(--accent)'} strokeWidth={stroke} strokeLinecap="round"
                    strokeDasharray={c} strokeDashoffset={c * (1 - pct)}
                    style={{ transition: 'stroke-dashoffset .6s cubic-bezier(.2,.7,.2,1)' }}
                />
            </svg>
            <div className="absolute inset-0 grid place-items-center">{children}</div>
        </div>
    );
}

export function ProgressBar({ value, className, color = 'var(--accent)' }) {
    return (
        <div className={cx('h-1.5 rounded-full bg-surface-3 overflow-hidden', className)}>
            <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
        </div>
    );
}

// Bottom sheet on mobile, centered panel / side drawer on desktop.
export function Sheet({ open, onClose, children, wide, side }) {
    useEffect(() => {
        if (!open) return;
        const onKey = (e) => e.key === 'Escape' && onClose();
        document.addEventListener('keydown', onKey);
        const prev = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
    }, [open, onClose]);
    if (!open) return null;
    return (
        <div className="fixed inset-0 z-[60] flex items-end sm:items-stretch sm:justify-end">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-fade" onClick={onClose} />
            <div
                role="dialog"
                aria-modal="true"
                className={cx(
                    'relative w-full bg-surface border-line shadow-2xl animate-sheet overflow-y-auto',
                    'max-h-[92dvh] rounded-t-3xl border-t sm:max-h-none sm:h-full sm:rounded-none sm:border-l sm:border-t-0',
                    side === false ? '' : '',
                    wide ? 'sm:max-w-2xl' : 'sm:max-w-lg',
                )}
            >
                <div className="sm:hidden sticky top-0 z-10 flex justify-center pt-2.5 pb-1 bg-surface">
                    <div className="h-1 w-10 rounded-full bg-line-strong" />
                </div>
                <button onClick={onClose} className="btn btn-ghost btn-icon absolute right-3 top-3 z-20" aria-label="Close">
                    <X className="h-4 w-4" />
                </button>
                {children}
            </div>
        </div>
    );
}

// ---------------- Toasts ----------------
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);
    const push = useCallback((message, type = 'success') => {
        const id = Math.random().toString(36).slice(2);
        setToasts((t) => [...t.slice(-2), { id, message, type }]);
        setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === 'error' ? 6000 : 3200);
    }, []);
    const icons = { success: CheckCircle2, error: AlertCircle, info: Info };
    return (
        <ToastCtx.Provider value={push}>
            {children}
            <div className="fixed z-[70] left-1/2 -translate-x-1/2 bottom-24 lg:bottom-6 flex flex-col gap-2 w-[calc(100%-2rem)] max-w-sm pointer-events-none">
                {toasts.map((t) => {
                    const Icon = icons[t.type] || Info;
                    return (
                        <div key={t.id} className="pointer-events-auto animate-rise flex items-start gap-2.5 rounded-xl border border-line bg-surface px-3.5 py-3 text-sm shadow-xl">
                            <Icon className={cx('h-4 w-4 mt-0.5 shrink-0', t.type === 'error' ? 'text-danger' : t.type === 'success' ? 'text-ok' : 'text-accent')} />
                            <span className="leading-snug">{t.message}</span>
                        </div>
                    );
                })}
            </div>
        </ToastCtx.Provider>
    );
}
