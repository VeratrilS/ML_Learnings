import { useState } from 'react';
import {
    RotateCcw, CheckCircle2, Plus, Eye
} from 'lucide-react';
import { api } from '../lib/api';
import { useApi } from '../lib/hooks';
import { Button, Card, CardHeader } from '../components/ui';
import { play } from '../lib/sfx';

export default function Drillmaster() {
    const { data, loading, reload } = useApi('/drillmaster/deck');
    const [currentIndex, setCurrentIndex] = useState(0);
    const [revealed, setRevealed] = useState(false);
    const [showAddModal, setShowAddModal] = useState(false);
    const [newFront, setNewFront] = useState('');
    const [newBack, setNewBack] = useState('');
    const [newCategory, setNewCategory] = useState('Algorithms');
    const [lastReview, setLastReview] = useState(null);

    const cards = data?.due_cards || [];
    const currentCard = cards[currentIndex];

    const submitGrade = async (grade) => {
        if (!currentCard) return;
        play('jab');
        try {
            const res = await api('/drillmaster/review', {
                method: 'POST',
                body: { card_id: currentCard.id, grade },
            });
            if (res.data) {
                setLastReview(res.data);
                if (grade === 5) play('combo');
            }
            setRevealed(false);
            if (currentIndex + 1 < cards.length) {
                setCurrentIndex((i) => i + 1);
            } else {
                reload({ silent: true });
                setCurrentIndex(0);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const addCard = async () => {
        if (!newFront.trim() || !newBack.trim()) return;
        try {
            await api('/drillmaster/card', {
                method: 'POST',
                body: { front: newFront.trim(), back: newBack.trim(), category: newCategory },
            });
            setNewFront('');
            setNewBack('');
            setShowAddModal(false);
            reload({ silent: true });
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div className="space-y-6 animate-rise">
            <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                    <div className="eyebrow flex items-center gap-1.5 text-cyan-400">
                        <RotateCcw className="h-4 w-4" /> Spaced Repetition Engine
                    </div>
                    <h1 className="mt-1 text-2xl sm:text-3xl font-bold tracking-tight">
                        SuperMemo SM-2 Drillmaster
                    </h1>
                    <p className="text-sm text-muted mt-1 max-w-2xl">
                        Active recall engine implementing the mathematical SuperMemo SM-2 algorithm. Optimizes interval schedules based on cognitive recall difficulty.
                    </p>
                </div>
                <Button variant="secondary" icon={Plus} onClick={() => setShowAddModal(true)}>
                    New Card
                </Button>
            </header>

            {/* Deck Stats Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-cyan-400 tabular-nums">{data?.due_count || 0}</div>
                    <div className="text-xs text-subtle mt-0.5">Cards Due Today</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold tabular-nums">{data?.total_cards || 0}</div>
                    <div className="text-xs text-subtle mt-0.5">Total In Deck</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold text-ok tabular-nums">{data?.mastered_cards || 0}</div>
                    <div className="text-xs text-subtle mt-0.5">Mastered (&gt;14d)</div>
                </Card>
                <Card className="card-pad text-center">
                    <div className="text-2xl font-bold tabular-nums">{data?.mastery_rate || 0}%</div>
                    <div className="text-xs text-subtle mt-0.5">Retention Rate</div>
                </Card>
            </div>

            {/* Active Flashcard Review View */}
            {currentCard ? (
                <div className="space-y-4 max-w-2xl mx-auto">
                    <div className="flex items-center justify-between text-xs text-subtle font-mono">
                        <span>CARD {currentIndex + 1} OF {cards.length}</span>
                        <span className="badge text-[10px] uppercase">{currentCard.category}</span>
                        <span>EASE FACTOR: {currentCard.ease_factor}</span>
                    </div>

                    <Card
                        className="card-pad min-h-[260px] flex flex-col justify-between cursor-pointer border-cyan-500/20 bg-gradient-to-br from-surface to-cyan-500/5 hover:border-cyan-500/40 transition-all select-none"
                        onClick={() => setRevealed(!revealed)}
                    >
                        <div>
                            <span className="text-[11px] font-mono text-cyan-400 font-bold uppercase tracking-wider block mb-2">
                                Prompt / Question
                            </span>
                            <div className="text-lg sm:text-xl font-bold tracking-tight leading-relaxed">
                                {currentCard.front}
                            </div>
                        </div>

                        {revealed ? (
                            <div className="pt-4 mt-4 border-t border-line/60 animate-rise">
                                <span className="text-[11px] font-mono text-ok font-bold uppercase tracking-wider block mb-1.5">
                                    Recall Solution / Answer
                                </span>
                                <div className="text-sm sm:text-base text-fg whitespace-pre-line leading-relaxed font-normal">
                                    {currentCard.back}
                                </div>
                            </div>
                        ) : (
                            <div className="text-center pt-8 text-xs text-subtle flex items-center justify-center gap-1.5">
                                <Eye className="h-3.5 w-3.5" /> Tap card or press Space to reveal answer
                            </div>
                        )}
                    </Card>

                    {/* SM-2 Rating Buttons */}
                    {revealed ? (
                        <div className="grid grid-cols-4 gap-2 pt-2 animate-rise">
                            <button
                                onClick={() => submitGrade(0)}
                                className="btn btn-secondary flex flex-col items-center py-2.5 h-auto text-danger hover:border-danger/40 border-danger/20"
                            >
                                <span className="text-xs font-bold">Again</span>
                                <span className="text-[10px] text-subtle mt-0.5 font-mono">1 day</span>
                            </button>
                            <button
                                onClick={() => submitGrade(3)}
                                className="btn btn-secondary flex flex-col items-center py-2.5 h-auto text-amber-500 hover:border-amber-500/40 border-amber-500/20"
                            >
                                <span className="text-xs font-bold">Hard</span>
                                <span className="text-[10px] text-subtle mt-0.5 font-mono">2 days</span>
                            </button>
                            <button
                                onClick={() => submitGrade(4)}
                                className="btn btn-secondary flex flex-col items-center py-2.5 h-auto text-cyan-400 hover:border-cyan-400/40 border-cyan-400/20"
                            >
                                <span className="text-xs font-bold">Good</span>
                                <span className="text-[10px] text-subtle mt-0.5 font-mono">4 days</span>
                            </button>
                            <button
                                onClick={() => submitGrade(5)}
                                className="btn btn-secondary flex flex-col items-center py-2.5 h-auto text-ok hover:border-ok/40 border-ok/20"
                            >
                                <span className="text-xs font-bold">Easy</span>
                                <span className="text-[10px] text-subtle mt-0.5 font-mono">7+ days</span>
                            </button>
                        </div>
                    ) : (
                        <div className="flex justify-center">
                            <Button variant="primary" size="lg" icon={Eye} onClick={() => setRevealed(true)} className="px-10 shadow-md">
                                Reveal Solution
                            </Button>
                        </div>
                    )}
                </div>
            ) : (
                <Card className="card-pad text-center py-12 space-y-3">
                    <CheckCircle2 className="h-10 w-10 text-ok mx-auto" />
                    <h2 className="text-xl font-bold tracking-tight">All Due Cards Mastered!</h2>
                    <p className="text-xs text-muted max-w-sm mx-auto">
                        Your memory retention is optimal according to the SM-2 decay curve. Fresh review intervals will appear tomorrow.
                    </p>
                    <div className="pt-2">
                        <Button variant="secondary" icon={Plus} onClick={() => setShowAddModal(true)}>
                            Add Custom Card
                        </Button>
                    </div>
                </Card>
            )}

            {/* Add Card Modal */}
            {showAddModal && (
                <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm p-4">
                    <Card className="card-pad w-full max-w-md space-y-4 animate-rise">
                        <CardHeader
                            title="Create Drillmaster Card"
                            subtitle="Add concept to SM-2 active recall queue"
                            icon={Plus}
                        />

                        <div>
                            <label className="text-xs font-bold text-subtle uppercase block mb-1">Category</label>
                            <input
                                type="text"
                                value={newCategory}
                                onChange={(e) => setNewCategory(e.target.value)}
                                className="input text-sm"
                            />
                        </div>

                        <div>
                            <label className="text-xs font-bold text-subtle uppercase block mb-1">Front (Prompt / Question)</label>
                            <textarea
                                value={newFront}
                                onChange={(e) => setNewFront(e.target.value)}
                                placeholder="e.g. When does a cache stampede occur and how to prevent it?"
                                rows={3}
                                className="input text-sm resize-none"
                            />
                        </div>

                        <div>
                            <label className="text-xs font-bold text-subtle uppercase block mb-1">Back (Solution / Answer)</label>
                            <textarea
                                value={newBack}
                                onChange={(e) => setNewBack(e.target.value)}
                                placeholder="e.g. Occurs when high-traffic cache key expires simultaneously..."
                                rows={4}
                                className="input text-sm resize-none"
                            />
                        </div>

                        <div className="flex justify-end gap-2 pt-2">
                            <Button variant="ghost" onClick={() => setShowAddModal(false)}>Cancel</Button>
                            <Button variant="primary" icon={Plus} onClick={addCard}>Save Card</Button>
                        </div>
                    </Card>
                </div>
            )}
        </div>
    );
}
