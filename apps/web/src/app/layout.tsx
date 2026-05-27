import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { PreferencesProvider } from "@/components/PreferencesProvider";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Shuttle Scope",
  description: "Local badminton video AI analysis workstation"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <PreferencesProvider>
          <div className="flex min-h-screen bg-app text-ink">
            <Sidebar />
            <main className="min-w-0 flex-1 px-6 py-5 xl:px-8">{children}</main>
          </div>
        </PreferencesProvider>
      </body>
    </html>
  );
}
