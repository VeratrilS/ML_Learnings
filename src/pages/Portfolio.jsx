import { useEffect, useRef, useState } from 'react';
import {
    ArrowRight, ArrowUpRight, Award, BadgeCheck, Boxes, BookOpen, Briefcase, Check, Code2, Copy, Cpu, Database,
    FolderGit2, GitFork, GraduationCap, LayoutDashboard, Mail, MapPin, Radio, Server, Sparkles, Star, Terminal, Train,
    Trophy, Users,
} from 'lucide-react';
import { cx } from '../components/ui';

/*
 * Public portfolio: what visitors see instead of the lock screen.
 * Static content comes from the resume; GitHub and Codeforces are fetched live in the browser, LeetCode via
 * /api/public/stats (LeetCode blocks browser requests). Every live number falls back to the resume figure.
 * Owner access is hidden: tap the dot after the name in the top bar three times quickly (or open #/login).
 */
const EMAIL = 'sairaghava1318@gmail.com';
const GH = 'VeratrilS';
const CF = 'Raghavan_CP';
const URLS = {
    github: 'https://github.com/VeratrilS',
    linkedin: 'https://www.linkedin.com/in/nandam-venkata-sai-raghava-946b3735b/',
    leetcode: 'https://leetcode.com/u/Sairaghava1318/',
    leetcodeContest: 'https://leetcode.com/u/Veratril/',
    codeforces: 'https://codeforces.com/profile/Raghavan_CP',
    codechef: 'https://www.codechef.com/users/sairaghava1318',
    msilCert: 'https://drive.google.com/file/d/1SI_AFaqTetcKILkznr3fn2OW1-HCVuns/view?usp=sharing',
    daProof: 'https://drive.google.com/file/d/1a4eKYbDAV47isPna7iFTe--GVPPcWMwT/view?usp=sharing',
};

const LINKS = [
    { label: 'GitHub', handle: 'VeratrilS', url: URLS.github },
    { label: 'LinkedIn', handle: 'nandam-venkata-sai-raghava', url: URLS.linkedin },
    { label: 'LeetCode', handle: 'Sairaghava1318', url: URLS.leetcode },
    { label: 'Codeforces', handle: 'Raghavan_CP', url: URLS.codeforces },
    { label: 'CodeChef', handle: 'sairaghava1318', url: URLS.codechef },
];

const EXPERIENCE = [
    {
        role: 'Software Engineering Intern',
        org: 'Maruti Suzuki India Limited (MSIL)',
        where: 'Gurugram, India',
        when: 'May 2026 – Jul 2026',
        proof: { label: 'Internship certificate', url: URLS.msilCert },
        metrics: [['13', 'React pages'], ['120+', 'REST APIs'], ['3', 'access roles']],
        points: [
            <>Built the internal <b>ITEA Department Portal</b> (MERN) with employee, attendance, leave, project and task modules.</>,
            <>Developed <b>13 React.js pages</b> integrated with <b>120+ REST APIs</b> (Node.js / Express.js) backed by MongoDB.</>,
            <>Implemented <b>JWT authentication</b> and <b>role-based access control</b> (User, Manager, Admin); reviewed backend code.</>,
        ],
        tags: ['React', 'Node.js', 'Express', 'MongoDB', 'JWT', 'RBAC'],
    },
    {
        role: 'Coding Expert (Freelance)',
        org: 'DataAnnotation.tech',
        where: 'Remote',
        when: 'May 2026 – Present',
        proof: { label: 'Proof of work', url: URLS.daProof },
        metrics: [['C++', 'LLM engine'], ['0', 'API breaks'], ['JS', 'graph evals']],
        points: [
            <>Fixed <b>XTC sampling</b> in a <b>llama.cpp</b>-based C++ LLM inference engine to preserve end-of-sequence and special tokens.</>,
            <>Preserved sampler API <b>backward compatibility</b> via vocabulary-derived token IDs, verified by regression tests.</>,
            <>Evaluated AI-generated JavaScript solutions for graph problems such as Kahn&apos;s topological sort and cycle detection.</>,
        ],
        tags: ['C++', 'llama.cpp', 'LLM inference', 'Regression tests'],
    },
];

const FEATURED = {
    name: 'Distributed Railway Reservation Platform',
    when: 'Aug 2026',
    blurb: 'An IRCTC-style booking backend designed so a seat can never be sold twice, even under concurrent load.',
    flow: ['Clients', 'API Gateway', '8 microservices', 'Kafka · 13 topics', 'Postgres · Redis · Elasticsearch'],
    points: [
        <>Architected <b>8 microservices</b> (database-per-service, Prisma) linked by <b>13 Kafka topics</b> with dead-letter queues.</>,
        <>Prevented <b>double-booking</b> with Redis Lua locks + PostgreSQL row locks; a <b>Saga</b> rolls back failed payments.</>,
        <>API gateway with <b>JWT</b>, <b>sliding-window rate limiting</b> and <b>circuit breakers</b>; Elasticsearch fuzzy search.</>,
    ],
    tags: ['Node.js', 'Apache Kafka', 'Redis', 'PostgreSQL', 'Elasticsearch', 'Prisma', 'Saga pattern'],
    code: 'https://github.com/VeratrilS/IRCTC_Backend',
};

const PROJECTS = [
    {
        name: 'Cache Server', icon: Server, when: 'Jun 2026',
        blurb: 'Redis-compatible in-memory cache in C++17 — works with redis-cli.',
        points: ['RESP parser over raw TCP sockets, pipelined requests', '30 commands: strings, lists, hashes, TTL expiry', 'O(1) LRU / LFU eviction, thread pool, snapshots'],
        tags: ['C++17', 'TCP', 'Multithreading', 'RESP'],
        code: 'https://github.com/VeratrilS/Cache-Server',
    },
    {
        name: 'React-Comps', icon: Boxes, when: 'May 2026',
        blurb: 'Prompt → working React component, with a marketplace and an NPM library.',
        points: ['LLM generation with live preview', 'Firebase sign-in, JWT sessions, credits, Razorpay', 'One-click build, version and publish to NPM'],
        tags: ['React', 'Redux', 'Express', 'MongoDB', 'Firebase', 'Razorpay'],
        code: 'https://github.com/VeratrilS/React-Comps',
        live: 'https://react-comps-zeta.vercel.app',
    },
    {
        name: 'RAG Book Assistant', icon: BookOpen, when: '2026',
        blurb: 'Ask questions about any PDF book; answers are grounded in retrieved passages.',
        points: ['LangChain loaders, chunking and OpenAI embeddings', 'ChromaDB vector store with MMR retrieval', 'Mistral LLM answers, Streamlit + terminal UIs'],
        tags: ['Python', 'LangChain', 'ChromaDB', 'RAG', 'Streamlit'],
        code: 'https://github.com/VeratrilS/GEN_AI',
    },
    {
        name: 'Daily — Productivity Platform', icon: LayoutDashboard, when: '2026',
        blurb: 'The personal dashboard behind this site: DSA practice, revision and study automation.',
        points: ['Flask API + React PWA, Postgres on Vercel', 'FSRS spaced repetition, LLM write-ups, email digests', 'Scheduled jobs via GitHub Actions · 470+ tests'],
        tags: ['Python', 'Flask', 'React', 'PostgreSQL', 'LLMs'],
        code: 'https://github.com/VeratrilS/ML_Learnings',
    },
    {
        name: 'B+ Tree Index', icon: Database, when: 'Feb 2026',
        blurb: 'Disk-backed B+ tree index that simulates how databases store and search data.',
        points: ['File-based page storage', 'Insertion, search and deletion with rebalancing', 'CMake build, DBMS internals'],
        tags: ['C++', 'DBMS', 'Data structures'],
        code: 'https://github.com/VeratrilS/B-Plus-Tree',
    },
];

// Descriptions for repos whose GitHub description is empty (taken from their READMEs).
const REPO_NOTES = {
    'Cache-Server': 'Redis-compatible in-memory cache server in C++17 (RESP, TTL, LRU, persistence).',
    'React-Comps': 'React component platform with AI generation, marketplace and NPM library.',
    GEN_AI: 'RAG Book Assistant: question answering over PDFs with LangChain, ChromaDB and Mistral.',
    'B-Plus-Tree': 'Disk-based B+ tree index in C++ for DBMS internals.',
    ML_Learnings: 'Daily: productivity platform with DSA practice, revision and LLM automation.',
    IRCTC_Backend: 'Distributed railway reservation backend: microservices, Kafka, Redis, Postgres.',
    versus: 'NeetCode problem submissions, synced automatically.',
};

const SKILLS = [
    { group: 'Languages', icon: Terminal, items: ['C++', 'Python', 'JavaScript', 'SQL'] },
    { group: 'Frontend', icon: Sparkles, items: ['React.js', 'Redux', 'Tailwind CSS', 'Vite', 'HTML', 'CSS'] },
    { group: 'Backend & Systems', icon: Server, items: ['Node.js', 'Express.js', 'REST APIs', 'Microservices', 'Apache Kafka', 'Redis', 'Elasticsearch', 'Flask'] },
    { group: 'Data & Tools', icon: Cpu, items: ['PostgreSQL', 'MongoDB', 'Prisma ORM', 'ChromaDB', 'Git', 'GitHub'] },
];

const COURSEWORK = ['Data Structures', 'Algorithms', 'Object-Oriented Programming', 'Database Management Systems', 'Operating Systems', 'Computer Networks'];

const NAV = [['about', 'About'], ['experience', 'Experience'], ['projects', 'Projects'], ['cp', 'Competitive'], ['github', 'GitHub'], ['skills', 'Skills'], ['contact', 'Contact']];

// In-page navigation scrolls instead of changing the hash (the app routes on #/hashes).
const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

/** Live public data. Each source is independent and optional. */
function useLive() {
    const [live, setLive] = useState({ gh: null, repos: null, cf: null, lc: null });
    useEffect(() => {
        let alive = true;
        const set = (patch) => alive && setLive((s) => ({ ...s, ...patch }));
        const json = (url) => fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);
        json(`https://api.github.com/users/${GH}`).then((gh) => set({ gh }));
        json(`https://api.github.com/users/${GH}/repos?per_page=100&sort=pushed`).then((repos) => set({ repos: Array.isArray(repos) ? repos : [] }));
        json(`https://codeforces.com/api/user.info?handles=${CF}`).then((d) => set({ cf: d?.status === 'OK' ? d.result[0] : null }));
        json('/api/public/stats').then((d) => set({ lc: d?.data?.leetcode || null }));
        return () => { alive = false; };
    }, []);
    return live;
}

function SectionHead({ n, eyebrow, title, action }) {
    return (
        <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">
                    <span className="font-mono">{n}</span><span className="h-px w-6 bg-accent/50" /><span className="text-subtle">{eyebrow}</span>
                </div>
                <h2 className="mt-2 text-[26px] sm:text-[32px] font-bold tracking-tight leading-tight">{title}</h2>
            </div>
            {action}
        </div>
    );
}

function Tags({ items, small }) {
    return (
        <div className="flex flex-wrap gap-1.5">
            {items.map((t) => (
                <span key={t} className={cx('rounded-md border border-line bg-surface-2 font-medium text-muted', small ? 'px-1.5 py-px text-[11px]' : 'px-2 py-0.5 text-[12px]')}>{t}</span>
            ))}
        </div>
    );
}

function Ext({ href, children, className }) {
    return (
        <a href={href} target="_blank" rel="noreferrer" className={cx('inline-flex items-center gap-1 font-medium text-accent hover:underline underline-offset-4', className)}>
            {children} <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
        </a>
    );
}

function LiveDot({ on }) {
    if (!on) return null;
    return (
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-ok">
            <span className="relative flex h-1.5 w-1.5"><span className="absolute inline-flex h-full w-full rounded-full bg-ok opacity-60 animate-ping" /><span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-ok" /></span>
            live
        </span>
    );
}

function CopyEmail() {
    const [copied, setCopied] = useState(false);
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(EMAIL);
            setCopied(true);
            setTimeout(() => setCopied(false), 1600);
        } catch { /* clipboard blocked; the mailto link still works */ }
    };
    return (
        <button type="button" onClick={copy} className="btn btn-secondary" aria-label="Copy email address">
            {copied ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />} {copied ? 'Copied' : 'Copy email'}
        </button>
    );
}

function ProfileCard({ live }) {
    const lc = live.lc?.Sairaghava1318;
    const lcContest = live.lc?.Veratril?.contest_rating || lc?.contest_rating;
    const rows = [
        { k: 'LeetCode contest', v: lcContest || 1709, live: !!lcContest, url: URLS.leetcodeContest },
        { k: 'Codeforces', v: live.cf ? `${live.cf.rating} · peak ${live.cf.maxRating}` : 'peak 1425', live: !!live.cf, url: URLS.codeforces },
        { k: 'CodeChef', v: '3★ · peak 1632', url: URLS.codechef },
        { k: 'GitHub', v: live.gh ? `${live.gh.public_repos} public repos` : 'VeratrilS', live: !!live.gh, url: URLS.github },
    ];
    return (
        <div className="card relative overflow-hidden p-5 sm:p-6 shadow-[0_30px_80px_-40px_var(--accent)]">
            <div aria-hidden className="pointer-events-none absolute -top-16 -right-16 h-40 w-40 rounded-full bg-accent opacity-[0.18] blur-2xl" />
            <div className="relative flex items-center gap-4">
                <img src={`https://github.com/${GH}.png?size=160`} alt="Sai Raghava" width="64" height="64"
                    className="h-16 w-16 rounded-2xl object-cover border border-line bg-surface-2" loading="eager" />
                <div className="min-w-0">
                    <div className="font-semibold truncate">Sai Raghava</div>
                    <div className="text-sm text-muted truncate">Software Engineer · NIT Rourkela</div>
                    <div className="mt-1 inline-flex items-center gap-1.5 text-xs text-subtle"><MapPin className="h-3.5 w-3.5" /> Nellore, India</div>
                </div>
            </div>
            <dl className="relative mt-5 divide-y divide-line rounded-xl border border-line bg-surface-2/50">
                {rows.map((r) => (
                    <a key={r.k} href={r.url} target="_blank" rel="noreferrer" className="group flex items-center justify-between gap-3 px-3.5 py-2.5 hover:bg-surface-2 transition-colors first:rounded-t-xl last:rounded-b-xl">
                        <dt className="text-sm text-muted flex items-center gap-2">{r.k} <LiveDot on={r.live} /></dt>
                        <dd className="text-sm font-semibold tabular-nums flex items-center gap-1">{r.v} <ArrowUpRight className="h-3.5 w-3.5 text-subtle group-hover:text-accent transition-colors" /></dd>
                    </a>
                ))}
            </dl>
            <div className="relative mt-4 rounded-xl bg-[#0b0b0e] border border-white/10 px-3.5 py-3 font-mono text-[12px] leading-relaxed text-white/80">
                <div><span className="text-emerald-400">$</span> whoami</div>
                <div className="text-white/60">backend · distributed systems · C++ · competitive programming</div>
                <div><span className="text-emerald-400">$</span> status <span className="text-orange-300">--open-to-work</span></div>
                <div className="text-white/60">SDE · full-time · 2027<span className="caret" /></div>
            </div>
        </div>
    );
}

function GitHubSection({ live }) {
    const repos = (live.repos || [])
        .filter((r) => !r.fork && !r.archived)
        .sort((a, b) => (b.stargazers_count - a.stargazers_count) || ((REPO_NOTES[b.name] ? 1 : 0) - (REPO_NOTES[a.name] ? 1 : 0)) || (new Date(b.pushed_at) - new Date(a.pushed_at)))
        .slice(0, 6);
    const langs = Object.entries((live.repos || []).filter((r) => !r.fork && r.language)
        .reduce((m, r) => ({ ...m, [r.language]: (m[r.language] || 0) + 1 }), {}))
        .sort((a, b) => b[1] - a[1]).slice(0, 5);
    const total = langs.reduce((s, [, n]) => s + n, 0);

    return (
        <div className="space-y-4">
            {live.gh && (
                <div className="card p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-4">
                    <div className="flex items-center gap-6 shrink-0">
                        <div><div className="text-2xl font-bold tabular-nums">{live.gh.public_repos}</div><div className="text-xs text-muted">public repos</div></div>
                        <div><div className="text-2xl font-bold tabular-nums">{live.gh.followers}</div><div className="text-xs text-muted">followers</div></div>
                    </div>
                    {total > 0 && (
                        <div className="flex-1 min-w-0">
                            <div className="flex h-2 rounded-full overflow-hidden gap-0.5" role="img" aria-label={`Languages: ${langs.map(([l, n]) => `${l} ${n}`).join(', ')}`}>
                                {langs.map(([l, n], i) => (
                                    <span key={l} title={`${l}: ${n} repos`} style={{ width: `${(100 * n) / total}%`, opacity: 1 - i * 0.16 }} className="bg-accent" />
                                ))}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                                {langs.map(([l, n], i) => (
                                    <span key={l} className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-accent" style={{ opacity: 1 - i * 0.16 }} />{l} <span className="text-subtle">{n}</span></span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {live.repos === null
                    ? [0, 1, 2].map((i) => <div key={i} className="card h-36 animate-pulse bg-surface-2" />)
                    : repos.length
                        ? repos.map((r) => (
                            <a key={r.id} href={r.html_url} target="_blank" rel="noreferrer" className="group card p-5 flex flex-col hover:border-accent/50 hover:-translate-y-0.5 transition-all">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="flex items-center gap-2 font-semibold min-w-0"><FolderGit2 className="h-4 w-4 text-accent shrink-0" /><span className="truncate">{r.name}</span></span>
                                    <ArrowUpRight className="h-4 w-4 text-subtle group-hover:text-accent transition-colors shrink-0" />
                                </div>
                                <p className="mt-2 text-sm text-muted line-clamp-2 flex-1">{r.description || REPO_NOTES[r.name] || `${r.language || 'Code'} project.`}</p>
                                <div className="mt-3 flex items-center gap-3 text-xs text-subtle">
                                    {r.language && <span className="font-medium text-muted">{r.language}</span>}
                                    <span className="inline-flex items-center gap-1"><Star className="h-3.5 w-3.5" /> {r.stargazers_count}</span>
                                    {r.forks_count > 0 && <span className="inline-flex items-center gap-1"><GitFork className="h-3.5 w-3.5" /> {r.forks_count}</span>}
                                    {r.homepage && <span className="text-ok font-medium">live</span>}
                                    <span className="ml-auto">{new Date(r.pushed_at).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}</span>
                                </div>
                            </a>
                        ))
                        : Object.entries(REPO_NOTES).slice(0, 6).map(([name, note]) => (
                            <a key={name} href={`${URLS.github}/${name}`} target="_blank" rel="noreferrer" className="group card p-5 flex flex-col hover:border-accent/50 hover:-translate-y-0.5 transition-all">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="flex items-center gap-2 font-semibold min-w-0"><FolderGit2 className="h-4 w-4 text-accent shrink-0" /><span className="truncate">{name}</span></span>
                                    <ArrowUpRight className="h-4 w-4 text-subtle group-hover:text-accent transition-colors shrink-0" />
                                </div>
                                <p className="mt-2 text-sm text-muted line-clamp-2 flex-1">{note}</p>
                            </a>
                        ))}
            </div>
        </div>
    );
}

function CPSection({ live }) {
    const lc = live.lc?.Sairaghava1318;
    const lcContest = live.lc?.Veratril || null;
    const cards = [
        {
            icon: Code2, title: 'LeetCode',
            big: lcContest?.contest_rating || 1709, bigLabel: 'contest rating', live: !!lcContest?.contest_rating,
            lines: [
                lc ? `${lc.total} solved · ${lc.easy}E / ${lc.medium}M / ${lc.hard}H` : '900+ problems solved',
                lcContest?.top_percentage ? `Top ${lcContest.top_percentage}% · ${lcContest.contests_attended} contests` : 'Contest rating from the Veratril account',
                `${lc?.badges || 15} badges incl. 365 Days, SQL`,
            ],
            links: [{ label: 'Contest', url: URLS.leetcodeContest }, { label: 'Profile', url: URLS.leetcode }],
        },
        {
            icon: Trophy, title: 'Codeforces',
            big: live.cf?.maxRating || 1425, bigLabel: 'peak rating · Specialist', live: !!live.cf,
            lines: [live.cf ? `Current ${live.cf.rating} (${live.cf.rank})` : 'Specialist (peak)', '325+ problems solved'],
            links: [{ label: 'Profile', url: URLS.codeforces }],
        },
        {
            icon: Award, title: 'CodeChef',
            big: 1632, bigLabel: 'peak rating · 3★',
            lines: ['23 rated contests', '437 problems solved'],
            links: [{ label: 'Profile', url: URLS.codechef }],
        },
    ];
    return (
        <div className="grid gap-3 md:grid-cols-3">
            {cards.map((c) => (
                <div key={c.title} className="card p-5 sm:p-6 flex flex-col">
                    <div className="flex items-center justify-between">
                        <span className="flex items-center gap-2 font-semibold"><c.icon className="h-5 w-5 text-accent" /> {c.title}</span>
                        <LiveDot on={c.live} />
                    </div>
                    <div className="mt-4 text-4xl font-extrabold tracking-tight tabular-nums">{c.big}</div>
                    <div className="text-xs text-subtle">{c.bigLabel}</div>
                    <ul className="mt-4 space-y-1 text-sm text-muted flex-1">{c.lines.map((l) => <li key={l}>{l}</li>)}</ul>
                    <div className="mt-4 pt-3 border-t border-line flex gap-4 text-sm">{c.links.map((l) => <Ext key={l.url} href={l.url}>{l.label}</Ext>)}</div>
                </div>
            ))}
        </div>
    );
}

export default function Portfolio({ onUnlock }) {
    const live = useLive();
    const taps = useRef([]);

    useEffect(() => {
        const prev = document.title;
        document.title = 'Nandam Venkata Sai Raghava · Software Engineer';
        return () => { document.title = prev; };
    }, []);

    // Hidden owner entrance: three quick taps on the dot after the name.
    const secretTap = () => {
        const now = Date.now();
        taps.current = [...taps.current.filter((t) => now - t < 1200), now];
        if (taps.current.length >= 3) {
            taps.current = [];
            onUnlock?.();
        }
    };

    const lcTotal = live.lc?.Sairaghava1318?.total;
    const solved = 325 + 437 + Math.max(900, lcTotal || 0);

    return (
        <div className="min-h-dvh bg-bg text-fg relative">
            <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[640px] opacity-60 [background-image:radial-gradient(var(--line-strong)_1px,transparent_1px)] [background-size:22px_22px] [mask-image:linear-gradient(to_bottom,black,transparent)]" />

            <header className="sticky top-0 z-40 border-b border-line bg-bg/75 backdrop-blur-xl">
                <div className="mx-auto max-w-6xl h-14 px-4 sm:px-6 flex items-center justify-between gap-3">
                    <span className="font-bold tracking-tight truncate select-none">
                        <button type="button" onClick={() => scrollTo('about')}>Sai Raghava</button>
                        <span onClick={secretTap} className="text-accent cursor-default px-0.5" aria-hidden>.</span>
                    </span>
                    <nav className="hidden lg:flex items-center gap-0.5 text-sm">
                        {NAV.map(([id, label]) => (
                            <button key={id} type="button" onClick={() => scrollTo(id)} className="px-3 h-8 rounded-lg text-muted hover:text-fg hover:bg-surface-2 transition-colors">{label}</button>
                        ))}
                    </nav>
                    <a href={`mailto:${EMAIL}`} className="btn btn-primary btn-sm shrink-0"><Mail className="h-4 w-4" /> Hire me</a>
                </div>
                <nav className="lg:hidden flex gap-1 overflow-x-auto no-scrollbar px-4 pb-2 -mt-1 text-[13px]">
                    {NAV.map(([id, label]) => (
                        <button key={id} type="button" onClick={() => scrollTo(id)} className="shrink-0 px-3 h-7 rounded-full border border-line text-muted bg-surface">{label}</button>
                    ))}
                </nav>
            </header>

            <main className="relative mx-auto max-w-6xl px-4 sm:px-6 pb-20 space-y-20 sm:space-y-28">
                {/* Hero */}
                <section id="about" className="relative pt-10 sm:pt-20 scroll-mt-28 grid gap-10 lg:grid-cols-[1.25fr_1fr] lg:items-center">
                    <div aria-hidden className="pointer-events-none absolute -top-10 -left-16 h-80 w-80 rounded-full bg-accent opacity-[0.13] blur-3xl" />
                    <div className="relative animate-rise min-w-0">
                        <div className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-muted">
                            <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full rounded-full bg-ok opacity-60 animate-ping" /><span className="relative inline-flex h-2 w-2 rounded-full bg-ok" /></span>
                            Open to full-time SDE roles · 2027
                        </div>
                        <h1 className="mt-5 text-[42px] leading-[1.02] sm:text-[68px] font-extrabold tracking-[-0.03em]">
                            Nandam Venkata<br />
                            <span className="bg-gradient-to-r from-accent to-orange-400 bg-clip-text text-transparent">Sai Raghava</span>
                        </h1>
                        <p className="mt-5 max-w-xl text-base sm:text-lg text-muted leading-relaxed">
                            Backend-leaning software engineer and competitive programmer at <b className="text-fg">NIT Rourkela</b>.
                            I build systems that hold up under load — event-driven microservices, a Redis-compatible cache in C++,
                            and production MERN apps shipped at <b className="text-fg">Maruti Suzuki</b>.
                        </p>
                        <div className="mt-7 flex flex-wrap gap-2">
                            <button type="button" onClick={() => scrollTo('projects')} className="btn btn-primary btn-lg">View projects <ArrowRight className="h-4 w-4" /></button>
                            <a href={URLS.github} target="_blank" rel="noreferrer" className="btn btn-secondary btn-lg"><FolderGit2 className="h-4 w-4" /> GitHub</a>
                            <a href={URLS.linkedin} target="_blank" rel="noreferrer" className="btn btn-secondary btn-lg">LinkedIn <ArrowUpRight className="h-4 w-4" /></a>
                        </div>
                        <div className="mt-10 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-5 max-w-xl">
                            {[
                                ['8.99', 'CGPA'],
                                [`${solved.toLocaleString()}+`, 'problems solved'],
                                ['2', 'industry roles'],
                                ['17+', 'public repos'],
                            ].map(([v, l]) => (
                                <div key={l}>
                                    <div className="text-2xl sm:text-[28px] font-extrabold tracking-tight tabular-nums">{v}</div>
                                    <div className="text-xs text-subtle mt-0.5">{l}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="relative animate-rise [animation-delay:80ms]"><ProfileCard live={live} /></div>
                </section>

                <section id="experience" className="scroll-mt-28">
                    <SectionHead n="01" eyebrow="Experience" title="Where I've shipped code" />
                    <ol className="mt-8 relative border-l border-line ml-2 space-y-8">
                        {EXPERIENCE.map((x) => (
                            <li key={x.org} className="pl-6 sm:pl-8 relative">
                                <span className="absolute -left-[7px] top-2 h-3.5 w-3.5 rounded-full border-2 border-accent bg-bg" />
                                <div className="card p-5 sm:p-7">
                                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-1 sm:gap-4">
                                        <div className="min-w-0">
                                            <h3 className="text-lg sm:text-xl font-semibold tracking-tight">{x.role}</h3>
                                            <div className="mt-0.5 text-sm text-accent font-medium flex items-center gap-1.5"><Briefcase className="h-3.5 w-3.5 shrink-0" /> {x.org}</div>
                                        </div>
                                        <div className="text-xs sm:text-right text-subtle shrink-0">
                                            <div className="font-medium text-muted">{x.when}</div>
                                            <div>{x.where}</div>
                                        </div>
                                    </div>
                                    <div className="mt-5 grid grid-cols-3 gap-2 max-w-md">
                                        {x.metrics.map(([v, l]) => (
                                            <div key={l} className="rounded-xl border border-line bg-surface-2/60 px-3 py-2">
                                                <div className="text-lg font-bold tabular-nums">{v}</div>
                                                <div className="text-[11px] text-subtle leading-tight">{l}</div>
                                            </div>
                                        ))}
                                    </div>
                                    <ul className="mt-5 space-y-2 text-sm text-muted leading-relaxed list-disc pl-5 marker:text-accent/60 [&_b]:text-fg [&_b]:font-semibold">
                                        {x.points.map((p, i) => <li key={i}>{p}</li>)}
                                    </ul>
                                    <div className="mt-5 pt-4 border-t border-line flex flex-wrap items-center justify-between gap-3">
                                        <Tags items={x.tags} />
                                        <Ext href={x.proof.url} className="text-sm"><BadgeCheck className="h-4 w-4" /> {x.proof.label}</Ext>
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ol>
                </section>

                <section id="projects" className="scroll-mt-28">
                    <SectionHead n="02" eyebrow="Projects" title="Things I've built" />
                    <article className="mt-8 card relative overflow-hidden p-5 sm:p-8">
                        <div aria-hidden className="pointer-events-none absolute -bottom-24 -right-24 h-72 w-72 rounded-full bg-accent opacity-[0.10] blur-3xl" />
                        <div className="relative flex flex-wrap items-center gap-2">
                            <span className="badge bg-accent text-accent-fg">Featured</span>
                            <span className="text-xs text-subtle">{FEATURED.when}</span>
                        </div>
                        <div className="relative mt-3 grid gap-8 lg:grid-cols-2">
                            <div className="min-w-0">
                                <h3 className="text-xl sm:text-2xl font-bold tracking-tight flex items-center gap-2"><Train className="h-6 w-6 text-accent shrink-0" /> {FEATURED.name}</h3>
                                <p className="mt-2 text-muted">{FEATURED.blurb}</p>
                                <ul className="mt-5 space-y-2 text-sm text-muted leading-relaxed list-disc pl-5 marker:text-accent/60 [&_b]:text-fg [&_b]:font-semibold">
                                    {FEATURED.points.map((p, i) => <li key={i}>{p}</li>)}
                                </ul>
                                <div className="mt-5"><Tags items={FEATURED.tags} /></div>
                                <div className="mt-5"><Ext href={FEATURED.code} className="text-sm">View code</Ext></div>
                            </div>
                            <div className="rounded-2xl border border-line bg-surface-2/60 p-4 sm:p-5" aria-label="Architecture: clients to API gateway to 8 microservices to Kafka to data stores">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-subtle">Architecture</div>
                                <ol className="mt-3 space-y-1.5">
                                    {FEATURED.flow.map((step, i) => (
                                        <li key={step}>
                                            <div className={cx('rounded-xl border px-3.5 py-2.5 text-sm font-medium flex items-center justify-between', i === 3 ? 'border-accent/50 bg-accent-soft text-fg' : 'border-line bg-surface')}>
                                                <span>{step}</span>
                                                <span className="font-mono text-[11px] text-subtle">{['edge', 'auth · rate limit', 'db-per-service', 'events · DLQ', 'locks · search'][i]}</span>
                                            </div>
                                            {i < FEATURED.flow.length - 1 && <div className="ml-6 h-2.5 w-px bg-line-strong" />}
                                        </li>
                                    ))}
                                </ol>
                                <p className="mt-3 text-xs text-subtle">Saga orchestration rolls back seat holds when payment fails.</p>
                            </div>
                        </div>
                    </article>

                    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {PROJECTS.map((p) => (
                            <article key={p.name} className="group card p-5 sm:p-6 flex flex-col hover:border-accent/40 hover:-translate-y-0.5 transition-all">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0"><p.icon className="h-5 w-5" /></div>
                                    <span className="text-xs text-subtle font-medium">{p.when}</span>
                                </div>
                                <h3 className="mt-4 text-lg font-semibold tracking-tight">{p.name}</h3>
                                <p className="mt-1 text-sm text-muted">{p.blurb}</p>
                                <ul className="mt-4 space-y-1.5 text-[13px] text-muted">
                                    {p.points.map((pt) => <li key={pt} className="flex gap-2"><Check className="h-3.5 w-3.5 text-accent mt-0.5 shrink-0" /> {pt}</li>)}
                                </ul>
                                <div className="mt-auto pt-5"><Tags items={p.tags} small /></div>
                                <div className="mt-4 pt-3 border-t border-line flex gap-4 text-sm">
                                    <Ext href={p.code}>Code</Ext>
                                    {p.live && <Ext href={p.live}>Live demo</Ext>}
                                </div>
                            </article>
                        ))}
                    </div>
                </section>

                <section id="cp" className="scroll-mt-28">
                    <SectionHead n="03" eyebrow="Competitive programming" title={`${solved.toLocaleString()}+ problems across three platforms`} />
                    <div className="mt-8"><CPSection live={live} /></div>
                </section>

                <section id="github" className="scroll-mt-28">
                    <SectionHead n="04" eyebrow="Open source" title="Live from GitHub" action={<Ext href={URLS.github} className="text-sm">github.com/{GH}</Ext>} />
                    <div className="mt-8"><GitHubSection live={live} /></div>
                </section>

                <section id="skills" className="scroll-mt-28">
                    <SectionHead n="05" eyebrow="Toolbox" title="Skills & education" />
                    <div className="mt-8 grid gap-4 lg:grid-cols-5">
                        <div className="card p-5 sm:p-7 lg:col-span-3 grid gap-6 sm:grid-cols-2">
                            {SKILLS.map((s) => (
                                <div key={s.group}>
                                    <div className="flex items-center gap-2 text-sm font-semibold"><s.icon className="h-4 w-4 text-accent" /> {s.group}</div>
                                    <div className="mt-2.5"><Tags items={s.items} /></div>
                                </div>
                            ))}
                        </div>
                        <div className="lg:col-span-2 space-y-4">
                            <div className="card p-5 sm:p-6">
                                <div className="flex items-center gap-2 text-sm font-semibold"><GraduationCap className="h-4 w-4 text-accent" /> Education</div>
                                <div className="mt-3 flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="font-semibold">NIT Rourkela</div>
                                        <div className="text-sm text-muted">B.Tech, Computer Science & Engineering</div>
                                        <div className="text-xs text-subtle mt-0.5">Aug 2023 – 2027</div>
                                    </div>
                                    <div className="text-right shrink-0"><div className="text-xl font-bold tabular-nums">8.99</div><div className="text-[11px] text-subtle">CGPA</div></div>
                                </div>
                                <div className="mt-4 pt-4 border-t border-line flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="font-semibold">Narayana Junior College</div>
                                        <div className="text-sm text-muted">Intermediate · AP Board</div>
                                        <div className="text-xs text-subtle mt-0.5">May 2023</div>
                                    </div>
                                    <div className="text-right shrink-0"><div className="text-xl font-bold tabular-nums">97.1%</div><div className="text-[11px] text-subtle">score</div></div>
                                </div>
                                <div className="mt-4 pt-4 border-t border-line">
                                    <div className="text-xs font-medium text-subtle mb-2">Relevant coursework</div>
                                    <Tags items={COURSEWORK} small />
                                </div>
                            </div>
                            <div className="card p-5 sm:p-6">
                                <div className="flex items-center gap-2 text-sm font-semibold"><Users className="h-4 w-4 text-accent" /> OpenCode Club, NIT Rourkela</div>
                                <div className="mt-1 text-sm text-muted">Technical Team Member · Nov 2023 – Present</div>
                                <p className="mt-2 text-sm text-muted">Organizing technical events, hands-on workshops and club activities.</p>
                            </div>
                        </div>
                    </div>
                </section>

                <section id="contact" className="scroll-mt-28">
                    <div className="card relative overflow-hidden p-7 sm:p-12 text-center">
                        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-50 [background-image:radial-gradient(var(--line-strong)_1px,transparent_1px)] [background-size:20px_20px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
                        <div aria-hidden className="pointer-events-none absolute -bottom-28 left-1/2 -translate-x-1/2 h-72 w-[40rem] max-w-full rounded-full bg-accent opacity-[0.16] blur-3xl" />
                        <div className="relative">
                            <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-accent"><Radio className="h-3.5 w-3.5" /> 06 · Contact</div>
                            <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">Let&apos;s build something.</h2>
                            <p className="mt-3 text-muted max-w-md mx-auto">Hiring for a 2027 SDE role, or want to talk systems and algorithms? My inbox is open.</p>
                            <a href={`mailto:${EMAIL}`} className="mt-6 inline-block text-lg sm:text-2xl font-semibold text-accent hover:underline underline-offset-4 break-all">{EMAIL}</a>
                            <div className="mt-6 flex flex-wrap justify-center gap-2">
                                <a href={`mailto:${EMAIL}`} className="btn btn-primary btn-lg"><Mail className="h-4 w-4" /> Email me</a>
                                <CopyEmail />
                            </div>
                            <div className="mt-8 flex flex-wrap justify-center gap-2">
                                {LINKS.map((l) => (
                                    <a key={l.label} href={l.url} target="_blank" rel="noreferrer"
                                        className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3.5 h-9 text-sm font-medium hover:border-accent/50 hover:text-accent transition-colors max-w-full">
                                        {l.label} <span className="text-subtle font-normal truncate">@{l.handle}</span> <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
                                    </a>
                                ))}
                            </div>
                        </div>
                    </div>
                    <footer className="mt-10 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-subtle">
                        <span>© {new Date().getFullYear()} Nandam Venkata Sai Raghava</span>
                        <span>Built with React, Tailwind & Flask · live data from GitHub, LeetCode and Codeforces</span>
                    </footer>
                </section>
            </main>
        </div>
    );
}
