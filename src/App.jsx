import React from 'react';
import NotifierCard from './components/NotifierCard';

function App() {
  return (
    <div className="min-h-screen bg-slate-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <header className="text-center">
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight sm:text-4xl">
            Productivity Automations
          </h1>
          <p className="mt-3 text-lg text-slate-500">
            Control Panel & Task Dashboard
          </p>
        </header>
        
        <main>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <NotifierCard 
              title="Incident Reporter"
              description="Generates a synthetic incident report and emails it to you. Scheduled daily at 14:00."
              type="incident"
              colorClass="bg-blue-600 hover:bg-blue-700"
              borderColorClass="border-blue-500"
              textColorClass="text-blue-700"
              bgLightClass="bg-blue-50"
            />
            <NotifierCard 
              title="LeetCode Notifier"
              description="Fetches a random Striver's sheet DSA problem with optimal solution and emails it. Scheduled hourly."
              type="leetcode"
              colorClass="bg-amber-500 hover:bg-amber-600"
              borderColorClass="border-amber-400"
              textColorClass="text-amber-700"
              bgLightClass="bg-amber-50"
            />
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
