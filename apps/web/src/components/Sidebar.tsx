"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Languages, ListChecks, Monitor, Moon, Settings, Sun, Upload } from "lucide-react";
import { usePreferences } from "@/components/PreferencesProvider";
import type { Language, ThemePreference } from "@/lib/i18n";

const items = [
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/jobs", label: "Jobs", icon: ListChecks },
  { href: "/analysis", label: "Analysis", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings }
];

export function Sidebar() {
  const pathname = usePathname();
  const { language, setLanguage, theme, setTheme, t } = usePreferences();

  return (
    <aside className="flex min-h-screen w-64 shrink-0 flex-col border-r border-line bg-surface px-4 py-5">
      <div className="mb-7">
        <div className="text-lg font-semibold tracking-normal text-ink">Shuttle Scope</div>
        <div className="mt-1 text-xs text-muted">{t("navSubtitle")}</div>
      </div>
      <nav className="space-y-1">
        {items.map((item) => {
          const active = pathname === item.href || (item.href !== "/analysis" && pathname.startsWith(`${item.href}/`));
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex h-11 items-center gap-3 rounded-md px-3 text-sm font-medium transition ${
                active ? "bg-court text-white" : "text-muted hover:bg-subtle hover:text-ink"
              }`}
            >
              <Icon size={18} />
              {t(item.label.toLowerCase() as "upload" | "jobs" | "analysis" | "settings")}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto space-y-4">
        <ControlGroup icon={<Languages size={15} />} label={t("language")}>
          <SegmentedButton<Language> value={language} options={[["zh", "中"], ["en", "EN"]]} onChange={setLanguage} />
        </ControlGroup>
        <ControlGroup icon={themeIcon(theme)} label={t("appearance")}>
          <SegmentedButton<ThemePreference>
            value={theme}
            options={[
              ["light", <Sun key="sun" size={14} />],
              ["dark", <Moon key="moon" size={14} />],
              ["system", <Monitor key="monitor" size={14} />]
            ]}
            onChange={setTheme}
          />
        </ControlGroup>
        <div className="whitespace-pre-line rounded-md border border-line bg-subtle p-3 text-xs leading-5 text-muted">{t("localOnly")}</div>
      </div>
    </aside>
  );
}

function ControlGroup({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-muted">
        {icon}
        {label}
      </div>
      {children}
    </div>
  );
}

function SegmentedButton<T extends string>({
  value,
  options,
  onChange
}: {
  value: T;
  options: [T, React.ReactNode][];
  onChange: (value: T) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-1 rounded-md border border-line bg-subtle p-1">
      {options.map(([option, label]) => (
        <button
          key={option}
          type="button"
          title={option}
          className={`focus-ring flex h-8 items-center justify-center rounded px-2 text-xs font-semibold transition ${
            value === option ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
          }`}
          onClick={() => onChange(option)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function themeIcon(theme: ThemePreference) {
  if (theme === "light") return <Sun size={15} />;
  if (theme === "dark") return <Moon size={15} />;
  return <Monitor size={15} />;
}
