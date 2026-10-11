// Client-side PDF helpers built on pdfjs-dist, loaded lazily so the library stays out of the main bundle.
// Uses the legacy build: the modern one relies on very new JS (Map#getOrInsertComputed, Math.sumPrecise)
// that Safari and older Chromium don't ship yet.

let pdfjsPromise = null;

export function loadPdfjs() {
    if (!pdfjsPromise) {
        pdfjsPromise = Promise.all([
            import('pdfjs-dist/legacy/build/pdf.mjs'),
            import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'),
        ]).then(([pdfjs, worker]) => {
            pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
            return pdfjs;
        }).catch((e) => {
            pdfjsPromise = null;
            throw e;
        });
    }
    return pdfjsPromise;
}

// Returns the pdf.js loading task; await `task.promise` for the document, call `task.destroy()` to cancel.
export async function openPdf(source, onProgress) {
    const pdfjs = await loadPdfjs();
    const cdn = pdfjs.version ? `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/` : null;
    const task = pdfjs.getDocument({
        ...source,
        ...(cdn && {
            cMapUrl: `${cdn}cmaps/`,
            cMapPacked: true,
            standardFontDataUrl: `${cdn}standard_fonts/`,
            wasmUrl: `${cdn}wasm/`,
            iccUrl: `${cdn}iccs/`,
        }),
    });
    if (onProgress) {
        task.onProgress = ({ loaded, total }) => total && onProgress(Math.min(loaded / total, 1));
    }
    return task;
}

const textCache = new WeakMap();

async function pageText(doc, n) {
    let pages = textCache.get(doc);
    if (!pages) textCache.set(doc, (pages = new Map()));
    if (!pages.has(n)) {
        const page = await doc.getPage(n);
        const content = await page.getTextContent();
        let s = '';
        for (const item of content.items) {
            if (typeof item.str !== 'string') continue;
            s += item.str + (item.hasEOL ? '\n' : ' ');
        }
        pages.set(n, s.replace(/[ \t ]+/g, ' ').replace(/ ?\n ?/g, '\n').replace(/\n{3,}/g, '\n\n').trim());
    }
    return pages.get(n);
}

// Extracted text for pages from..to (1-based, inclusive), with page markers.
export async function extractText(doc, from, to) {
    const parts = [];
    for (let n = from; n <= to; n++) {
        const t = await pageText(doc, n);
        parts.push(`--- Page ${n} ---\n${t || '(no extractable text)'}`);
    }
    return parts.join('\n\n');
}

async function renderPage(doc, n, maxWidth, quality) {
    const page = await doc.getPage(n);
    const base = page.getViewport({ scale: 1 });
    const scale = Math.min(maxWidth / base.width, (maxWidth * 1.6) / base.height, 3);
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.floor(viewport.width));
    canvas.height = Math.max(1, Math.floor(viewport.height));
    try {
        await page.render({ canvas, viewport }).promise;
        return canvas.toDataURL('image/jpeg', quality);
    } finally {
        canvas.width = 0;
        canvas.height = 0;
        page.cleanup();
    }
}

const PASSES = [
    { width: 1100, quality: 0.7 },
    { width: 950, quality: 0.6 },
    { width: 800, quality: 0.5 },
    { width: 640, quality: 0.45 },
];

// Renders pages to JPEG data URLs whose combined length stays under `budget` characters,
// re-encoding at smaller sizes when needed. onProgress({ done, total, pass }).
export async function renderPagesForUpload(doc, from, to, { budget = 3_300_000, onProgress, signal } = {}) {
    const total = to - from + 1;
    for (let pass = 0; pass < PASSES.length; pass++) {
        const { width, quality } = PASSES[pass];
        const last = pass === PASSES.length - 1;
        const images = [];
        let size = 0;
        for (let n = from; n <= to; n++) {
            signal?.throwIfAborted();
            onProgress?.({ done: n - from, total, pass });
            const url = await renderPage(doc, n, width, quality);
            images.push(url);
            size += url.length;
            if (size > budget && !last) break;
        }
        signal?.throwIfAborted();
        if (size <= budget) {
            onProgress?.({ done: total, total, pass });
            return images;
        }
        if (last) {
            while (images.length > 1 && size > budget) size -= images.pop().length;
            return images;
        }
    }
    return [];
}
