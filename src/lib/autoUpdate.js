// Installed PWAs stay alive in the background and keep running the old bundle after a deploy.
// When the app comes back to the foreground (and every 10 minutes while open), compare the deployed
// entry script with the one we are running and reload if a newer build is live.
const CHECK_EVERY_MS = 10 * 60 * 1000;
const MIN_GAP_MS = 30 * 1000;

const entryOf = (html) => (html.match(/\/assets\/index-[\w-]+\.js/) || [])[0] || null;

export function startAutoUpdate() {
    if (!import.meta.env.PROD) return;
    const current = entryOf(
        [...document.querySelectorAll('script[type="module"][src]')].map((s) => new URL(s.src).pathname).join(' '),
    );
    if (!current) return;

    let last = 0;
    const check = async () => {
        if (Date.now() - last < MIN_GAP_MS) return;
        last = Date.now();
        try {
            const res = await fetch(`/?v=${Date.now()}`, { cache: 'no-store' });
            const live = entryOf(await res.text());
            // Don't interrupt someone typing; the next foreground check will pick it up.
            const typing = /input|textarea|select/i.test(document.activeElement?.tagName || '');
            if (live && live !== current && !typing) window.location.reload();
        } catch { /* offline: try again next time */ }
    };

    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') check(); });
    window.addEventListener('focus', check);
    setInterval(check, CHECK_EVERY_MS);
}
