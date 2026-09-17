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
    const [isParsing, setIsParsing] = useState(false);
    const [fileId, setFileId] = useState(null);
    const [chunks, setChunks] = useState([]);
    const [error, setError] = useState('');
    const [expandedChunks, setExpandedChunks] = useState({});
    
    // State for individual chunk analysis
    const [analyzingChunk, setAnalyzingChunk] = useState({});
    const [chunkResults, setChunkResults] = useState({});
    const [defaultPdfs, setDefaultPdfs] = useState([]);

    useEffect(() => {
        // Fetch default pre-parsed PDFs
        fetch('/api/pdf/defaults')
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data)) setDefaultPdfs(data);
            })
            .catch(err => console.error("Failed to load default PDFs", err));
    }, []);

    const toggleChunk = (index) => {
        setExpandedChunks(prev => ({
            ...prev,
            [index]: !prev[index]
        }));
    };

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            setFile(e.target.files[0]);
            setError('');
            setChunks([]);
            setFileId(null);
            setExpandedChunks({});
            setChunkResults({});
        }
    };

    const startAnalysis = async () => {
        if (!file) {
            setError('Please select a PDF file first.');
            return;
        }
        
        setIsParsing(true);
        setChunks([]);
        setExpandedChunks({});
        setChunkResults({});
        setError('');
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch('/api/pdf/parse', {
                method: 'POST',
                body: formData,
            });
            
            if (!response.ok) {
                const errData = await response.json();
                setError(errData.message || 'Error parsing file.');
                setIsParsing(false);
                return;
            }
            
            const data = await response.json();
            setFileId(data.file_id);
            setChunks(data.chunks);
            // Auto-expand the first chunk
            if (data.chunks.length > 0) {
                setExpandedChunks({ 0: true });
            }
        } catch (err) {
            setError(err.message || 'Network error occurred.');
        } finally {
            setIsParsing(false);
        }
    };

    const selectDefaultPdf = (defaultPdf) => {
        setFile(null);
        setError('');
        setFileId(defaultPdf.file_id);
        setChunks(defaultPdf.chunks);
        setExpandedChunks({ 0: true });
        setChunkResults({});
    };

    const continueHere = async (chunkIndex) => {
        const chunk = chunks[chunkIndex];
        setAnalyzingChunk(prev => ({ ...prev, [chunkIndex]: true }));
        setChunkResults(prev => ({ ...prev, [chunkIndex]: null })); // Reset previous result if any

        try {
            const response = await fetch('/api/pdf/explain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_id: fileId,
                    chunk_start: chunk.chunk_start,
                    chunk_end: chunk.chunk_end
                }),
            });
            
            if (!response.ok) {
                const errData = await response.json();
                setChunkResults(prev => ({ ...prev, [chunkIndex]: { status: 'error', message: errData.message } }));
                return;
            }
            
            // Handle SSE response
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let done = false;

            while (!done) {
                const { value, done: readerDone } = await reader.read();
                done = readerDone;
                if (value) {
                    buffer += decoder.decode(value, { stream: true });
                    
                    let newlineIndex;
                    while ((newlineIndex = buffer.indexOf('\n\n')) >= 0) {
                        const line = buffer.slice(0, newlineIndex).trim();
                        buffer = buffer.slice(newlineIndex + 2);
                        
                        if (line.startsWith('data: ')) {
                            const dataStr = line.substring(6);
                            try {
                                const data = JSON.parse(dataStr);
                                setChunkResults(prev => ({ ...prev, [chunkIndex]: data }));
                            } catch (e) {
                                console.error('Error parsing SSE data:', e, dataStr);
                            }
                        }
                    }
                }
            }
        } catch (err) {
            setChunkResults(prev => ({ ...prev, [chunkIndex]: { status: 'error', message: err.message || 'Network error occurred.' } }));
        } finally {
            setAnalyzingChunk(prev => ({ ...prev, [chunkIndex]: false }));
        }
    };

    const goToChatGPT = (chunkText) => {
        // Prepare the prompt
        const prompt = `Please summarize and analyze the following text from a PDF document:\n\n${chunkText}`;
        
        // Copy to clipboard
        navigator.clipboard.writeText(prompt).then(() => {
            const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
            
            if (isMobile) {
                // Try deep linking to the app on mobile
                window.location.href = 'chatgpt://';
                // Fallback to web after a short delay if app doesn't open
                setTimeout(() => {
                    window.open('https://chatgpt.com', '_blank');
                }, 1000);
            } else {
                // Open web on desktop
                window.open('https://chatgpt.com', '_blank');
            }
        }).catch(err => {
            alert('Failed to copy to clipboard: ' + err);
        });
    };

    return (
        <section className={`p-8 rounded-2xl shadow-xl border backdrop-blur-md transition-all duration-500 ${isDark ? 'bg-slate-900/80 border-slate-700/50 shadow-indigo-900/20' : 'bg-white/90 border-gray-100 shadow-indigo-100/50'}`}>
            <div className="flex items-center space-x-3 mb-6">
                <div className="p-3 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg">
                    <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                </div>
                <h2 className={`text-3xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r ${isDark ? 'from-indigo-400 to-purple-400' : 'from-indigo-600 to-purple-600'}`}>PDF AI Studio</h2>
            </div>
            
            <p className={`text-base ${factory.getText()} mb-8 opacity-80 leading-relaxed`}>
                Upload a document to split it into precise, 10-page analytical chunks. Seamlessly generate deep insights locally using Gemini Vision, or export them to your favorite AI platform.
            </p>
            
            <div className="flex flex-col sm:flex-row items-center space-y-4 sm:space-y-0 sm:space-x-4 mb-10">
                <div className={`relative flex-1 w-full rounded-xl border-2 border-dashed p-2 transition-all duration-300 ${isDark ? 'border-slate-700 hover:border-indigo-500 bg-slate-800/50' : 'border-indigo-200 hover:border-indigo-400 bg-indigo-50/30'}`}>
                    <input 
                        type="file" 
                        accept="application/pdf"
                        onChange={handleFileChange}
                        className={`block w-full text-sm ${factory.getText()} 
                        file:mr-4 file:py-2.5 file:px-6
                        file:rounded-lg file:border-0
                        file:text-sm file:font-bold
                        file:bg-gradient-to-r file:from-indigo-500 file:to-purple-600 file:text-white
                        hover:file:opacity-90 file:cursor-pointer file:transition-opacity
                        file:shadow-md cursor-pointer`}
                        disabled={isParsing}
                    />
                </div>
                
                <button
                    onClick={startAnalysis}
                    disabled={!file || isParsing}
                    className={`px-8 py-4 flex items-center justify-center rounded-xl font-bold text-white shadow-lg transition-all duration-300 transform hover:-translate-y-1 
                        ${isParsing || !file ? 'bg-slate-400 cursor-not-allowed opacity-50 shadow-none hover:translate-y-0' : 'bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 hover:shadow-indigo-500/25'}
                    `}
                >
                    {isParsing ? (
                        <>
                            <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Parsing...
                        </>
                    ) : 'Parse Document'}
                </button>
            </div>
            
            {defaultPdfs.length > 0 && (
                <div className={`mb-10 p-5 rounded-xl border ${isDark ? 'bg-slate-800/50 border-slate-700' : 'bg-indigo-50/50 border-indigo-100'}`}>
                    <p className={`text-sm ${factory.getText()} mb-3 font-semibold tracking-wide uppercase opacity-70`}>✨ Or explore sample documents</p>
                    <div className="flex flex-wrap gap-3">
                        {defaultPdfs.map(pdf => (
                            <button
                                key={pdf.file_id}
                                onClick={() => selectDefaultPdf(pdf)}
                                className={`px-5 py-2.5 rounded-lg text-sm font-bold shadow-sm transition-all duration-300 transform hover:-translate-y-0.5
                                ${fileId === pdf.file_id 
                                    ? 'bg-gradient-to-r from-indigo-500 to-indigo-600 text-white ring-2 ring-indigo-300 ring-offset-2' 
                                    : (isDark ? 'bg-slate-800 border border-slate-600 hover:bg-slate-700 text-slate-200 hover:border-slate-500' : 'bg-white border border-gray-200 hover:border-indigo-300 hover:text-indigo-700 text-slate-700 hover:shadow-md')}`}
                            >
                                {pdf.name}
                            </button>
                        ))}
                    </div>
                </div>
            )}
            
            {error && (
                <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-6">
                    <p className="text-sm text-red-700">{error}</p>
                </div>
            )}
            
            <div className="space-y-6">
                {chunks.map((chunk, index) => {
                    const res = chunkResults[index];
                    const isAnalyzing = analyzingChunk[index];
                    
                    return (
                        <div key={index} className={`rounded-xl border overflow-hidden transition-all duration-300 shadow-sm hover:shadow-md ${isDark ? 'bg-slate-800/80 border-slate-700' : 'bg-white border-gray-200'}`}>
                            <button 
                                onClick={() => toggleChunk(index)}
                                className={`w-full flex justify-between items-center p-5 text-left transition-all ${isDark ? 'hover:bg-slate-700/80' : 'hover:bg-indigo-50/30'}`}
                            >
                                <div className="flex items-center space-x-3">
                                    <span className="inline-flex items-center justify-center px-3 py-1 rounded-full text-xs font-black tracking-wider uppercase bg-gradient-to-r from-indigo-100 to-purple-100 text-indigo-800 border border-indigo-200">
                                        📄 Pages {chunk.chunk}
                                    </span>
                                    {res && res.status === 'success' && (
                                        <span className="inline-flex items-center justify-center px-3 py-1 rounded-full text-xs font-black tracking-wider uppercase bg-gradient-to-r from-emerald-100 to-teal-100 text-emerald-800 border border-emerald-200">
                                            ✅ Analyzed
                                        </span>
                                    )}
                                    {res && res.status === 'error' && (
                                        <span className="inline-flex items-center justify-center px-3 py-1 rounded-full text-xs font-black tracking-wider uppercase bg-gradient-to-r from-red-100 to-rose-100 text-red-800 border border-red-200">
                                            ❌ Error
                                        </span>
                                    )}
                                </div>
                                <span className={`text-lg font-bold transition-transform duration-300 ${expandedChunks[index] ? 'rotate-180 text-indigo-500' : 'text-gray-400'}`}>
                                    ▼
                                </span>
                            </button>
                            
                            {expandedChunks[index] && (
                                <div className={`p-6 pt-2 border-t ${isDark ? 'border-slate-700/50 bg-slate-800/30' : 'border-gray-100 bg-gray-50/50'}`}>
                                    {/* Action Buttons */}
                                    <div className="flex flex-col sm:flex-row gap-4 py-4">
                                        <button 
                                            onClick={() => continueHere(index)}
                                            disabled={isAnalyzing}
                                            className="flex-1 py-3 bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-700 border border-indigo-200 hover:border-indigo-300 hover:from-indigo-100 hover:to-purple-100 rounded-xl text-sm font-bold transition-all shadow-sm disabled:opacity-50 flex items-center justify-center"
                                        >
                                            {isAnalyzing ? (
                                                <span className="flex items-center animate-pulse"><svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Analyzing...</span>
                                            ) : '🚀 Continue here (Gemini Vision)'}
                                        </button>
                                        
                                        <button 
                                            onClick={() => goToChatGPT(chunk.text)}
                                            className="flex-1 py-3 bg-gradient-to-r from-emerald-50 to-teal-50 text-emerald-700 border border-emerald-200 hover:border-emerald-300 hover:from-emerald-100 hover:to-teal-100 rounded-xl text-sm font-bold transition-all shadow-sm flex items-center justify-center"
                                        >
                                            📋 Copy & Go to ChatGPT
                                        </button>
                                    </div>
                                    
                                    {/* Analysis Result */}
                                    {res && (
                                        <div className={`mt-6 p-6 rounded-xl border bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm prose prose-sm max-w-none ${isDark ? 'prose-invert border-slate-700' : 'border-gray-200'}`}>
                                            {res.status === 'error' ? (
                                                <p className="text-red-500 font-bold">{res.message}</p>
                                            ) : (
                                                <>
                                                    <div className="whitespace-pre-wrap leading-relaxed">{res.explanation}</div>
                                                    <div className="mt-8 pt-8 border-t border-gray-200/50 dark:border-slate-700/50">
                                                        <QuizComponent explanation={res.explanation} isDark={isDark} factory={factory} />
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
            
        </section>
    );
}
