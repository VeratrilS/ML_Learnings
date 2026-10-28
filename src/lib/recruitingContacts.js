// Public recruiting contacts, researched 2026-10-17. Only addresses a company published (or that appear in a cited
// source, marked unconfirmed): never guessed name@company addresses. Most companies publish no email; for those the
// LinkedIn recruiter search and the careers page are the routes.

import RESEARCHED from '../data/recruitingContacts.json';

const PORTFOLIO = 'https://productivity-automations.vercel.app';
const GITHUB = 'https://github.com/VeratrilS';
const LINKEDIN = 'https://www.linkedin.com/in/nandam-venkata-sai-raghava-946b3735b/';

export const RECRUITING_CONTACTS = {
    barclays: {
        emails: [{
            address: 'campusrecruitmentmailbox-india@barclays.com',
            label: 'Campus recruitment, India',
            source: 'https://sirc-icai.org/vacancy/2024/Recritment%20Notice_ver%203.0_240424120000.pdf',
            trust: 'Published by Barclays in a 2024 campus notice (used for a training programme)',
        }],
    },
    'hevo data': {
        emails: [{
            address: 'careers@hevodata.com',
            label: 'Careers',
            source: 'https://hevodata.com/careers/',
            trust: "On Hevo's own careers page",
        }],
    },
    razorpay: {
        emails: [{
            address: 'jobs@razorpay.com',
            label: 'Jobs',
            source: 'https://anymailfinder.com/directory/razorpay.com/people/shashank-kumar',
            trust: 'Unconfirmed: third-party directory only',
            unconfirmed: true,
        }],
    },
    'goldman sachs': { campus: 'https://higher.gs.com/' },
    'texas instruments': { campus: 'https://www.ti.com/students' },
    point72: { campus: 'https://job-boards.greenhouse.io/point72' },
    databricks: { campus: 'https://www.databricks.com/company/careers' },
    imc: { campus: 'https://www.imc.com/ap/careers' },
    hackerrank: { note: 'Genuine HackerRank recruiters write from @hackerrank.com.' },
};

const key = (company) => String(company || '').trim().toLowerCase();

/** Researched entry (54 companies, every link checked) merged with the hand-written one above. Emails are de-duplicated
 *  by address, the researched entry wins (it carries the "unconfirmed" / "questions only" flags). */
export function contactsFor(company) {
    const k = key(company);
    const found = RESEARCHED[k] || {};
    const manual = RECRUITING_CONTACTS[k] || {};
    const emails = [...(found.emails || []), ...(manual.emails || [])]
        .filter((e, i, all) => all.findIndex((x) => x.address.toLowerCase() === e.address.toLowerCase()) === i);
    return {
        ...manual,
        ...found,
        emails: emails.length ? emails : undefined,
        campus: manual.campus || found.campus,
        note: manual.note,
    };
}

export function linkedinRecruiterSearch(company) {
    const q = `${company} university recruiter India`;
    return `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(q)}`;
}

/** Short, factual cold email (only true resume facts). */
export function coldEmail(company, role) {
    const what = role ? `the ${role} role` : 'software engineering roles';
    const subject = `${role || 'Software Engineer'} at ${company}: Nandam Venkata Sai Raghava, NIT Rourkela 2027`;
    const body = [
        'Hi,',
        '',
        `I'm a final-year B.Tech CSE student at NIT Rourkela (CGPA 8.99, graduating 2027) and I'm very interested in ${what} at ${company}.`,
        '',
        'A few things I have built:',
        '- SR-CarRentals, a car rental and shared-ride backend: 8 microservices over 14 Kafka topics, 3-layer concurrency control against double-booking (Redis locks, row locks, exclusion constraints) and Saga rollbacks.',
        '- A redis-cli-compatible cache server in C++17 (RESP, 29 commands, LRU/LFU eviction, thread pool).',
        '- Software Engineering Intern at Maruti Suzuki (MERN portal, 120+ REST APIs); Coding Expert at DataAnnotation (C++ fixes in llama.cpp).',
        '- Codeforces Specialist, LeetCode contest rating 1750.',
        '',
        `If my profile fits, I'd be grateful for a chance to interview, or a pointer to the right person. Happy to share my resume.`,
        '',
        'Thanks,',
        'Nandam Venkata Sai Raghava',
        `+91 9110307856 · Portfolio: ${PORTFOLIO}`,
        `LinkedIn: ${LINKEDIN} · GitHub: ${GITHUB}`,
    ].join('\n');
    return { subject, body };
}

/** Opens Sai's Gmail compose window with the draft filled in; he reviews and sends it himself. */
export function gmailDraftUrl(to, company, role) {
    const { subject, body } = coldEmail(company, role);
    const p = new URLSearchParams({ view: 'cm', fs: '1', to, su: subject, body });
    return `https://mail.google.com/mail/?${p.toString()}`;
}

/** A LinkedIn connection note fits in 300 characters. */
export function linkedinNote(company) {
    return `Hi! I'm a final-year CSE student at NIT Rourkela (CGPA 8.99, 2027). I built a Kafka/Redis microservices backend `
        + `and a Redis-compatible cache in C++. I'd love to be considered for SWE roles at ${company}. Portfolio: ${PORTFOLIO}`;
}
