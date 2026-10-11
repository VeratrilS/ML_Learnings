import { ExternalLink } from 'lucide-react';
import { timeAgo, navigate } from '../lib/hooks';
import { Checkbox, DifficultyBadge, cx } from './ui';

export default function ProblemRow({ log, onToggle, compact }) {
    return (
        <li
            onClick={() => navigate(`problems/${log.id}`)}
            className="group flex items-center gap-3 px-3 sm:px-4 py-3 row-hover cursor-pointer"
        >
            <Checkbox checked={log.is_completed} onChange={(v) => onToggle(log, v)} label={`Mark ${log.title} solved`} />
            <div className="min-w-0 flex-1">
                <div className={cx('text-sm font-medium truncate', log.is_completed && 'text-subtle line-through decoration-line-strong')}>
                    {log.title}
                </div>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-subtle min-w-0">
                    <DifficultyBadge value={log.difficulty} />
                    {log.topic && <span className="truncate">{log.topic}</span>}
                    {!compact && <span className="shrink-0 hidden sm:inline">· {timeAgo(log.timestamp)}</span>}
                </div>
            </div>
            {log.link && (
                <a
                    href={log.link}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="btn btn-ghost btn-icon btn-sm shrink-0 opacity-70 group-hover:opacity-100"
                    aria-label="Open on LeetCode"
                    title="Open on LeetCode"
                >
                    <ExternalLink className="h-4 w-4" />
                </a>
            )}
        </li>
    );
}
