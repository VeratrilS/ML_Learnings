import React, { useState, useRef, useEffect } from 'react';
import { useTheme } from '../themes/ThemeContext';

function QuizComponent({ explanation, isDark, factory }) {
    const [quizData, setQuizData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [answers, setAnswers] = useState({});
    const [showResults, setShowResults] = useState(false);

    const generateQuiz = async () => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch('/api/pdf/quiz', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: explanation })
            });
            const data = await res.json();
            if (data.status === 'success') {
                setQuizData(data.data);
            } else {
                setError(data.message || 'Error generating quiz');
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleSelect = (qIndex, optIndex) => {
        if (showResults) return;
        setAnswers(prev => ({ ...prev, [qIndex]: optIndex }));
    };

    const checkAnswers = () => {
        setShowResults(true);
    };

    if (!quizData && !loading && !error) {
        return (
            <button 
                onClick={generateQuiz}
                className={`mt-4 px-3 py-1.5 text-sm font-medium rounded-md shadow-sm bg-indigo-100 text-indigo-700 hover:bg-indigo-200 transition-colors`}
            >
                Generate Quiz for this Section
            </button>
        );
    }

    if (loading) {
        return (
            <div className="mt-4 flex items-center text-sm text-indigo-500">
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Generating Quiz...
            </div>
        );
    }

    if (error) {
        return <div className="mt-4 text-sm text-red-500">Error: {error}</div>;
    }

    return (
        <div className={`mt-6 p-4 rounded-lg border ${isDark ? 'bg-slate-900 border-slate-700' : 'bg-slate-50 border-slate-200'}`}>
            <h3 className={`font-bold mb-4 ${factory.getHeading()}`}>Test Your Knowledge</h3>
            <div className="space-y-6">
                {quizData.questions.map((q, qIndex) => (
                    <div key={qIndex} className="space-y-2">
                        <p className={`font-medium text-sm ${factory.getText()}`}>{qIndex + 1}. {q.question}</p>
                        <div className="space-y-2">
                            {q.options.map((opt, optIndex) => {
                                const isSelected = answers[qIndex] === optIndex;
                                const isCorrect = q.correct_answer === optIndex;
                                
                                let btnClass = isDark ? 'bg-slate-800 border-slate-600 text-slate-300 hover:bg-slate-700' : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50';
                                
                                if (showResults) {
                                    if (isCorrect) {
                                        btnClass = 'bg-emerald-100 border-emerald-500 text-emerald-800';
                                    } else if (isSelected && !isCorrect) {
                                        btnClass = 'bg-red-100 border-red-500 text-red-800';
                                    }
                                } else if (isSelected) {
                                    btnClass = 'bg-indigo-100 border-indigo-500 text-indigo-800';
                                }

                                return (
                                    <button
                                        key={optIndex}
                                        onClick={() => handleSelect(qIndex, optIndex)}
                                        className={`w-full text-left px-4 py-2 text-sm border rounded-md transition-colors ${btnClass}`}
                                    >
                                        {opt}
                                    </button>
                                );
                            })}
                        </div>
                        {showResults && (
                            <p className={`text-xs mt-2 ${factory.getText()} opacity-80 italic`}>
                                Explanation: {q.explanation}
                            </p>
                        )}
                    </div>
                ))}
            </div>
            
            {!showResults && (
                <button 
                    onClick={checkAnswers}
                    disabled={Object.keys(answers).length < quizData.questions.length}
                    className="mt-6 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded hover:bg-indigo-700 disabled:bg-indigo-400"
                >
                    Submit Answers
                </button>
            )}
        </div>
    );
}

export default function PDFAnalyzer() {
    const { factory, isDark } = useTheme();
    const [file, setFile] = useState(null);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [results, setResults] = useState([]);
    const [error, setError] = useState('');
    
    // Auto-scroll to bottom of results
    const resultsEndRef = useRef(null);
    useEffect(() => {
        resultsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [results]);

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            setFile(e.target.files[0]);
            setError('');
            setResults([]);
        }
    };

    const startAnalysis = async () => {
        if (!file) {
            setError('Please select a PDF file first.');
            return;
        }
        
        setIsAnalyzing(true);
        setResults([]);
        setError('');
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch('/api/pdf/explain', {
                method: 'POST',
                body: formData,
            });
            
            if (!response.ok) {
                const errData = await response.json();
                setError(errData.message || 'Error uploading file.');
                setIsAnalyzing(false);
                return;
            }
            
            // Handle SSE response
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            
            let done = false;
            while (!done) {
                const { value, done: readerDone } = await reader.read();
                done = readerDone;
                if (value) {
                    const chunkStr = decoder.decode(value, { stream: true });
                    // SSE messages are separated by \n\n and prefixed with "data: "
                    const lines = chunkStr.split('\n\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.substring(6);
                            try {
                                const data = JSON.parse(dataStr);
                                setResults(prev => [...prev, data]);
                            } catch (e) {
                                console.error('Error parsing SSE data:', e, dataStr);
                            }
                        }
                    }
                }
            }
        } catch (err) {
            setError(err.message || 'Network error occurred.');
        } finally {
            setIsAnalyzing(false);
        }
    };

    return (
        <section className={`p-6 rounded-xl shadow-sm border ${factory.getCardBackground()} ${factory.getCardBorder()}`}>
            <h2 className={`text-2xl font-bold ${factory.getHeading()} mb-4`}>📄 PDF AI Analyzer</h2>
            <p className={`text-sm ${factory.getText()} mb-6`}>
                Upload a PDF document. The AI will read it chunk-by-chunk (10 pages at a time) and provide detailed explanations including images/charts.
            </p>
            
            <div className="flex flex-col sm:flex-row items-center space-y-4 sm:space-y-0 sm:space-x-4 mb-8">
                <input 
                    type="file" 
                    accept="application/pdf"
                    onChange={handleFileChange}
                    className={`block w-full text-sm ${factory.getText()} 
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-md file:border-0
                    file:text-sm file:font-semibold
                    file:bg-indigo-50 file:text-indigo-700
                    hover:file:bg-indigo-100
                    ${isDark ? 'file:bg-indigo-900/50 file:text-indigo-300' : ''}`}
                    disabled={isAnalyzing}
                />
                
                <button
                    onClick={startAnalysis}
                    disabled={!file || isAnalyzing}
                    className={`px-4 py-2 flex items-center justify-center rounded-md font-medium text-white shadow-sm transition-colors 
                        ${isAnalyzing || !file ? 'bg-indigo-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700'}
                    `}
                >
                    {isAnalyzing ? (
                        <>
                            <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Analyzing...
                        </>
                    ) : 'Start Analysis'}
                </button>
            </div>
            
            {error && (
                <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-6">
                    <p className="text-sm text-red-700">{error}</p>
                </div>
            )}
            
            <div className="space-y-6">
                {results.map((res, index) => (
                    <div key={index} className={`p-5 rounded-lg border ${isDark ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}`}>
                        <div className="flex items-center mb-3">
                            <span className="inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800">
                                Pages {res.chunk}
                            </span>
                            {res.status === 'error' && (
                                <span className="ml-2 inline-flex items-center justify-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-800">
                                    Error
                                </span>
                            )}
                        </div>
                        
                        <div className={`prose prose-sm max-w-none ${isDark ? 'prose-invert' : ''}`}>
                            {res.status === 'error' ? (
                                <p className="text-red-500">{res.message}</p>
                            ) : (
                                <>
                                    <div className="whitespace-pre-wrap">{res.explanation}</div>
                                    <QuizComponent explanation={res.explanation} isDark={isDark} factory={factory} />
                                </>
                            )}
                        </div>
                    </div>
                ))}
                <div ref={resultsEndRef} />
            </div>
            
        </section>
    );
}
