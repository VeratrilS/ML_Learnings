import { useState } from 'react';
import { Lightbulb, Link2, Sparkles, X } from 'lucide-react';
import { api } from '../lib/api';
import { invalidate } from '../lib/hooks';
import { Button, cx, useToast } from './ui';

// Mirrors CATEGORIES in api/domain/mistakes.py (order + labels). Tones use semantic colours only.
const CATEGORIES = [
    { key: 'off_by_one', label: 'Off by one', tone: 'text-medium bg-medium/10' },
    { key: 'wrong_pattern', label: 'Wrong pattern', tone: 'text-accent bg-accent-soft' },
    { key: 'missed_edge_case', label: 'Missed edge case', tone: 'text-hard bg-hard/10' },
    { key: 'tle_complexity', label: 'TLE / complexity', tone: 'text-danger bg-danger/10' },
    { key: 'misread_problem', label: 'Misread problem', tone: 'text-easy bg-easy/10' },
    { key: 'overflow', label: 'Overflow', tone: 'text-ok bg-ok/10' },
    { key: 'implementation_bug', label: 'Implementation bug', tone: 'text-fg bg-surface-3' },
    { key: 'other', label: 'Other', tone: 'text-muted bg-surface-2' },
];
const BY_KEY = Object.fromEntries(CATEGORIES.map((c) => [c.key, c]));

export function CategoryBadge({ category, label, className }) {
    const c = BY_KEY[category] || BY_KEY.other;
    return <span className={cx('badge', c.tone, className)}>{label || c.label}</span>;
}

const isUrl = (s) => /^https?:\/\/\S+$/i.test(s);

/**
 * Compact "What went wrong?" form. With `log` (a problem from /api/problems) the entry is tied to it
 * and title/link come from the server; without it the user can type them. Calls onSaved(mistake, source).
 */
export default function MistakeQuickAdd({ log, onSaved }) {
    const toast = useToast();
    const [what, setWhat] = useState('');
    const [title, setTitle] = useState('');
    const [link, setLink] = useState('');
    const [category, setCategory] = useState(null); // null = let the AI decide
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [saved, setSaved] = useState(null);

    const linkBad = !log && link.trim() && !isUrl(link.trim());
    const canSave = what.trim().length > 0 && !linkBad && !saving;

    async function submit(e) {
        e?.preventDefault();
        if (!canSave) return;
        setSaving(true);
        setError('');
        try {
            const body = { what_happened: what.trim() };
            if (category) body.category = category;
            if (log?.id != null) body.log_id = log.id;
            else {
                if (title.trim()) body.problem_title = title.trim();
                if (link.trim()) body.link = link.trim();
            }
            const res = await api('/mistakes', { method: 'POST', body });
            invalidate('/mistakes');
            setSaved(res.data);
            setWhat('');
            setTitle('');
            setLink('');
            setCategory(null);
            toast(res.source === 'ai' ? 'Logged. AI wrote your lesson.' : 'Logged.', 'success');
            onSaved?.(res.data, res.source);
        } catch (err) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    }

    return (
        <form onSubmit={submit} className="space-y-3 min-w-0">
            <div>
                <label htmlFor="mistake-what" className="label">
                    What went wrong?
                    {log?.title && <span className="text-subtle font-normal"> · {log.title}</span>}
                </label>
                <textarea
                    id="mistake-what"
                    value={what}
                    onChange={(e) => { setWhat(e.target.value); if (saved) setSaved(null); }}
                    onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e); }}
                    rows={2}
                    maxLength={2000}
                    placeholder="e.g. Used < instead of <= in the binary search, missed the last index"
                    className="input h-auto min-h-[68px] py-2.5 leading-relaxed resize-y"
                />
            </div>

            {!log && (
                <div className="grid gap-2 sm:grid-cols-2">
                    <input
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        maxLength={200}
                        placeholder="Problem (optional)"
                        aria-label="Problem title"
                        className="input"
                    />
                    <div className="relative">
                        <Link2 className="h-4 w-4 text-subtle absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden />
                        <input
                            value={link}
                            onChange={(e) => setLink(e.target.value)}
                            maxLength={500}
                            inputMode="url"
                            placeholder="https://… (optional)"
                            aria-label="Problem link"
                            aria-invalid={!!linkBad}
                            className={cx('input pl-9', linkBad && 'border-danger focus:border-danger')}
                        />
                    </div>
                </div>
            )}

            <div className="-mx-1 px-1 flex gap-1.5 overflow-x-auto no-scrollbar sm:flex-wrap" role="radiogroup" aria-label="Category">
                <button
                    type="button"
                    role="radio"
                    aria-checked={category === null}
                    onClick={() => setCategory(null)}
                    className={cx('chip shrink-0', category === null && 'chip-on')}
                >
                    <Sparkles className="h-3 w-3" aria-hidden /> Auto
                </button>
                {CATEGORIES.filter((c) => c.key !== 'other').map((c) => (
                    <button
                        key={c.key}
                        type="button"
                        role="radio"
                        aria-checked={category === c.key}
                        onClick={() => setCategory(category === c.key ? null : c.key)}
                        className={cx('chip shrink-0', category === c.key && 'chip-on')}
                    >
                        {c.label}
                    </button>
                ))}
            </div>

            {(error || linkBad) && (
                <p className="text-[13px] text-danger" role="alert">{error || 'Link must start with http:// or https://'}</p>
            )}

            <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-subtle hidden sm:block">Ctrl + Enter to save</p>
                <Button type="submit" variant="primary" size="sm" icon={Sparkles} loading={saving} disabled={!canSave} className="w-full sm:w-auto">
                    {saving ? 'Tagging…' : 'Save lesson'}
                </Button>
            </div>

            {saved && (
                <div className="animate-rise flex items-start gap-2.5 rounded-xl border border-line bg-surface-2 p-3">
                    <Lightbulb className="h-4 w-4 text-accent mt-0.5 shrink-0" aria-hidden />
                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            <CategoryBadge category={saved.category} label={saved.category_label} />
                            {saved.pattern && <span className="badge text-muted bg-surface-3">{saved.pattern}</span>}
                        </div>
                        <p className="text-[13px] leading-snug">{saved.lesson || saved.what_happened}</p>
                    </div>
                    <button type="button" onClick={() => setSaved(null)} className="btn btn-ghost btn-icon h-7 w-7 -m-1" aria-label="Dismiss">
                        <X className="h-3.5 w-3.5" />
                    </button>
                </div>
            )}
        </form>
    );
}
