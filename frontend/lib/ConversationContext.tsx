"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  Conversation,
  deleteConversation as apiDeleteConversation,
  listConversations,
} from "@/lib/conversations";

interface ConversationContextType {
  activeConversationId: string | null;
  conversations: Conversation[];
  isLoadingConversations: boolean;
  sidebarOpen: boolean;
  mode: string;
  userRole: "student" | "teacher";
  setActiveConversationId: (id: string | null) => void;
  refreshConversations: () => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  createNewConversation: () => void;
  toggleSidebar: () => void;
  closeSidebar: () => void;
}

const ConversationContext = createContext<ConversationContextType | null>(null);

export function useConversation(): ConversationContextType {
  const ctx = useContext(ConversationContext);
  if (!ctx) throw new Error("useConversation must be used inside ConversationProvider");
  return ctx;
}

export function ConversationProvider({
  children,
  mode = "student",
  userRole = "student",
}: {
  children: React.ReactNode;
  mode?: string;
  userRole?: "student" | "teacher";
}) {
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const initialLoadRef = useRef(false);

  const refreshConversations = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations(list.filter((c) => c.mode === mode));
    } catch {
      // Graceful — user may not be logged in
    }
  }, [mode]);

  // Load on mount
  useEffect(() => {
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    setIsLoadingConversations(true);
    refreshConversations().finally(() => setIsLoadingConversations(false));
  }, [refreshConversations]);

  const deleteConversation = useCallback(
    async (id: string) => {
      await apiDeleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConversationId === id) {
        setActiveConversationId(null);
      }
    },
    [activeConversationId],
  );

  const createNewConversation = useCallback(() => {
    setActiveConversationId(null);
    setSidebarOpen(false);
  }, []);

  const toggleSidebar = useCallback(() => setSidebarOpen((v) => !v), []);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  return (
    <ConversationContext.Provider
      value={{
        activeConversationId,
        conversations,
        isLoadingConversations,
        sidebarOpen,
        mode,
        userRole,
        setActiveConversationId,
        refreshConversations,
        deleteConversation,
        createNewConversation,
        toggleSidebar,
        closeSidebar,
      }}
    >
      {children}
    </ConversationContext.Provider>
  );
}
