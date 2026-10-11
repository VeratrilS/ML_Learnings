import { useEffect, useRef, useState } from 'react';
import { Send, Square, Lightbulb, ClipboardCheck, GraduationCap, RotateCcw, CheckCircle2, XCircle } from 'lucide-react';
import { api, streamSSE } from '../lib/api';
import { Button, Empty, cx } from './ui';
import Markdown from './Markdown';

const CHIPS = [
    { label: "I'm stuck, give me a hint", text: "I'm stuck. Can I get a hint?", hint: true },
    { label: 'Where do I start?', text: "I don't know where to start. What should I think about first?" },
    { label: 'Is my complexity optimal?', text: 'Is the complexity of my idea optimal? What should I aim for?' },
    { label: 'Edge cases?', text: 'Which edge cases should I be careful about?' },
];

function Flag({ ok, children }) {
    const Icon = ok ? CheckCircle2 : XCircle;
    return (
        <span className={cx('badge', ok ? 'bg-ok/10 text-ok' : 'bg-danger/10 text-danger')}>
            <Icon className="h-3 w-3" /> {children}
        </span>
    );
}

function AssessCard({ a }) {
    return (
        <div className="rounded-xl border border-line bg-surface-2/60 p-3 mb-2 space-y-2">
            <div className="flex flex-wrap gap-1.5">
                <Flag ok={a.idea_correct}>{a.idea_correct ? 'Idea works' : 'Idea has a gap'}</Flag>
                <Flag ok={a.complexity_ok}>{a.complexity_ok ? 'Optimal complexity' : 'Not optimal yet'}</Flag>
                {a.hint_level > 0 && <span className="badge bg-accent-soft text-accent">Hint level {a.hint_level}</span>}
            </div>
            {a.missing_insight && <p className="text-[13px] text-muted">{a.missing_insight}</p>}
        </div>
    );
}

export default function TutorPanel({ logId }) {
    const [messages, setMessages] = useState([]); // {role: 'user'|'tutor', text, assess?, error?}
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState(null); // 'chat' | 'assess' | null
    const [hintLevel, setHintLevel] = useState(0);
    const abortRef = useRef(null);
    const endRef = useRef(null);

    useEffect(() => () => abortRef.current?.abort(), []);
    useEffect(() => { endRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, [messages]);

    const history = (list) => list.filter((m) => !m.error && m.text).map(({ role, text }) => ({ role, text }));

    const send = async (text, { hint = false, base = messages } = {}) => {
        const msg = text.trim();
        if (!msg || busy) return;
        const level = hint ? Math.min(3, hintLevel + 1) : hintLevel;
        if (hint) setHintLevel(level);
        const next = [...base, { role: 'user', text: msg }];
        setMessages([...next, { role: 'tutor', text: '', streaming: true }]);
        setInput('');
        setBusy('chat');
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        const patch = (fn) => setMessages((ms) => {
            const copy = ms.slice();
            copy[copy.length - 1] = fn(copy[copy.length - 1]);
            return copy;
        });
        try {
            await streamSSE(`/tutor/${logId}/chat`, { messages: history(next), hint_level: level }, (ev) => {
                if (ev.type === 'delta') patch((m) => ({ ...m, text: m.text + ev.text }));
                else if (ev.type === 'done') patch((m) => ({ ...m, text: ev.text, streaming: false }));
                else if (ev.type === 'error') patch((m) => ({ ...m, text: '', error: ev.message, streaming: false }));
            }, ctrl.signal);
            patch((m) => (m.streaming ? { ...m, streaming: false } : m));
        } catch (e) {
            if (e.name === 'AbortError') patch((m) => ({ ...m, streaming: false, text: m.text || '_(stopped)_' }));
            else patch((m) => ({ ...m, text: '', error: e.message, streaming: false }));
        } finally {
            setBusy(null);
            abortRef.current = null;
        }
    };

    const assess = async () => {
        const approach = input.trim();
        if (!approach || busy) return;
        setMessages((ms) => [...ms, { role: 'user', text: `My approach: ${approach}` }]);
        setInput('');
        setBusy('assess');
        try {
            const { data } = await api(`/tutor/${logId}/assess`, { method: 'POST', body: { approach } });
            setHintLevel((h) => Math.max(h, Math.min(data.hint_level, h + 1)));
            setMessages((ms) => [...ms, { role: 'tutor', text: data.next_question || 'Looks good. Try coding it up!', assess: data }]);
        } catch (e) {
            setMessages((ms) => [...ms, { role: 'tutor', text: '', error: e.message }]);
        } finally {
            setBusy(null);
        }
    };

    const onKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send(input);
        }
    };

    return (
        <div className="mt-5">
            <div className="rounded-2xl border border-line bg-surface-2/40 p-3 sm:p-4 min-h-[240px] max-h-[55dvh] overflow-y-auto">
                {!messages.length ? (
                    <Empty icon={GraduationCap} title="Think it through with a tutor">
                        Describe your idea or ask a question. The tutor asks guiding questions and only hints when you ask. It never writes the code for you.
                    </Empty>
                ) : (
                    <div className="space-y-3">
                        {messages.map((m, i) => (
                            <div key={i} className={cx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                                {m.role === 'user' ? (
                                    <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent text-accent-fg px-3.5 py-2 text-[14px] leading-relaxed whitespace-pre-wrap">{m.text}</div>
                                ) : (
                                    <div className="max-w-[92%] rounded-2xl rounded-bl-md bg-surface border border-line px-3.5 py-2.5 text-[14px]">
                                        {m.assess && <AssessCard a={m.assess} />}
                                        {m.error ? (
                                            <div className="flex items-center gap-2 text-sm text-danger">
                                                <span>{m.error}</span>
                                                {i === messages.length - 1 && i > 0 && messages[i - 1].role === 'user' && !busy && (
                                                    <button className="btn btn-ghost btn-sm h-7" onClick={() => send(messages[i - 1].text, { base: messages.slice(0, i - 1) })}>
                                                        <RotateCcw className="h-3.5 w-3.5" /> Retry
                                                    </button>
                                                )}
                                            </div>
                                        ) : m.streaming && !m.text ? (
                                            <span className="text-sm text-subtle animate-pulse">Thinking…</span>
                                        ) : (
                                            <Markdown streaming={m.streaming}>{m.text}</Markdown>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                        {busy === 'assess' && <p className="text-sm text-subtle animate-pulse">Checking your approach…</p>}
                        <div ref={endRef} />
                    </div>
                )}
            </div>

            <div className="flex flex-wrap gap-1.5 mt-3">
                {CHIPS.map((c) => (
                    <button key={c.label} type="button" className="chip" disabled={!!busy} onClick={() => send(c.text, { hint: c.hint })}>
                        {c.hint && <Lightbulb className="h-3 w-3" />}{c.label}
                    </button>
                ))}
            </div>

            <div className="mt-3 rounded-2xl border border-line bg-surface p-2 focus-within:border-accent/60 transition-colors">
                <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={onKeyDown}
                    rows={3}
                    maxLength={2000}
                    placeholder="Explain your idea, or ask a question… (Enter to send, Shift+Enter for a new line)"
                    className="w-full resize-none bg-transparent px-2 py-1.5 text-[14px] outline-none placeholder:text-subtle"
                />
                <div className="flex items-center justify-between gap-2 px-1">
                    <span className="text-[11px] text-subtle">{hintLevel ? `Hints used: ${hintLevel}/3` : 'No hints used'}</span>
                    <div className="flex gap-1.5">
                        <Button size="sm" variant="secondary" icon={ClipboardCheck} loading={busy === 'assess'} disabled={!input.trim() || !!busy} onClick={assess}>
                            Check approach
                        </Button>
                        {busy === 'chat' ? (
                            <Button size="sm" variant="secondary" icon={Square} onClick={() => abortRef.current?.abort()}>Stop</Button>
                        ) : (
                            <Button size="sm" variant="primary" icon={Send} disabled={!input.trim() || !!busy} onClick={() => send(input)}>Send</Button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
