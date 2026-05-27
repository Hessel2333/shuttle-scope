"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { dictionaries, type I18nKey, type Language, type ThemePreference } from "@/lib/i18n";

type PreferencesContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  resolvedTheme: "light" | "dark";
  t: (key: I18nKey) => string;
};

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("zh");
  const [theme, setThemeState] = useState<ThemePreference>("system");
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const storedLanguage = window.localStorage.getItem("shuttle-scope-language") as Language | null;
    const storedTheme = window.localStorage.getItem("shuttle-scope-theme") as ThemePreference | null;
    if (storedLanguage === "zh" || storedLanguage === "en") setLanguageState(storedLanguage);
    if (storedTheme === "light" || storedTheme === "dark" || storedTheme === "system") setThemeState(storedTheme);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const nextResolved = theme === "system" ? (media.matches ? "dark" : "light") : theme;
      setResolvedTheme(nextResolved);
      document.documentElement.classList.toggle("dark", nextResolved === "dark");
      document.documentElement.dataset.theme = nextResolved;
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  const value = useMemo<PreferencesContextValue>(() => {
    return {
      language,
      setLanguage: (nextLanguage) => {
        setLanguageState(nextLanguage);
        window.localStorage.setItem("shuttle-scope-language", nextLanguage);
      },
      theme,
      setTheme: (nextTheme) => {
        setThemeState(nextTheme);
        window.localStorage.setItem("shuttle-scope-theme", nextTheme);
      },
      resolvedTheme,
      t: (key) => dictionaries[language][key]
    };
  }, [language, resolvedTheme, theme]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences() {
  const value = useContext(PreferencesContext);
  if (!value) {
    throw new Error("usePreferences must be used inside PreferencesProvider");
  }
  return value;
}
