"use client";

import Link from "next/link";
import { usePreferences } from "@/components/PreferencesProvider";

export function AnalysisIndexClient() {
  const { t } = usePreferences();

  return (
    <div className="mx-auto max-w-4xl rounded-md border border-line bg-surface p-8 shadow-soft">
      <h1 className="text-2xl font-semibold text-ink">{t("analysisTitle")}</h1>
      <p className="mt-2 text-sm text-muted">{t("analysisDescription")}</p>
      <Link className="mt-5 inline-flex rounded-md bg-court px-4 py-2 text-sm font-semibold text-white" href="/jobs">
        {t("goJobs")}
      </Link>
    </div>
  );
}
