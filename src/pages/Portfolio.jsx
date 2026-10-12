import { useEffect, useRef, useState } from 'react';
import {
    ArrowRight, ArrowUp, ArrowUpRight, Award, BadgeCheck, Boxes, BookOpen, Briefcase, Check, Code2, Copy, Cpu, Database,
    FolderGit2, GitFork, GraduationCap, LayoutDashboard, Mail, MapPin, Moon, Radio, Server, Sparkles, Star, Sun, Terminal,
    Train, Trophy, Users,
} from 'lucide-react';
import { cx } from '../components/ui';
import { useTheme } from '../themes/ThemeContext';

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
        proof: { label: 'Proof of work', url: URLS.daProof, ownerOnly: true }, // only shown behind the lock
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
const FLOW_NOTES = ['edge', 'auth · rate limit', 'db-per-service', 'events · DLQ', 'locks · search'];

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

// "Now" strip: only facts stated elsewhere on this page.
const NOW = [
    { icon: Briefcase, label: 'Coding Expert at DataAnnotation.tech', sub: 'May 2026 – Present' },
    { icon: GraduationCap, label: 'B.Tech CSE at NIT Rourkela', sub: 'Class of 2027 · 8.99 CGPA' },
    { icon: LayoutDashboard, label: 'Building Daily', sub: 'The dashboard behind this site' },
    { icon: Users, label: 'OpenCode Club', sub: 'Technical team member' },
];

// Rotating focus line in the hero (same words as the profile card's `whoami`).
const ROLES = ['backend engineering', 'distributed systems', 'C++ systems', 'competitive programming'];

const NAV = [['about', 'About'], ['experience', 'Experience'], ['projects', 'Projects'], ['cp', 'Competitive'], ['github', 'GitHub'], ['skills', 'Skills'], ['contact', 'Contact']];
const NAV_IDS = NAV.map(([id]) => id);

const prefersReduced = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

// In-page navigation scrolls instead of changing the hash (the app routes on #/hashes). Focus follows for keyboard users.
const scrollTo = (id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: prefersReduced() ? 'auto' : 'smooth', block: 'start' });
    el.focus?.({ preventScroll: true });
};

// Page-scoped motion styles. Transform/opacity-only where it repeats; every animation is off under prefers-reduced-motion.
const PF_CSS = `
:root{--pf-shine:#b93d06}
:root[data-theme="dark"]{--pf-shine:#ffd3b0}
@keyframes pf-enter{from{opacity:0;transform:translateY(18px);filter:blur(8px)}to{opacity:1;transform:none;filter:none}}
@keyframes pf-enter-scale{from{opacity:0;transform:translateY(16px) scale(.94)}to{opacity:1;transform:none}}
.pf-enter{animation:pf-enter .85s cubic-bezier(.2,.7,.2,1) var(--d,0ms) both}
.pf-enter-scale{animation:pf-enter-scale 1s cubic-bezier(.2,.7,.2,1) var(--d,0ms) both}
@keyframes pf-shimmer{from{background-position:0% 50%}to{background-position:-100% 50%}}
.pf-shimmer{background-image:linear-gradient(90deg,var(--accent) 0%,var(--pf-shine) 25%,var(--accent) 50%,var(--pf-shine) 75%,var(--accent) 100%);background-size:200% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:pf-shimmer 7s linear infinite}
.pf-reveal{opacity:0;translate:0 28px;scale:.985;transition:opacity .8s cubic-bezier(.2,.7,.2,1) var(--pf-delay,0ms),translate .8s cubic-bezier(.2,.7,.2,1) var(--pf-delay,0ms),scale .8s cubic-bezier(.2,.7,.2,1) var(--pf-delay,0ms)}
.pf-reveal.pf-in{opacity:1;translate:none;scale:none}
.pf-draw{scale:0 1;transform-origin:left;transition:scale .9s cubic-bezier(.2,.7,.2,1) .25s}
.pf-in .pf-draw{scale:1 1}
@keyframes pf-pop{from{opacity:0;transform:translateY(6px) scale(.85)}to{opacity:1;transform:none}}
.pf-reveal:not(.pf-in) .pf-tag{opacity:0}
.pf-in .pf-tag{animation:pf-pop .45s cubic-bezier(.2,.9,.3,1.2) calc(var(--pf-delay,0ms) + 280ms + var(--i,0) * 35ms) both}
.pf-spot{isolation:isolate;transition:translate .3s cubic-bezier(.2,.7,.2,1),box-shadow .3s ease,border-color .3s ease}
.pf-spot::before{content:"";position:absolute;inset:0;z-index:-1;border-radius:inherit;pointer-events:none;opacity:0;transition:opacity .3s ease;background:radial-gradient(360px circle at var(--mx,50%) var(--my,0%),var(--accent-soft),transparent 65%)}
.pf-spot::after{content:"";position:absolute;inset:-1px;border-radius:inherit;pointer-events:none;opacity:0;transition:opacity .3s ease;padding:1px;background:radial-gradient(220px circle at var(--mx,50%) var(--my,0%),var(--accent),transparent 70%);-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0)}
.pf-spot:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@media (hover:hover){
  .pf-spot:hover{translate:0 -4px;border-color:color-mix(in srgb,var(--accent) 35%,var(--line));box-shadow:0 28px 60px -34px var(--accent),var(--shadow)}
  .pf-spot:hover::before,.pf-spot:hover::after{opacity:1}
}
.pf-sheen{position:relative;overflow:hidden;isolation:isolate}
.pf-sheen::after{content:"";position:absolute;inset:0;z-index:1;pointer-events:none;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.38) 50%,transparent 70%);transform:translateX(-130%);transition:transform .75s cubic-bezier(.2,.7,.2,1)}
.pf-sheen:hover::after{transform:translateX(130%)}
.pf-step{opacity:0;translate:-12px 0;transition:opacity .5s ease var(--pf-delay,0ms),translate .55s cubic-bezier(.2,.7,.2,1) var(--pf-delay,0ms)}
.pf-link{position:relative;transform:scaleY(0);transform-origin:top;transition:transform .35s ease var(--pf-delay,0ms)}
.pf-in .pf-step{opacity:1;translate:none}
.pf-in .pf-link{transform:none}
@keyframes pf-light{0%,100%{box-shadow:0 0 0 0 transparent}35%{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),0 10px 26px -12px var(--accent)}}
.pf-in .pf-node{animation:pf-light 1.2s ease calc(var(--pf-delay,0ms) + 250ms) both}
@keyframes pf-flow{0%{transform:translateY(-3px);opacity:0}25%{opacity:1}100%{transform:translateY(16px);opacity:0}}
.pf-flow{position:absolute;left:-1.5px;top:0;width:4px;height:4px;border-radius:9999px;background:var(--accent);box-shadow:0 0 8px var(--accent);opacity:0}
.pf-in .pf-flow{animation:pf-flow 1.8s ease-in calc(var(--pf-delay,0ms) + 900ms) infinite}
@keyframes pf-drift{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(60px,-40px,0) scale(1.15)}}
@keyframes pf-drift-2{0%,100%{transform:translate3d(0,0,0) scale(1.05)}50%{transform:translate3d(-70px,45px,0) scale(.9)}}
@keyframes pf-drift-3{0%,100%{transform:translate3d(0,0,0) scale(.95)}50%{transform:translate3d(40px,60px,0) scale(1.12)}}
.pf-aurora{will-change:transform;animation:pf-drift 16s ease-in-out infinite}
.pf-aurora-2{will-change:transform;animation:pf-drift-2 21s ease-in-out infinite}
.pf-aurora-3{will-change:transform;animation:pf-drift-3 26s ease-in-out infinite}
.pf-hero-spot{opacity:0;transition:opacity .5s ease;background:radial-gradient(480px circle at var(--sx,30%) var(--sy,30%),var(--accent-soft),transparent 70%)}
.pf-hero:hover .pf-hero-spot{opacity:1}
@media (prefers-reduced-motion:reduce){
  .pf-enter,.pf-enter-scale,.pf-shimmer,.pf-aurora,.pf-aurora-2,.pf-aurora-3,.pf-in .pf-tag,.pf-in .pf-node,.pf-in .pf-flow{animation:none!important}
  .pf-reveal,.pf-step,.pf-tag{opacity:1!important;translate:none!important;scale:none!important;transition:none!important}
  .pf-draw{scale:1 1!important;transition:none!important}
  .pf-link{transform:none!important;transition:none!important}
  .pf-spot,.pf-spot:hover{translate:none!important}
  .pf-sheen::after{display:none}
}
`;

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

/** True once the element has entered the viewport (or immediately without IntersectionObserver / with reduced motion). */
function useInView(rootMargin = '0px 0px -10% 0px') {
    const ref = useRef(null);
    const [seen, setSeen] = useState(() => typeof IntersectionObserver === 'undefined' || prefersReduced());
    useEffect(() => {
        const el = ref.current;
        if (seen || !el) return undefined;
        const io = new IntersectionObserver(([e]) => {
            // Also reveal anything already scrolled past (e.g. restored scroll position).
            if (e.isIntersecting || e.boundingClientRect.bottom < 0) {
                setSeen(true);
                io.disconnect();
            }
        }, { rootMargin });
        io.observe(el);
        return () => io.disconnect();
    }, [seen, rootMargin]);
    return [ref, seen];
}

/** Scroll spy, header state and reading progress, all from one rAF-throttled passive listener. */
function useScrollState(progressRef) {
    const [active, setActive] = useState(NAV_IDS[0]);
    const [scrolled, setScrolled] = useState(false);
    const [far, setFar] = useState(false);
    useEffect(() => {
        let raf = 0;
        const update = () => {
            raf = 0;
            const y = window.scrollY;
            const max = document.documentElement.scrollHeight - window.innerHeight;
            if (progressRef.current) progressRef.current.style.transform = `scaleX(${max > 0 ? Math.min(1, y / max) : 0})`;
            const line = window.innerHeight * 0.35;
            let cur = NAV_IDS[0];
            for (const id of NAV_IDS) {
                const el = document.getElementById(id);
                if (el && el.getBoundingClientRect().top <= line) cur = id;
            }
            if (max > 0 && y >= max - 4) cur = NAV_IDS[NAV_IDS.length - 1];
            setActive(cur);
            setScrolled(y > 8);
            setFar(y > 700);
        };
        const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
        update();
        window.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('resize', onScroll, { passive: true });
        return () => {
            window.removeEventListener('scroll', onScroll);
            window.removeEventListener('resize', onScroll);
            if (raf) cancelAnimationFrame(raf);
        };
    }, [progressRef]);
    return { active, scrolled, far };
}

function Reveal({ as: Tag = 'div', delay = 0, className, style, children, ...rest }) {
    const [ref, shown] = useInView();
    return (
        <Tag ref={ref} className={cx('pf-reveal', shown && 'pf-in', className)} style={delay ? { ...style, '--pf-delay': `${delay}ms` } : style} {...rest}>
            {children}
        </Tag>
    );
}

/** Card with a cursor-following glow and hover lift (mouse only; touch gets the plain card). */
function Spot({ as: Tag = 'div', className, children, ...rest }) {
    const move = (e) => {
        if (e.pointerType !== 'mouse') return;
        const r = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`);
        e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`);
    };
    return <Tag onPointerMove={move} className={cx('pf-spot group card relative', className)} {...rest}>{children}</Tag>;
}

/** Number that counts up when it scrolls into view and eases to new values (e.g. when live data arrives). */
function CountUp({ value, decimals = 0, suffix = '', className }) {
    const target = Number(value) || 0;
    const [ref, seen] = useInView('0px');
    const [shown, setShown] = useState(() => (prefersReduced() ? target : 0));
    const from = useRef(shown);
    useEffect(() => {
        if (!seen) return undefined;
        if (prefersReduced()) {
            from.current = target;
            setShown(target);
            return undefined;
        }
        const start = performance.now();
        const a = from.current;
        let raf = 0;
        const tick = (t) => {
            const p = Math.min(1, (t - start) / 1100);
            const v = a + (target - a) * (1 - (1 - p) ** 3);
            from.current = v;
            setShown(v);
            if (p < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
        // rAF is paused in background tabs and throttled on slow devices: always land on the real value.
        const done = setTimeout(() => {
            cancelAnimationFrame(raf);
            from.current = target;
            setShown(target);
        }, 1400);
        return () => { cancelAnimationFrame(raf); clearTimeout(done); };
    }, [seen, target]);
    const fmt = (n) => n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    return (
        <span ref={ref} className={cx('tabular-nums', className)}>
            <span aria-hidden>{fmt(shown)}{suffix}</span>
            <span className="sr-only">{fmt(target)}{suffix}</span>
        </span>
    );
}

/** Typed focus line in the hero. Static list under reduced motion; screen readers always get the static list. */
function TypedRole() {
    const [reduce] = useState(prefersReduced);
    const [s, setS] = useState({ i: 0, n: 0, del: false });
    useEffect(() => {
        if (reduce) return undefined;
        const word = ROLES[s.i];
        const full = !s.del && s.n === word.length;
        const t = setTimeout(() => {
            setS(({ i, n, del }) => {
                if (!del && n === ROLES[i].length) return { i, n, del: true };
                if (del && n === 0) return { i: (i + 1) % ROLES.length, n: 0, del: false };
                return { i, n: n + (del ? -1 : 1), del };
            });
        }, full ? 1700 : s.del ? 32 : 65);
        return () => clearTimeout(t);
    }, [s, reduce]);
    return (
        <p className="mt-4 h-6 flex items-center gap-2 font-mono text-[13px] sm:text-sm text-muted whitespace-nowrap overflow-hidden">
            <span className="text-accent" aria-hidden>~/focus</span>
            <span className="text-subtle" aria-hidden>$</span>
            <span className="sr-only">Focus: {ROLES.join(', ')}</span>
            {reduce
                ? <span aria-hidden className="text-fg truncate">{ROLES.join(' · ')}</span>
                : <span aria-hidden className="text-fg">{ROLES[s.i].slice(0, s.n)}<span className="caret" /></span>}
        </p>
    );
}

function SectionHead({ n, eyebrow, title, action }) {
    return (
        <Reveal className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">
                    <span className="font-mono">{n}</span><span className="h-px w-8 bg-gradient-to-r from-accent to-transparent" /><span className="text-subtle">{eyebrow}</span>
                </div>
                <h2 className="mt-2 text-[26px] sm:text-[34px] font-bold tracking-tight leading-tight text-balance">{title}</h2>
            </div>
            {action}
        </Reveal>
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
        <a href={href} target="_blank" rel="noreferrer" className={cx('inline-flex items-center gap-1 rounded font-medium text-accent hover:underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent', className)}>
            {children} <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
        </a>
    );
}

function Pulse({ size = 'h-1.5 w-1.5' }) {
    return (
        <span className={cx('relative flex', size)}>
            <span className="absolute inline-flex h-full w-full rounded-full bg-ok opacity-60 animate-ping motion-reduce:animate-none" />
            <span className={cx('relative inline-flex rounded-full bg-ok', size)} />
        </span>
    );
}

function LiveDot({ on }) {
    if (!on) return null;
    return (
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-ok">
            <Pulse /> live
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
        <button type="button" onClick={copy} className="btn btn-secondary btn-lg" aria-label="Copy email address">
            {copied ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />} {copied ? 'Copied' : 'Copy email'}
            <span className="sr-only" aria-live="polite">{copied ? 'Email address copied' : ''}</span>
        </button>
    );
}

function ThemeToggle() {
    const { isDark, toggleTheme } = useTheme();
    const label = isDark ? 'Switch to light theme' : 'Switch to dark theme';
    return (
        <button type="button" onClick={toggleTheme} className="btn btn-ghost btn-icon shrink-0" aria-label={label} title={label}>
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
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
            <div aria-hidden className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent" />
            <div className="relative flex items-center gap-4">
                <div className="relative shrink-0">
                    <img src={`https://github.com/${GH}.png?size=160`} alt="Sai Raghava" width="64" height="64"
                        className="h-16 w-16 rounded-2xl object-cover border border-line bg-surface-2" loading="eager" />
                    <span aria-hidden className="absolute -bottom-1 -right-1 grid place-items-center h-5 w-5 rounded-full bg-surface border border-line"><Pulse /></span>
                </div>
                <div className="min-w-0">
                    <div className="font-semibold truncate">Sai Raghava</div>
                    <div className="text-sm text-muted truncate">Software Engineer · NIT Rourkela</div>
                    <div className="mt-1 inline-flex items-center gap-1.5 text-xs text-subtle"><MapPin className="h-3.5 w-3.5" /> Nellore, India</div>
                </div>
            </div>
            <dl className="relative mt-5 divide-y divide-line rounded-xl border border-line bg-surface-2/50">
                {rows.map((r) => (
                    <a key={r.k} href={r.url} target="_blank" rel="noreferrer" className="group flex items-center justify-between gap-3 px-3.5 py-2.5 hover:bg-surface-2 transition-colors first:rounded-t-xl last:rounded-b-xl focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent">
                        <dt className="text-sm text-muted flex items-center gap-2 min-w-0">{r.k} <LiveDot on={r.live} /></dt>
                        <dd className="text-sm font-semibold tabular-nums flex items-center gap-1 shrink-0">{r.v} <ArrowUpRight className="h-3.5 w-3.5 text-subtle group-hover:text-accent transition-colors" /></dd>
                    </a>
                ))}
            </dl>
            <div className="relative mt-4 rounded-xl bg-[#0b0b0e] border border-white/10 overflow-hidden">
                <div aria-hidden className="flex items-center gap-1.5 px-3.5 h-7 border-b border-white/10">
                    <span className="h-2 w-2 rounded-full bg-white/15" /><span className="h-2 w-2 rounded-full bg-white/15" /><span className="h-2 w-2 rounded-full bg-white/15" />
                    <span className="ml-2 font-mono text-[10px] text-white/40">zsh</span>
                </div>
                <div className="px-3.5 py-3 font-mono text-[12px] leading-relaxed text-white/80">
                    <div><span className="text-emerald-400">$</span> whoami</div>
                    <div className="text-white/60">backend · distributed systems · C++ · competitive programming</div>
                    <div><span className="text-emerald-400">$</span> status <span className="text-orange-300">--open-to-work</span></div>
                    <div className="text-white/60">SDE · full-time · 2027<span className="caret" /></div>
                </div>
            </div>
        </div>
    );
}

function NowStrip() {
    return (
        <div className="card p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center gap-4 lg:gap-6">
            <div className="flex items-center gap-2 shrink-0">
                <span className="inline-flex items-center gap-2 rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">
                    <Pulse /> Now
                </span>
            </div>
            <ul className="grid flex-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:gap-0 lg:divide-x lg:divide-line">
                {NOW.map((x) => (
                    <li key={x.label} className="flex items-start gap-3 min-w-0 lg:px-5 lg:first:pl-0">
                        <span className="grid place-items-center h-8 w-8 rounded-lg bg-surface-2 border border-line text-accent shrink-0"><x.icon className="h-4 w-4" /></span>
                        <span className="min-w-0">
                            <span className="block text-sm font-medium leading-snug">{x.label}</span>
                            <span className="block text-xs text-subtle">{x.sub}</span>
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

function ArchFlow() {
    const [ref, shown] = useInView('0px 0px -15% 0px');
    return (
        <div ref={ref} className={cx('rounded-2xl border border-line bg-surface-2/60 p-4 sm:p-5', shown && 'pf-in')} role="group" aria-label="Architecture: clients to API gateway to 8 microservices to Kafka to data stores">
            <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-subtle">Architecture</div>
                <span className="font-mono text-[10px] text-subtle">request path</span>
            </div>
            <ol className="mt-3">
                {FEATURED.flow.map((step, i) => (
                    <li key={step}>
                        <div className={cx('pf-step rounded-xl border px-3.5 py-2.5 text-sm font-medium flex items-center justify-between gap-3', i === 3 ? 'border-accent/50 bg-accent-soft text-fg' : 'border-line bg-surface')}
                            style={{ '--pf-delay': `${i * 140}ms` }}>
                            <span className="flex items-center gap-2.5 min-w-0">
                                <span className="font-mono text-[10px] text-accent shrink-0">{String(i + 1).padStart(2, '0')}</span>
                                <span className="truncate">{step}</span>
                            </span>
                            <span className="font-mono text-[11px] text-subtle shrink-0 hidden min-[400px]:inline">{FLOW_NOTES[i]}</span>
                        </div>
                        {i < FEATURED.flow.length - 1 && (
                            <div aria-hidden className="pf-link ml-[22px] h-3 w-px bg-gradient-to-b from-accent/70 to-line-strong" style={{ '--pf-delay': `${i * 140 + 90}ms` }} />
                        )}
                    </li>
                ))}
            </ol>
            <p className="pf-step mt-3 text-xs text-subtle" style={{ '--pf-delay': `${FEATURED.flow.length * 140}ms` }}>Saga orchestration rolls back seat holds when payment fails.</p>
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
                <Reveal className="card p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-8">
                    <div className="flex items-center gap-8 shrink-0">
                        <div><CountUp value={live.gh.public_repos} className="block text-2xl font-bold" /><div className="text-xs text-muted">public repos</div></div>
                        <div><CountUp value={live.gh.followers} className="block text-2xl font-bold" /><div className="text-xs text-muted">followers</div></div>
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
                </Reveal>
            )}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {live.repos === null
                    ? [0, 1, 2].map((i) => <div key={i} className="card h-36 animate-pulse bg-surface-2" />)
                    : repos.length
                        ? repos.map((r, i) => (
                            <Reveal key={r.id} delay={(i % 3) * 70} className="flex">
                                <Spot as="a" href={r.html_url} target="_blank" rel="noreferrer" className="p-5 flex flex-col w-full">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="flex items-center gap-2 font-semibold min-w-0"><FolderGit2 className="h-4 w-4 text-accent shrink-0" /><span className="truncate">{r.name}</span></span>
                                        <ArrowUpRight className="h-4 w-4 text-subtle group-hover:text-accent group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all shrink-0" />
                                    </div>
                                    <p className="mt-2 text-sm text-muted line-clamp-2 flex-1">{r.description || REPO_NOTES[r.name] || `${r.language || 'Code'} project.`}</p>
                                    <div className="mt-3 flex items-center gap-3 text-xs text-subtle">
                                        {r.language && <span className="font-medium text-muted">{r.language}</span>}
                                        <span className="inline-flex items-center gap-1"><Star className="h-3.5 w-3.5" /> {r.stargazers_count}</span>
                                        {r.forks_count > 0 && <span className="inline-flex items-center gap-1"><GitFork className="h-3.5 w-3.5" /> {r.forks_count}</span>}
                                        {r.homepage && <span className="text-ok font-medium">live</span>}
                                        <span className="ml-auto">{new Date(r.pushed_at).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}</span>
                                    </div>
                                </Spot>
                            </Reveal>
                        ))
                        : Object.entries(REPO_NOTES).slice(0, 6).map(([name, note], i) => (
                            <Reveal key={name} delay={(i % 3) * 70} className="flex">
                                <Spot as="a" href={`${URLS.github}/${name}`} target="_blank" rel="noreferrer" className="p-5 flex flex-col w-full">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="flex items-center gap-2 font-semibold min-w-0"><FolderGit2 className="h-4 w-4 text-accent shrink-0" /><span className="truncate">{name}</span></span>
                                        <ArrowUpRight className="h-4 w-4 text-subtle group-hover:text-accent transition-colors shrink-0" />
                                    </div>
                                    <p className="mt-2 text-sm text-muted line-clamp-2 flex-1">{note}</p>
                                </Spot>
                            </Reveal>
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
            {cards.map((c, i) => (
                <Reveal key={c.title} delay={i * 80} className="flex">
                    <Spot className="p-5 sm:p-6 flex flex-col w-full">
                        <div className="flex items-center justify-between">
                            <span className="flex items-center gap-2 font-semibold"><span className="grid place-items-center h-8 w-8 rounded-lg bg-accent-soft text-accent"><c.icon className="h-4 w-4" /></span> {c.title}</span>
                            <LiveDot on={c.live} />
                        </div>
                        <CountUp value={c.big} className="mt-5 block text-4xl sm:text-[44px] leading-none font-extrabold tracking-tight" />
                        <div className="mt-1.5 text-xs text-subtle">{c.bigLabel}</div>
                        <ul className="mt-4 space-y-1.5 text-sm text-muted flex-1">
                            {c.lines.map((l) => <li key={l} className="flex gap-2"><span aria-hidden className="mt-2 h-1 w-1 rounded-full bg-accent/60 shrink-0" />{l}</li>)}
                        </ul>
                        <div className="mt-4 pt-3 border-t border-line flex gap-4 text-sm">{c.links.map((l) => <Ext key={l.url} href={l.url}>{l.label}</Ext>)}</div>
                    </Spot>
                </Reveal>
            ))}
        </div>
    );
}

export default function Portfolio({ onUnlock, owner = false }) {
    const live = useLive();
    const taps = useRef([]);
    const progressRef = useRef(null);
    const chipNavRef = useRef(null);
    const heroRef = useRef(null);
    const { active, scrolled, far } = useScrollState(progressRef);

    useEffect(() => {
        const prev = document.title;
        document.title = 'Nandam Venkata Sai Raghava · Software Engineer';
        return () => { document.title = prev; };
    }, []);

    // Keep the active chip visible in the mobile chip nav (scrolls the strip only, never the page).
    useEffect(() => {
        const nav = chipNavRef.current;
        const chip = nav?.querySelector(`[data-id="${active}"]`);
        if (!nav || !chip || nav.scrollWidth <= nav.clientWidth) return;
        const left = chip.offsetLeft - (nav.clientWidth - chip.offsetWidth) / 2;
        nav.scrollTo({ left: Math.max(0, left), behavior: prefersReduced() ? 'auto' : 'smooth' });
    }, [active]);

    // Hidden owner entrance: three quick taps on the dot after the name. Pointer-down (not click) so it works on iOS,
    // and preventDefault on touch so quick taps neither zoom nor produce ghost clicks.
    const secretTap = (e) => {
        if (e.pointerType === 'touch') e.preventDefault();
        const now = Date.now();
        taps.current = [...taps.current.filter((t) => now - t < 1500), now];
        if (taps.current.length >= 3) {
            taps.current = [];
            onUnlock?.();
        }
    };

    // Desktop-only cursor spotlight in the hero (mouse pointers; cheap CSS variable writes).
    const heroMove = (e) => {
        if (e.pointerType !== 'mouse' || !heroRef.current) return;
        const r = heroRef.current.getBoundingClientRect();
        heroRef.current.style.setProperty('--sx', `${e.clientX - r.left}px`);
        heroRef.current.style.setProperty('--sy', `${e.clientY - r.top}px`);
    };

    const lcTotal = live.lc?.Sairaghava1318?.total;
    const solved = 325 + 437 + Math.max(900, lcTotal || 0);
    const stats = [
        { v: 8.99, d: 2, l: 'CGPA' },
        { v: solved, s: '+', l: 'problems solved' },
        { v: 2, l: 'industry roles' },
        live.gh?.public_repos ? { v: live.gh.public_repos, l: 'public repos' } : { v: 17, s: '+', l: 'public repos' },
    ];

    const sectionCls = 'scroll-mt-28 lg:scroll-mt-20 focus:outline-none';

    return (
        <div className="min-h-dvh bg-bg text-fg relative overflow-x-clip">
            <style>{PF_CSS}</style>
            <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[680px] opacity-60 [background-image:radial-gradient(var(--line-strong)_1px,transparent_1px)] [background-size:22px_22px] [mask-image:linear-gradient(to_bottom,black,transparent)]" />

            <button type="button" onClick={() => scrollTo('about')}
                className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 btn btn-primary btn-sm">
                Skip to content
            </button>

            <header style={{ touchAction: 'manipulation' }}
                className={cx('sticky top-0 z-40 border-b backdrop-blur-xl transition-colors', scrolled ? 'border-line bg-bg/80' : 'border-transparent bg-bg/40')}>
                <div className="mx-auto max-w-6xl h-14 px-4 sm:px-6 flex items-center justify-between gap-3">
                    {/* The dot sits outside the truncating button so its enlarged hit area is never clipped. */}
                    <span className="flex items-center min-w-0 font-bold tracking-tight select-none">
                        <button type="button" onClick={() => scrollTo('about')} className="truncate rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">Sai Raghava</button>
                        <span role="presentation" aria-hidden onPointerDown={secretTap}
                            className="relative z-10 inline-block shrink-0 text-accent px-0.5 select-none"
                            style={{ touchAction: 'manipulation', WebkitTapHighlightColor: 'transparent' }}>
                            .<span className="absolute -inset-x-3 -inset-y-3" />
                        </span>
                    </span>
                    <nav aria-label="Sections" className="hidden lg:flex items-center gap-0.5 text-sm">
                        {NAV.map(([id, label]) => {
                            const on = active === id;
                            return (
                                <button key={id} type="button" onClick={() => scrollTo(id)} aria-current={on ? 'true' : undefined}
                                    className={cx('relative px-3 h-8 rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent',
                                        on ? 'text-fg bg-surface-2' : 'text-muted hover:text-fg hover:bg-surface-2')}>
                                    {label}
                                    <span aria-hidden className={cx('absolute left-1/2 -bottom-[3px] h-1 w-1 -translate-x-1/2 rounded-full bg-accent transition-opacity', on ? 'opacity-100' : 'opacity-0')} />
                                </button>
                            );
                        })}
                    </nav>
                    <div className="flex items-center gap-1 shrink-0">
                        <ThemeToggle />
                        <a href={`mailto:${EMAIL}`} className="btn btn-primary btn-sm shrink-0"><Mail className="h-4 w-4" /> Hire me</a>
                    </div>
                </div>
                <nav ref={chipNavRef} aria-label="Sections" className="lg:hidden flex gap-1 overflow-x-auto no-scrollbar px-4 pb-2 -mt-1 text-[13px]">
                    {NAV.map(([id, label]) => {
                        const on = active === id;
                        return (
                            <button key={id} data-id={id} type="button" onClick={() => scrollTo(id)} aria-current={on ? 'true' : undefined}
                                className={cx('shrink-0 px-3 h-7 rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent',
                                    on ? 'border-accent/40 bg-accent-soft text-accent font-medium' : 'border-line text-muted bg-surface')}>
                                {label}
                            </button>
                        );
                    })}
                </nav>
                <div aria-hidden className="pointer-events-none absolute inset-x-0 -bottom-px h-0.5 overflow-hidden">
                    <div ref={progressRef} className="h-full origin-left bg-linear-to-r from-accent to-orange-400" style={{ transform: 'scaleX(0)' }} />
                </div>
            </header>

            <main className="relative mx-auto max-w-6xl px-4 sm:px-6 pb-20 space-y-24 sm:space-y-32">
                {/* Hero */}
                <section id="about" tabIndex={-1} ref={heroRef} onPointerMove={heroMove} aria-label="About"
                    className={cx(sectionCls, 'pf-hero relative pt-10 sm:pt-20 grid gap-10 lg:grid-cols-[1.25fr_1fr] lg:items-center')}>
                    <div aria-hidden className="pointer-events-none absolute inset-0">
                        <div className="pf-aurora absolute -top-10 -left-16 h-80 w-80 rounded-full bg-accent opacity-[0.16] blur-3xl" />
                        <div className="pf-aurora-2 absolute top-48 left-1/3 h-64 w-64 rounded-full bg-orange-400 opacity-[0.10] blur-3xl" />
                        <div className="pf-aurora-3 absolute top-4 right-0 h-72 w-72 rounded-full bg-accent opacity-[0.10] blur-3xl" />
                    </div>
                    <div aria-hidden className="pf-hero-spot pointer-events-none absolute -inset-x-6 inset-y-0 hidden lg:block rounded-4xl" />
                    <div className="relative min-w-0">
                        <div className="pf-enter inline-flex items-center gap-2 rounded-full border border-ok/30 bg-surface/80 px-3 py-1 text-xs font-medium text-muted shadow-sm">
                            <Pulse size="h-2 w-2" />
                            <span><span className="text-fg">Open to full-time SDE roles</span> · 2027</span>
                        </div>
                        <h1 className="mt-5 text-[clamp(2.25rem,10.5vw,4.25rem)] leading-[1.02] font-extrabold tracking-[-0.03em]">
                            <span className="pf-enter block" style={{ '--d': '100ms' }}>Nandam Venkata</span>
                            <span className="pf-enter block" style={{ '--d': '200ms' }}><span className="pf-shimmer">Sai Raghava</span></span>
                        </h1>
                        <div className="pf-enter" style={{ '--d': '300ms' }}><TypedRole /></div>
                        <p className="pf-enter mt-4 max-w-xl text-base sm:text-lg text-muted leading-relaxed" style={{ '--d': '400ms' }}>
                            Backend-leaning software engineer and competitive programmer at <b className="text-fg">NIT Rourkela</b>.
                            I build systems that hold up under load — event-driven microservices, a Redis-compatible cache in C++,
                            and production MERN apps shipped at <b className="text-fg">Maruti Suzuki</b>.
                        </p>
                        <div className="pf-enter mt-7 flex flex-wrap gap-2" style={{ '--d': '500ms' }}>
                            <button type="button" onClick={() => scrollTo('projects')} className="pf-sheen group btn btn-primary btn-lg shadow-[0_10px_30px_-12px_var(--accent)]">
                                View projects <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                            </button>
                            <a href={URLS.github} target="_blank" rel="noreferrer" className="btn btn-secondary btn-lg"><FolderGit2 className="h-4 w-4" /> GitHub</a>
                            <a href={URLS.linkedin} target="_blank" rel="noreferrer" className="btn btn-secondary btn-lg">LinkedIn <ArrowUpRight className="h-4 w-4" /></a>
                        </div>
                        <dl className="mt-10 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-5 max-w-xl">
                            {stats.map((s, i) => (
                                <div key={s.l} className="pf-enter flex flex-col-reverse border-l-2 border-accent/30 pl-3" style={{ '--d': `${600 + i * 90}ms` }}>
                                    <dt className="text-xs text-subtle mt-0.5">{s.l}</dt>
                                    <dd className="text-2xl sm:text-[28px] font-extrabold tracking-tight"><CountUp value={s.v} decimals={s.d} suffix={s.s} /></dd>
                                </div>
                            ))}
                        </dl>
                    </div>
                    <div className="pf-enter-scale relative" style={{ '--d': '350ms' }}><ProfileCard live={live} /></div>
                    <Reveal delay={200} className="relative lg:col-span-2"><NowStrip /></Reveal>
                </section>

                <section id="experience" tabIndex={-1} className={sectionCls}>
                    <SectionHead n="01" eyebrow="Experience" title="Where I've shipped code" />
                    <ol className="mt-10 relative ml-2 space-y-8">
                        <span aria-hidden className="absolute left-0 top-2 bottom-2 w-px bg-gradient-to-b from-accent/70 via-line-strong to-transparent" />
                        {EXPERIENCE.map((x, i) => {
                            const current = x.when.includes('Present');
                            return (
                                <Reveal as="li" key={x.org} delay={i * 60} className="pl-6 sm:pl-10 relative">
                                    <span aria-hidden className="absolute -left-[7px] top-7 flex h-3.5 w-3.5">
                                        {current && <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-40 animate-ping motion-reduce:animate-none" />}
                                        <span className={cx('relative h-3.5 w-3.5 rounded-full border-2 border-accent', current ? 'bg-accent' : 'bg-bg')} />
                                    </span>
                                    <Spot className="p-5 sm:p-7">
                                        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-1 sm:gap-4">
                                            <div className="min-w-0">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <h3 className="text-lg sm:text-xl font-semibold tracking-tight">{x.role}</h3>
                                                    {current && <span className="badge bg-ok/10 text-ok">Current</span>}
                                                </div>
                                                <div className="mt-0.5 text-sm text-accent font-medium flex items-center gap-1.5"><Briefcase className="h-3.5 w-3.5 shrink-0" /> {x.org}</div>
                                            </div>
                                            <div className="text-xs sm:text-right text-subtle shrink-0">
                                                <div className="font-medium text-muted font-mono">{x.when}</div>
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
                                            {x.points.map((p, j) => <li key={j}>{p}</li>)}
                                        </ul>
                                        <div className="mt-5 pt-4 border-t border-line flex flex-wrap items-center justify-between gap-3">
                                            <Tags items={x.tags} />
                                            {(!x.proof.ownerOnly || owner) && <Ext href={x.proof.url} className="text-sm"><BadgeCheck className="h-4 w-4" /> {x.proof.label}</Ext>}
                                        </div>
                                    </Spot>
                                </Reveal>
                            );
                        })}
                    </ol>
                </section>

                <section id="projects" tabIndex={-1} className={sectionCls}>
                    <SectionHead n="02" eyebrow="Projects" title="Things I've built" />
                    <Reveal as="article" className="mt-10 card relative overflow-hidden p-5 sm:p-8">
                        <div aria-hidden className="pointer-events-none absolute -bottom-24 -right-24 h-72 w-72 rounded-full bg-accent opacity-[0.10] blur-3xl" />
                        <div aria-hidden className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent" />
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
                                <div className="mt-6">
                                    <a href={FEATURED.code} target="_blank" rel="noreferrer" className="btn btn-secondary"><FolderGit2 className="h-4 w-4" /> View code <ArrowUpRight className="h-3.5 w-3.5" /></a>
                                </div>
                            </div>
                            <ArchFlow />
                        </div>
                    </Reveal>

                    <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {PROJECTS.map((p, i) => (
                            <Reveal key={p.name} delay={(i % 3) * 80} className="flex">
                                <Spot as="article" className="p-5 sm:p-6 flex flex-col w-full">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="grid place-items-center h-10 w-10 rounded-xl bg-accent-soft text-accent shrink-0 transition-transform group-hover:scale-105 motion-reduce:group-hover:scale-100"><p.icon className="h-5 w-5" /></div>
                                        <span className="text-xs text-subtle font-medium font-mono">{p.when}</span>
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
                                </Spot>
                            </Reveal>
                        ))}
                    </div>
                </section>

                <section id="cp" tabIndex={-1} className={sectionCls}>
                    <SectionHead n="03" eyebrow="Competitive programming" title={`${solved.toLocaleString()}+ problems across three platforms`} />
                    <div className="mt-10"><CPSection live={live} /></div>
                </section>

                <section id="github" tabIndex={-1} className={sectionCls}>
                    <SectionHead n="04" eyebrow="Open source" title="Live from GitHub" action={<Ext href={URLS.github} className="text-sm">github.com/{GH}</Ext>} />
                    <div className="mt-10"><GitHubSection live={live} /></div>
                </section>

                <section id="skills" tabIndex={-1} className={sectionCls}>
                    <SectionHead n="05" eyebrow="Toolbox" title="Skills & education" />
                    <div className="mt-10 grid gap-4 lg:grid-cols-5">
                        <Reveal className="card p-5 sm:p-7 lg:col-span-3 grid gap-6 sm:grid-cols-2 content-start">
                            {SKILLS.map((s) => (
                                <div key={s.group}>
                                    <div className="flex items-center gap-2 text-sm font-semibold">
                                        <span className="grid place-items-center h-7 w-7 rounded-lg bg-accent-soft text-accent"><s.icon className="h-3.5 w-3.5" /></span> {s.group}
                                    </div>
                                    <div className="mt-3"><Tags items={s.items} /></div>
                                </div>
                            ))}
                        </Reveal>
                        <div className="lg:col-span-2 space-y-4">
                            <Reveal delay={80} className="card p-5 sm:p-6">
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
                            </Reveal>
                            <Reveal delay={140} className="card p-5 sm:p-6">
                                <div className="flex items-center gap-2 text-sm font-semibold"><Users className="h-4 w-4 text-accent" /> OpenCode Club, NIT Rourkela</div>
                                <div className="mt-1 text-sm text-muted">Technical Team Member · Nov 2023 – Present</div>
                                <p className="mt-2 text-sm text-muted">Organizing technical events, hands-on workshops and club activities.</p>
                            </Reveal>
                        </div>
                    </div>
                </section>

                <section id="contact" tabIndex={-1} className={sectionCls}>
                    <Reveal className="card relative overflow-hidden p-7 sm:p-12 text-center">
                        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-50 [background-image:radial-gradient(var(--line-strong)_1px,transparent_1px)] [background-size:20px_20px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
                        <div aria-hidden className="pf-aurora pointer-events-none absolute -bottom-28 left-1/2 -ml-[min(20rem,50%)] h-72 w-[40rem] max-w-full rounded-full bg-accent opacity-[0.16] blur-3xl" />
                        <div className="relative">
                            <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-accent"><Radio className="h-3.5 w-3.5" /> 06 · Contact</div>
                            <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight text-balance">Let&apos;s build something.</h2>
                            <p className="mt-3 text-muted max-w-md mx-auto">Hiring for a 2027 SDE role, or want to talk systems and algorithms? My inbox is open.</p>
                            <a href={`mailto:${EMAIL}`} className="mt-6 inline-block rounded text-lg sm:text-2xl font-semibold text-accent hover:underline underline-offset-4 break-all focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent">{EMAIL}</a>
                            <div className="mt-6 flex flex-wrap justify-center gap-2">
                                <a href={`mailto:${EMAIL}`} className="btn btn-primary btn-lg shadow-[0_10px_30px_-12px_var(--accent)]"><Mail className="h-4 w-4" /> Email me</a>
                                <CopyEmail />
                            </div>
                            <div className="mt-8 flex flex-wrap justify-center gap-2">
                                {LINKS.map((l) => (
                                    <a key={l.label} href={l.url} target="_blank" rel="noreferrer"
                                        className="group inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3.5 h-9 text-sm font-medium hover:border-accent/50 hover:text-accent transition-colors max-w-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
                                        {l.label} <span className="text-subtle font-normal truncate">@{l.handle}</span> <ArrowUpRight className="h-3.5 w-3.5 shrink-0 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                                    </a>
                                ))}
                            </div>
                        </div>
                    </Reveal>
                    <footer className="mt-10 pt-6 border-t border-line flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-subtle text-center sm:text-left">
                        <span>© {new Date().getFullYear()} Nandam Venkata Sai Raghava</span>
                        <span>Built with React, Tailwind & Flask · live data from GitHub, LeetCode and Codeforces</span>
                        <button type="button" onClick={() => scrollTo('about')} className="inline-flex items-center gap-1 rounded font-medium text-muted hover:text-accent transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
                            Back to top <ArrowUp className="h-3.5 w-3.5" />
                        </button>
                    </footer>
                </section>
            </main>

            <button type="button" onClick={() => scrollTo('about')} aria-label="Back to top" tabIndex={far ? 0 : -1} aria-hidden={!far}
                className={cx('fixed right-4 z-40 bottom-[calc(1rem+env(safe-area-inset-bottom))] btn btn-secondary btn-icon h-11 w-11 rounded-full shadow-lg backdrop-blur transition-all',
                    far ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3 pointer-events-none')}>
                <ArrowUp className="h-4 w-4" />
            </button>
        </div>
    );
}
