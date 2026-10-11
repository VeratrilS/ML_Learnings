// Thin fetch wrapper: returns parsed JSON or throws an Error with the server's message.
export async function api(path, { method = 'GET', body, signal } = {}) {
    let res;
    try {
        res = await fetch(`/api${path}`, {
            method,
            signal,
            headers: body ? { 'Content-Type': 'application/json' } : undefined,
            body: body ? JSON.stringify(body) : undefined,
        });
    } catch (e) {
        if (e.name === 'AbortError') throw e;
        throw new Error('Network error. Is the backend running?');
    }
    let data = null;
    try { data = await res.json(); } catch { /* non-JSON */ }
    if (!res.ok || data?.status === 'error') {
        throw new Error(data?.message || `Request failed (${res.status})`);
    }
    return data;
}

// Reads a text/event-stream response, calling onEvent for every `data:` JSON payload.
export async function streamSSE(path, body, onEvent, signal) {
    const res = await fetch(`/api${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
    });
    if (!res.ok) {
        let msg = `Request failed (${res.status})`;
        try { msg = (await res.json()).message || msg; } catch { /* ignore */ }
        if (res.status === 413) msg = 'These pages are too large to upload. Try a smaller chunk size.';
        throw new Error(msg);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
        const { value, done } = await reader.read();
        if (value) buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
            const line = buffer.slice(0, idx).trim();
            buffer = buffer.slice(idx + 2);
            if (line.startsWith('data: ')) {
                try { onEvent(JSON.parse(line.slice(6))); } catch { /* partial */ }
            }
        }
        if (done) break;
    }
}
