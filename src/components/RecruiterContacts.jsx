import { useMemo, useState } from 'react';
import { Users, Mail, UserSearch, ExternalLink, Copy, ShieldCheck, AlertTriangle } from 'lucide-react';
import { Card, cx, useToast } from './ui';
import { contactsFor, gmailDraftUrl, linkedinNote, linkedinRecruiterSearch } from '../lib/recruitingContacts';

const isApplied = (j) => j.status === 'manual_applied' || j.status === 'applied_confirmed';

/** One row per company in Job Radar: its public recruiting contacts and a ready cold email / LinkedIn note. */
export default function RecruiterContacts({ jobs }) {
    const toast = useToast();
    const [showAll, setShowAll] = useState(false);

    const companies = useMemo(() => {
        const by = new Map();
        for (const j of jobs) {
            if (!j.company) continue;
            const c = by.get(j.company) || { company: j.company, roles: [], applied: false, best: 0, url: '' };
            c.roles.push(j.role);
            c.applied = c.applied || isApplied(j);
            if ((j.match_score || 0) >= c.best) {
                c.best = j.match_score || 0;
                c.topRole = j.role;
                c.url = j.portal_url || j.url || c.url;
            }
            by.set(j.company, c);
        }
        return [...by.values()].sort((a, b) =>
            (b.applied - a.applied) || ((contactsFor(b.company).emails ? 1 : 0) - (contactsFor(a.company).emails ? 1 : 0))
            || (b.best - a.best) || a.company.localeCompare(b.company));
    }, [jobs]);

    const visible = showAll ? companies : companies.slice(0, 12);
    const withEmail = companies.filter((c) => contactsFor(c.company).emails).length;

    const copyNote = (company) => {
        try {
            navigator.clipboard.writeText(linkedinNote(company));
            toast('LinkedIn note copied: paste it in a connection request', 'success');
        } catch {
            toast('Could not copy', 'error');
        }
    };

    return (
        <Card className="card-pad space-y-3">
            <div className="flex items-start gap-2.5">
                <Users className="h-5 w-5 text-cyan-400 shrink-0 mt-0.5" />
                <div>
                    <h2 className="font-bold text-base text-fg">Recruiter contacts</h2>
                    <p className="text-xs text-subtle">
                        {companies.length} companies · {withEmail} publish a recruiting email. For the rest, a short LinkedIn
                        note to their university recruiters works best. Drafts open in your Gmail: you review and send.
                    </p>
                </div>
            </div>

            <div className="divide-y divide-line border-y border-line">
                {visible.map((c) => {
                    const info = contactsFor(c.company);
                    return (
                        <div key={c.company} className="py-2.5 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                            <div className="min-w-0 sm:w-56 shrink-0">
                                <div className="font-semibold text-sm text-fg flex items-center gap-1.5">
                                    {c.company}
                                    {c.applied && <span className="badge text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">Applied</span>}
                                </div>
                                <div className="text-[11px] text-subtle line-clamp-1">
                                    {c.roles.length} role{c.roles.length > 1 ? 's' : ''} · {c.topRole}
                                </div>
                            </div>

                            <div className="flex-1 min-w-0 space-y-1">
                                {(info.emails || []).map((e) => (
                                    <div key={e.address} className="flex items-center gap-2 flex-wrap text-xs">
                                        <a href={gmailDraftUrl(e.address, c.company, c.topRole)} target="_blank" rel="noopener noreferrer"
                                            className="btn btn-primary btn-sm text-xs gap-1" title={`Draft a cold email to ${e.address} in Gmail`}>
                                            <Mail className="h-3.5 w-3.5" /> Draft email
                                        </a>
                                        <span className="font-mono text-fg break-all">{e.address}</span>
                                        <a href={e.source} target="_blank" rel="noopener noreferrer"
                                            className={cx('inline-flex items-center gap-1', e.unconfirmed ? 'text-amber-400' : 'text-subtle hover:text-fg')}
                                            title={e.trust}>
                                            {e.unconfirmed ? <AlertTriangle className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
                                            {e.unconfirmed ? 'unconfirmed' : 'source'}
                                        </a>
                                    </div>
                                ))}
                                {info.note && <div className="text-[11px] text-subtle">{info.note}</div>}
                                {!info.emails && <div className="text-[11px] text-subtle">No public recruiting email: reach out on LinkedIn.</div>}
                            </div>

                            <div className="flex items-center gap-1.5 flex-wrap shrink-0">
                                <a href={linkedinRecruiterSearch(c.company)} target="_blank" rel="noopener noreferrer"
                                    className="btn btn-ghost btn-sm text-xs gap-1" title="Find this company's university recruiters in India on LinkedIn">
                                    <UserSearch className="h-3.5 w-3.5" /> LinkedIn recruiters
                                </a>
                                <button type="button" onClick={() => copyNote(c.company)}
                                    className="btn btn-ghost btn-sm text-xs gap-1" title="Copy a LinkedIn connection note (under 300 characters)">
                                    <Copy className="h-3.5 w-3.5" /> Note
                                </button>
                                {(info.campus || c.url) && (
                                    <a href={info.campus || c.url} target="_blank" rel="noopener noreferrer"
                                        className="btn btn-ghost btn-sm text-xs gap-1" title={info.campus ? 'Campus / careers page' : 'Job posting'}>
                                        <ExternalLink className="h-3.5 w-3.5" /> {info.campus ? 'Careers' : 'Job'}
                                    </a>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
            {companies.length > 12 && (
                <button type="button" onClick={() => setShowAll((v) => !v)} className="text-xs text-subtle hover:text-fg">
                    {showAll ? 'Show fewer' : `Show all ${companies.length} companies`}
                </button>
            )}
        </Card>
    );
}
