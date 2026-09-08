import React, { useState } from 'react';

const NotifierCard = ({ title, description, type, colorClass, borderColorClass, textColorClass, bgLightClass }) => {
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const handleTrigger = async () => {
        setLoading(true);
        setResult(null);
        setError(null);

        try {
            const response = await fetch('/api/trigger', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: type })
            });
            const data = await response.json();

            if (response.ok && data.status === 'success') {
                setResult(data.data);
            } else {
                setError(data.message || 'An error occurred.');
            }
        } catch (err) {
            setError('Server unreachable. Is the Flask backend running?');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={`bg-white rounded-xl shadow-sm border-t-4 ${borderColorClass} border-l border-r border-b border-slate-200 p-6 flex flex-col transition duration-200 hover:shadow-md hover:-translate-y-1`}>
            <div className="flex justify-between items-center mb-2">
                <h2 className="text-xl font-bold text-slate-800">{title}</h2>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${bgLightClass} ${textColorClass}`}>
                    <svg className={`-ml-0.5 mr-1.5 h-2 w-2 ${textColorClass}`} fill="currentColor" viewBox="0 0 8 8">
                        <circle cx="4" cy="4" r="3" />
                    </svg>
                    Active
                </span>
            </div>
            
            <p className="text-slate-500 text-sm mb-6 flex-grow">
                {description}
            </p>
            
            <button 
                onClick={handleTrigger}
                disabled={loading}
                className={`w-full flex justify-center items-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white ${colorClass} focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors`}
            >
                {loading ? (
                    <>
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Processing...
                    </>
                ) : 'Run Automation'}
            </button>

            {result && (
                <div className="mt-4 p-4 rounded-md bg-green-50 border border-green-200">
                    <div className="flex">
                        <div className="flex-shrink-0">
                            <svg className="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                        </div>
                        <div className="ml-3">
                            <h3 className="text-sm font-medium text-green-800">Successfully Sent</h3>
                            <div className="mt-2 text-sm text-green-700">
                                <ul className="list-disc pl-5 space-y-1">
                                    <li><span className="font-semibold">Title:</span> {result.title}</li>
                                    {result.category && <li><span className="font-semibold">Category:</span> {result.category}</li>}
                                    {result.difficulty && <li><span className="font-semibold">Difficulty:</span> {result.difficulty}</li>}
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {error && (
                <div className="mt-4 p-4 rounded-md bg-red-50 border border-red-200">
                    <div className="flex">
                        <div className="flex-shrink-0">
                            <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                            </svg>
                        </div>
                        <div className="ml-3">
                            <h3 className="text-sm font-medium text-red-800">Action Failed</h3>
                            <div className="mt-2 text-sm text-red-700">
                                <p>{error}</p>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default NotifierCard;
