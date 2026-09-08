import React, { createContext, useContext, useState, useEffect } from 'react';
import { LightThemeFactory, DarkThemeFactory } from './ThemeFactory';

const ThemeContext = createContext();

export const useTheme = () => {
    return useContext(ThemeContext);
};

export const ThemeProvider = ({ children }) => {
    const [isDark, setIsDark] = useState(true);

    useEffect(() => {
        // Automatically sync body class
        if (isDark) {
            document.body.className = "bg-slate-950 text-slate-100";
        } else {
            document.body.className = "bg-slate-50 text-slate-900";
        }
    }, [isDark]);

    const toggleTheme = () => setIsDark(!isDark);

    // The core of Abstract Factory: We provide the FACTORY, not just a string.
    const factory = isDark ? new DarkThemeFactory() : new LightThemeFactory();

    return (
        <ThemeContext.Provider value={{ factory, isDark, toggleTheme }}>
            {children}
        </ThemeContext.Provider>
    );
};
