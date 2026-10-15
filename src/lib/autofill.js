// Autofill bookmarklet for job application forms (Greenhouse, Lever, Ashby, and generic forms).
// It fills standard fields from Sai's profile, outlines what it filled (green) and what still needs him
// (orange: resume upload, required custom questions), and NEVER submits — Sai reviews and clicks Submit.

/** Normalises a JobRadarProfile-like object into the fields the filler understands. */
export function autofillProfile(p = {}) {
    const full = (p.full_name || p.fullName || '').trim();
    const parts = full.split(/\s+/);
    return {
        fullName: full,
        firstName: p.first_name || parts.slice(0, -1).join(' ') || full,
        lastName: p.last_name || (parts.length > 1 ? parts[parts.length - 1] : ''),
        email: p.email || '',
        phone: p.phone || '',
        linkedin: p.linkedin || '',
        github: p.github || '',
        leetcode: p.leetcode || '',
        codeforces: p.codeforces || '',
        portfolio: p.portfolio || (typeof window !== 'undefined' ? window.location.origin : ''),
        college: p.college || '',
        degree: p.degree || '',
        gradYear: String(p.grad_year || p.gradYear || ''),
        cgpa: p.cgpa != null ? String(p.cgpa) : '',
        location: p.location || (p.location_pref || '').split(',')[0].trim(),
        resumeUrl: p.resume_url || p.resumeUrl || '',
        resumeName: p.resume_name || p.resumeName || 'Resume.pdf',
    };
}

// The filler runs on the job site, so it must be self-contained (no imports, no closures over this module).
function filler(P) {
    const RULES = [
        [/first\s*name|given\s*name|_systemfield_first|^first$/i, 'firstName'],
        [/last\s*name|surname|family\s*name|^last$/i, 'lastName'],
        [/^(full\s*)?name$|your name|_systemfield_name|legal name|candidate name/i, 'fullName'],
        [/e-?mail/i, 'email'],
        [/phone|mobile|contact number/i, 'phone'],
        [/linked\s*in/i, 'linkedin'],
        [/git\s*hub/i, 'github'],
        [/leet\s*code/i, 'leetcode'],
        [/codeforces/i, 'codeforces'],
        [/portfolio|personal (web)?site|website|other (link|url)/i, 'portfolio'],
        [/school|university|college|institution/i, 'college'],
        [/degree|qualification|major|discipline/i, 'degree'],
        [/grad(uation)?\s*(year|date)|year of (graduation|passing)|class of|batch/i, 'gradYear'],
        [/cgpa|\bgpa\b|grade point/i, 'cgpa'],
        [/current (location|city)|^location|city|where are you (based|located)/i, 'location'],
    ];
    const YES = /authori[sz]ed to work in india|eligible to work in india|legally (allowed|authori[sz]ed) to work.*india|willing to relocate|open to relocat/i;
    const NO = /require.*sponsor|need.*sponsor|visa sponsorship/i;

    const labelOf = (el) => {
        const bits = [];
        if (el.id) {
            const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (l) bits.push(l.textContent);
        }
        const wrap = el.closest('label, .field, .application-question, .form-group, [class*="question"], [class*="Field"], fieldset, li, div');
        if (wrap) {
            const l = wrap.querySelector('label, legend, .application-label, [class*="label"]');
            if (l && l !== el) bits.push(l.textContent);
        }
        bits.push(el.getAttribute('aria-label') || '', el.placeholder || '', el.name || '', el.id || '');
        return bits.join(' ').replace(/\s+/g, ' ').trim();
    };
    const setVal = (el, v) => {
        const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        if (desc && desc.set) desc.set.call(el, v); else el.value = v;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
    };
    const mark = (el, color) => { el.style.outline = `2px solid ${color}`; el.style.outlineOffset = '2px'; };

    let filled = 0;
    const todo = [];
    const resumeJobs = [];
    const inputs = [...document.querySelectorAll('input, textarea, select')].filter((el) => {
        const t = (el.type || '').toLowerCase();
        return !el.disabled && el.offsetParent !== null && !['hidden', 'submit', 'button', 'reset', 'image'].includes(t);
    });

    for (const el of inputs) {
        const t = (el.type || '').toLowerCase();
        const label = labelOf(el);
        if (t === 'file') {
            const isResume = /resume|cv|curriculum/i.test(label) || inputs.filter((x) => x.type === 'file').length === 1;
            if (isResume && P.resumeUrl && !(el.files && el.files.length)) {
                resumeJobs.push(fetch(P.resumeUrl).then((r) => {
                    if (!r.ok) throw new Error(`resume ${r.status}`);
                    return r.blob();
                }).then((blob) => {
                    const dt = new DataTransfer();
                    dt.items.add(new File([blob], P.resumeName, { type: 'application/pdf' }));
                    el.files = dt.files;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    mark(el, '#16a34a');
                    filled++;
                }).catch(() => { mark(el, '#f59e0b'); todo.push('Upload your resume (automatic attach failed)'); }));
            } else {
                mark(el, '#f59e0b');
                todo.push(`Upload: ${label.slice(0, 50) || 'resume'}`);
            }
            continue;
        }
        if (t === 'radio' || t === 'checkbox') {
            const group = (el.closest('fieldset, [role="radiogroup"], .application-question, div') || el.parentElement);
            const q = group ? group.textContent : label;
            const optText = (labelOf(el) + ' ' + el.value).toLowerCase();
            if (YES.test(q) && /\byes\b/.test(optText) && !el.checked) { el.click(); mark(el, '#16a34a'); filled++; }
            if (NO.test(q) && /\bno\b/.test(optText) && !el.checked) { el.click(); mark(el, '#16a34a'); filled++; }
            continue;
        }
        if (el.tagName === 'SELECT') {
            if (el.required && !el.value) { mark(el, '#f59e0b'); todo.push(label.slice(0, 50) || 'a dropdown'); }
            continue;
        }
        if (el.value && el.value.trim()) continue; // never overwrite what's already there
        let key = null;
        if (t === 'email') key = 'email';
        else if (t === 'tel') key = 'phone';
        else for (const [re, k] of RULES) { if (re.test(label)) { key = k; break; } }
        if (key && P[key]) { setVal(el, P[key]); mark(el, '#16a34a'); filled++; }
        else if (el.required || el.getAttribute('aria-required') === 'true') { mark(el, '#f59e0b'); todo.push(label.slice(0, 50) || 'a required field'); }
    }

    Promise.allSettled(resumeJobs).then(() => showBox());
    function showBox() {
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed;z-index:2147483647;right:16px;bottom:16px;max-width:340px;background:#111827;color:#fff;'
        + 'font:14px/1.45 system-ui,sans-serif;padding:14px 16px;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.35)';
    const list = todo.slice(0, 8).map((x) => `<li>${x.replace(/</g, '&lt;')}</li>`).join('');
    box.innerHTML = `<b>Autofill: ${filled} field${filled === 1 ? '' : 's'} filled</b>`
        + (todo.length ? `<div style="margin-top:6px;color:#fcd34d">Still for you (orange):</div><ul style="margin:4px 0 0 16px;padding:0">${list}</ul>` : '')
        + '<div style="margin-top:8px;color:#d1d5db">Check everything, then press Submit yourself.</div>'
        + '<button style="margin-top:10px;background:#f97316;color:#fff;border:0;border-radius:8px;padding:6px 12px;font-weight:600;cursor:pointer">OK</button>';
    box.querySelector('button').onclick = () => box.remove();
    document.body.appendChild(box);
    }
}

/** A javascript: URL that runs the filler with this profile baked in (drag it to the bookmarks bar). */
export function buildBookmarklet(profile) {
    const P = JSON.stringify(autofillProfile(profile));
    const code = `(${filler.toString()})(${P});void 0;`;
    return `javascript:${encodeURIComponent(code)}`;
}

/** Same code as plain text, for "copy and paste into the console" on phones / locked-down browsers. */
export function autofillSnippet(profile) {
    return `(${filler.toString()})(${JSON.stringify(autofillProfile(profile))});`;
}
