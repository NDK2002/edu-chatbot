"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ConversationProvider } from "@/lib/ConversationContext";
import ConversationSidebar from "@/components/ConversationSidebar";
import { logout } from "@/app/auth/actions";

const MOBILE_NAV_BASE = [
  {
    href: "/student",
    short: "Chat",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
      </svg>
    ),
  },
  {
    href: "/dictionary",
    short: "Từ điển",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
      </svg>
    ),
  },
];

const TEACHER_NAV_ITEM = {
  href: "/teacher",
  short: "Soạn bài",
  icon: (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 3.741-3.342M6.75 15a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm0 0v-3.675A55.378 55.378 0 0 1 12 8.443m-7.007 11.55A5.981 5.981 0 0 0 6.75 15.75v-1.5" />
    </svg>
  ),
};

export default function ProtectedShell({
  children,
  displayName,
  role = "student",
}: {
  children: React.ReactNode;
  displayName: string | null;
  role?: "student" | "teacher";
}) {
  const pathname = usePathname();

  const mobileNav = role === "teacher"
    ? [...MOBILE_NAV_BASE, TEACHER_NAV_ITEM]
    : MOBILE_NAV_BASE;

  return (
    <ConversationProvider mode="student">
      <div className="flex h-screen overflow-hidden">
        {/* Sidebar: conversation history on all protected pages */}
        <ConversationSidebar displayName={displayName} />

        {/* Main column */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <main
            key={pathname}
            className="flex-1 min-h-0 animate-page-in"
            style={{ willChange: "opacity" }}
          >
            {children}
          </main>

          {/* Mobile bottom tabs */}
          <nav className="md:hidden shrink-0 flex items-stretch bg-white border-t border-gray-100">
            {mobileNav.map(({ href, short, icon }) => {
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
                  {icon}
                  <span>{short}</span>
                </Link>
              );
            })}
            <form action={logout} className="flex-1">
              <button
                type="submit"
                className="w-full h-full flex flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium text-gray-500 hover:text-red-600 transition-colors border-t-2 border-transparent"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
                </svg>
                <span>Thoát</span>
              </button>
            </form>
          </nav>
        </div>
      </div>
    </ConversationProvider>
  );
}
