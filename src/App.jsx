import React, { useState, useEffect } from 'react';
import NotifierCard from './components/NotifierCard';
import { useTheme } from './themes/ThemeContext';

function App() {
  const { factory, isDark, toggleTheme } = useTheme();
  const [logs, setLogs] = useState([]);
  const [interval, setIntervalVal] = useState("60");
  const [activeTab, setActiveTab] = useState('dashboard');

  const fetchLogs = async () => {
      try {
          const res = await fetch('/api/logs');
          const data = await res.json();
          if(data.status === 'success') setLogs(data.data);
      } catch (e) {}
  };

  const fetchSettings = async () => {
      try {
          const res = await fetch('/api/settings');
          const data = await res.json();
          if(data.status === 'success') setIntervalVal(data.leetcode_interval_minutes);
      } catch (e) {}
  };

  useEffect(() => {
      fetchLogs();
      fetchSettings();
  }, []);

  const handleToggleCompleted = async (logId, currentState) => {
      try {
          await fetch(`/api/logs/${logId}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ is_completed: !currentState })
          });
          fetchLogs(); // refresh
      } catch(e) {}
  };

  const handleIntervalChange = async (e) => {
      const val = e.target.value;
      setIntervalVal(val);
      await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ leetcode_interval_minutes: val })
      });
  };

  const solvedLogs = logs.filter(l => l.is_completed);
  const unsolvedLogs = logs.filter(l => !l.is_completed);

  return (
    <div className={`min-h-screen ${factory.getBackground()} py-12 px-4 sm:px-6 lg:px-8 transition-colors duration-300`}>
      <div className="max-w-4xl mx-auto space-y-8">
        
        <nav className={`flex justify-between items-center pb-4 border-b ${factory.getCardBorder()}`}>
          <div className="flex space-x-4">
            <button 
              onClick={() => setActiveTab('dashboard')} 
              className={`px-3 py-2 text-sm font-medium rounded-md ${activeTab === 'dashboard' ? 'bg-indigo-600 text-white' : factory.getText() + ' hover:bg-slate-800'}`}>
              Dashboard
            </button>
            <button 
              onClick={() => setActiveTab('solved')} 
              className={`px-3 py-2 text-sm font-medium rounded-md flex items-center ${activeTab === 'solved' ? 'bg-indigo-600 text-white' : factory.getText() + ' hover:bg-slate-800'}`}>
              Solved Problems 
              <span className="ml-2 inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                {solvedLogs.length}
              </span>
            </button>
          </div>
          <button onClick={toggleTheme} className={`px-4 py-2 rounded-md font-medium shadow-sm transition-colors ${factory.getSecondaryButton()}`}>
            {isDark ? '☀️ Light Mode' : '🌙 Dark Mode'}
          </button>
        </nav>

        <header className="flex justify-between items-center">
          <div>
            <h1 className={`text-3xl font-extrabold ${factory.getHeading()} tracking-tight sm:text-4xl`}>
              Productivity Automations
            </h1>
            <p className={`mt-3 text-lg ${factory.getText()}`}>
              Control Panel & Task Dashboard
            </p>
          </div>
        </header>

        {activeTab === 'dashboard' ? (
        <>
            <section className={`p-6 rounded-xl shadow-sm border-t-4 border-t-indigo-500 border border-b border-l border-r ${factory.getCardBackground()} ${factory.getCardBorder()}`}>
                <h2 className={`text-xl font-bold ${factory.getHeading()} mb-2`}>⚙️ Automation Settings</h2>
                <div className="flex items-center space-x-4">
                    <label className={`text-sm font-medium ${factory.getText()}`}>Receive LeetCode problem every (minutes):</label>
                    <select value={interval} onChange={handleIntervalChange} className={`mt-1 block w-48 pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md ${isDark ? 'bg-slate-800 text-white' : 'bg-white text-slate-900'}`}>
                        <option value="5">5 Minutes (Intense)</option>
                        <option value="10">10 Minutes</option>
                        <option value="30">30 Minutes</option>
                        <option value="60">1 Hour</option>
                        <option value="1440">24 Hours</option>
                    </select>
                </div>
                <p className={`mt-2 text-xs ${factory.getText()}`}>Powered autonomously by GitHub Actions. No local machine required!</p>
            </section>
            
            <main>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <NotifierCard 
                title="Incident Reporter"
                description="Generates a synthetic incident report and emails it to you. Scheduled daily at 14:00."
                type="incident"
                colorClass="bg-blue-600 hover:bg-blue-500"
                borderColorClass="border-blue-500"
                textColorClass={isDark ? "text-blue-300" : "text-blue-700"}
                bgLightClass={isDark ? "bg-blue-900/50" : "bg-blue-50"}
                />
                <NotifierCard 
                title="LeetCode Notifier"
                description="Fetches a non-repeating DSA problem with optimal approach and C++ code. Uses Spaced Repetition."
                type="leetcode"
                colorClass="bg-amber-500 hover:bg-amber-400"
                borderColorClass="border-amber-400"
                textColorClass={isDark ? "text-amber-300" : "text-amber-700"}
                bgLightClass={isDark ? "bg-amber-900/50" : "bg-amber-50"}
                />
            </div>
            </main>

            <section className={`p-6 rounded-xl shadow-sm border border-t border-b border-l border-r ${factory.getCardBackground()} ${factory.getCardBorder()}`}>
                <h2 className={`text-xl font-bold ${factory.getHeading()} mb-4`}>⏳ Unsolved Problems</h2>
                <p className={`text-sm ${factory.getText()} mb-4`}>Check off the problems you have fully understood. Unticked problems will be resent automatically for practice.</p>
                {unsolvedLogs.length === 0 ? (
                    <p className={`text-sm ${factory.getText()} italic`}>No unsolved problems. You are all caught up!</p>
                ) : (
                    <ul className="space-y-3">
                        {unsolvedLogs.map(log => (
                            <li key={log.id} className="flex items-center space-x-3">
                                <input 
                                    type="checkbox" 
                                    checked={log.is_completed}
                                    onChange={() => handleToggleCompleted(log.id, log.is_completed)}
                                    className="h-5 w-5 text-indigo-600 focus:ring-indigo-500 rounded cursor-pointer"
                                />
                                <span className={`text-base font-medium ${factory.getText()}`}>
                                    {log.title}
                                </span>
                                <span className={`text-xs ${factory.getText()} opacity-60`}>
                                    ({new Date(log.timestamp).toLocaleString()})
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </>
        ) : (
        <>
            <section className={`p-6 rounded-xl shadow-sm border border-t border-b border-l border-r ${factory.getCardBackground()} ${factory.getCardBorder()}`}>
                <h2 className={`text-xl font-bold ${factory.getHeading()} mb-4`}>✅ Solved Problems Archive</h2>
                <p className={`text-sm ${factory.getText()} mb-4`}>These are problems you have already mastered. Uncheck them if you want the system to resuggest them to you.</p>
                {solvedLogs.length === 0 ? (
                    <p className={`text-sm ${factory.getText()} italic`}>No solved problems yet. Keep grinding!</p>
                ) : (
                    <ul className="space-y-3">
                        {solvedLogs.map(log => (
                            <li key={log.id} className="flex items-center space-x-3 opacity-60 hover:opacity-100 transition-opacity">
                                <input 
                                    type="checkbox" 
                                    checked={log.is_completed}
                                    onChange={() => handleToggleCompleted(log.id, log.is_completed)}
                                    className="h-5 w-5 text-emerald-600 focus:ring-emerald-500 rounded cursor-pointer"
                                />
                                <span className={`text-base font-medium line-through ${factory.getText()}`}>
                                    {log.title}
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </>
        )}

      </div>
    </div>
  );
}

export default App;
