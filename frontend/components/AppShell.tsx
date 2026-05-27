"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/student",    emoji: "💬", label: "Chat học sinh", short: "Chat"     },
  { href: "/dictionary", emoji: "📖", label: "Từ điển",       short: "Từ điển"  },
  { href: "/teacher",    emoji: "👩‍🏫", label: "Giáo viên",    short: "Giáo viên" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── Desktop sidebar ── */}
      <aside className="hidden md:flex flex-col w-56 shrink-0 bg-white border-r border-gray-100 shadow-sm">
        {/* Logo */}
        <div className="px-4 py-5 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center overflow-hidden shadow">
              <Image src="/student-icon.png" alt="App" width={24} height={24} />
            </div>
            <div>
              <p className="font-bold text-sky-800 text-sm leading-tight">Chatbot Giáo dục</p>
              <p className="text-xs text-sky-500">Việt–Tày/Nùng</p>
            </div>
          </div>
        </div>

        {/* Nav items */}
        <nav className="flex-1 flex flex-col gap-1 p-3">
          {NAV.map(({ href, emoji, label }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                  active
                    ? "bg-sky-50 text-sky-700 border border-sky-100"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <span className="text-base">{emoji}</span>
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="px-4 py-3 border-t border-gray-100">
          <p className="text-xs text-gray-400">SGK Cánh Diều · Lớp 1–5</p>
        </div>
      </aside>

      {/* ── Main column ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* key={pathname} remounts on navigation → triggers animation */}
        <main key={pathname} className="flex-1 min-h-0 animate-page-in" style={{ willChange: "opacity" }}>
          {children}
        </main>

        {/* ── Mobile bottom tabs ── */}
        <nav className="md:hidden shrink-0 flex items-stretch bg-white border-t border-gray-100 safe-area-pb">
          {NAV.map(({ href, emoji, short }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium transition-colors border-t-2 ${
                  active
                    ? "text-sky-600 border-sky-500"
                    : "text-gray-500 border-transparent hover:text-gray-700"
                }`}
              >
                <span className="text-xl leading-none">{emoji}</span>
                <span>{short}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
