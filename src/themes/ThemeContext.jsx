import { createContext, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext({ isDark: true, toggleTheme: () => {} });

export const useTheme = () => useContext(ThemeContext);

const initial = () => {
    try {
        const saved = localStorage.getItem('theme');
        if (saved) return saved === 'dark';
    } catch { /* storage unavailable */ }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true;
};

export const ThemeProvider = ({ children }) => {
    const [isDark, setIsDark] = useState(initial);

    useEffect(() => {
        const theme = isDark ? 'dark' : 'light';
        document.documentElement.dataset.theme = theme;
        document.querySelector('meta[name="theme-color"]')?.setAttribute('content', isDark ? '#08080a' : '#f6f6f7');
        try { localStorage.setItem('theme', theme); } catch { /* storage unavailable */ }
    }, [isDark]);

    const toggleTheme = () => setIsDark((d) => !d);

    return (
        <ThemeContext.Provider value={{ isDark, toggleTheme }}>
            {children}
        </ThemeContext.Provider>
    );
};
