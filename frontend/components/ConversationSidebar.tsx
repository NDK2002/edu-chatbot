"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useConversation } from "@/lib/ConversationContext";
import { Conversation } from "@/lib/conversations";
import { logout } from "@/app/auth/actions";

// ── Nav links shown at the bottom of the sidebar ────────────────────────────

const NAV_LINKS_BASE = [
  {
    href: "/dictionary",
    label: "Từ điển Việt–Tày/Nùng",
    teacherOnly: false,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 shrink-0">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
      </svg>
    ),
  },
  {
    href: "/teacher",
    label: "Giáo viên",
    teacherOnly: true,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 shrink-0">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 3.741-3.342M6.75 15a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm0 0v-3.675A55.378 55.378 0 0 1 12 8.443m-7.007 11.55A5.981 5.981 0 0 0 6.75 15.75v-1.5" />
      </svg>
    ),
  },
];

const LogoutIcon = (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 shrink-0">
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
  </svg>
);

// ── Time grouping helpers ────────────────────────────────────────────────────

function getGroup(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86_400_000);
  const weekAgo = new Date(today.getTime() - 7 * 86_400_000);

  if (date >= today) return "Hôm nay";
  if (date >= yesterday) return "Hôm qua";
  if (date >= weekAgo) return "7 ngày qua";
  return "Cũ hơn";
}

const GROUP_ORDER = ["Hôm nay", "Hôm qua", "7 ngày qua", "Cũ hơn"];

function groupConversations(convs: Conversation[]): Map<string, Conversation[]> {
  const groups = new Map<string, Conversation[]>();
  for (const c of convs) {
    const g = getGroup(c.last_message_at);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g)!.push(c);
  }
  return groups;
}

// ── Conversation list item ───────────────────────────────────────────────────

function ConvItem({
  conv,
  isActive,
  onSelect,
  onDelete,
}: {
  conv: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  function handleDeleteClick(e: React.MouseEvent) {
    e.stopPropagation();
    setConfirmOpen(true);
  }

  return (
    <div className="relative group">
      <button
        onClick={onSelect}
        title={conv.title}
        className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-center gap-1.5 ${
          isActive
            ? "bg-sky-100 text-sky-800 font-medium"
            : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
        }`}
      >
        <span className="flex-1 truncate min-w-0">{conv.title}</span>
        {conv.is_compacted && (
          <span className="shrink-0 text-[10px] text-sky-500 font-medium">✦</span>
        )}
        <span
          role="button"
          tabIndex={0}
          onClick={handleDeleteClick}
          onKeyDown={(e) => e.key === "Enter" && handleDeleteClick(e as unknown as React.MouseEvent)}
          className="shrink-0 p-0.5 rounded hover:text-red-500 transition-colors opacity-0 group-hover:opacity-60 hover:!opacity-100"
          title="Xóa"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
            <path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35l.815-8.15h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clipRule="evenodd" />
          </svg>
        </span>
      </button>

      {confirmOpen && (
        <div
          className="absolute left-0 right-0 z-10 top-full mt-1 bg-white border border-gray-200 rounded-xl shadow-lg p-3"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-xs text-gray-700 mb-2">Xóa cuộc trò chuyện này?</p>
          <div className="flex gap-2 justify-end">
            <button
              onClick={(e) => { e.stopPropagation(); setConfirmOpen(false); }}
              className="px-2.5 py-1 text-xs rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600"
            >
              Hủy
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setConfirmOpen(false); onDelete(); }}
              className="px-2.5 py-1 text-xs rounded-lg bg-red-500 hover:bg-red-600 text-white"
            >
              Xóa
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main sidebar content (shared desktop + mobile) ───────────────────────────

function SidebarContent({
  onClose,
  displayName,
  role = "student",
}: {
  onClose?: () => void;
  displayName?: string | null;
  role?: "student" | "teacher";
}) {
  const pathname = usePathname();
  const router = useRouter();
  const {
    activeConversationId,
    conversations,
    isLoadingConversations,
    setActiveConversationId,
    deleteConversation,
    createNewConversation,
  } = useConversation();

  const groups = groupConversations(conversations);

  function handleSelect(id: string) {
    setActiveConversationId(id);
    onClose?.();
    if (!pathname.startsWith("/student")) router.push("/student");
  }

  function handleNewConversation() {
    createNewConversation();
    if (!pathname.startsWith("/student")) router.push("/student");
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Logo ── */}
      <div className="px-4 py-4 border-b border-gray-100 flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center overflow-hidden shadow shrink-0">
            <Image src="/student-icon.png" alt="App" width={22} height={22} loading="eager" priority />
          </div>
          <div>
            <p className="font-bold text-sky-800 text-sm leading-tight">Chatbot Giáo dục</p>
            <p className="text-[11px] text-sky-500">Việt–Tày/Nùng</p>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400 shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
          </button>
        )}
      </div>

      {/* ── New conversation button ── */}
      <div className="px-3 pt-3 pb-2 shrink-0">
        <button
          onClick={handleNewConversation}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium bg-sky-500 text-white hover:bg-sky-600 active:scale-95 transition-all shadow-sm"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 shrink-0">
            <path d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z" />
          </svg>
          Cuộc trò chuyện mới
        </button>
      </div>

      {/* ── Conversation list (scrollable) ── */}
      <div className="flex-1 overflow-y-auto px-3 pb-2 min-h-0">
        {isLoadingConversations && (
          <div className="py-6 flex justify-center">
            <span className="w-4 h-4 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        {!isLoadingConversations && conversations.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-6 px-2">
            Chưa có cuộc trò chuyện nào
          </p>
        )}
        {GROUP_ORDER.map((groupName) => {
          const items = groups.get(groupName);
          if (!items || items.length === 0) return null;
          return (
            <div key={groupName} className="mb-3">
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide px-1 py-1.5">
                {groupName}
              </p>
              <div className="space-y-0.5">
                {items.map((conv) => (
                  <ConvItem
                    key={conv.id}
                    conv={conv}
                    isActive={conv.id === activeConversationId}
                    onSelect={() => handleSelect(conv.id)}
                    onDelete={() => deleteConversation(conv.id)}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Bottom: nav links + user + logout ── */}
      <div className="shrink-0 border-t border-gray-100">
        {/* Nav links */}
        <div className="px-3 py-2 space-y-0.5">
          {NAV_LINKS_BASE.filter((l) => !l.teacherOnly || role === "teacher").map(({ href, label, icon }) => (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                pathname.startsWith(href)
                  ? "bg-sky-50 text-sky-700"
                  : "text-gray-500 hover:bg-gray-100 hover:text-gray-800"
              }`}
            >
              {icon}
              {label}
            </Link>
          ))}
        </div>

        {/* User + logout */}
        <div className="px-3 py-2 border-t border-gray-100">
          {displayName && (
            <div className="flex items-center gap-2 px-2 py-1.5 mb-1">
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 flex items-center justify-center text-white text-[11px] font-bold shrink-0">
                {displayName.charAt(0).toUpperCase()}
              </div>
              <p className="text-sm font-medium text-gray-700 truncate">{displayName}</p>
            </div>
          )}
          <form action={logout}>
            <button
              type="submit"
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-500 hover:bg-red-50 hover:text-red-600 transition-colors"
            >
              {LogoutIcon}
              Đăng xuất
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// ── Export: desktop aside + mobile overlay ───────────────────────────────────

export default function ConversationSidebar({
  displayName,
  role = "student",
}: {
  displayName?: string | null;
  role?: "student" | "teacher";
}) {
  const { sidebarOpen, closeSidebar } = useConversation();
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sidebarOpen) return;
    function handleOutside(e: MouseEvent) {
      if (overlayRef.current && !overlayRef.current.contains(e.target as Node)) {
        closeSidebar();
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [sidebarOpen, closeSidebar]);

  return (
    <>
      {/* Desktop */}
      <aside className="hidden md:flex flex-col w-64 shrink-0 bg-white border-r border-gray-100 shadow-sm">
        <SidebarContent displayName={displayName} role={role} />
      </aside>

      {/* Mobile backdrop */}
      <div
        className={`md:hidden fixed inset-0 z-40 bg-black/40 transition-opacity duration-200 ${
          sidebarOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
      />

      {/* Mobile drawer */}
      <div
        ref={overlayRef}
        className={`md:hidden fixed inset-y-0 left-0 z-50 w-72 bg-white shadow-xl flex flex-col transition-transform duration-200 ease-out ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <SidebarContent onClose={closeSidebar} displayName={displayName} role={role} />
      </div>
    </>
  );
}
