"use client";

import Link from "next/link";
import {
  LayoutDashboard,
  MessageSquare,
  Bot,
  Wrench,
  FileText,
  Clock3,
  Ticket,
} from "lucide-react";

const navigation = [
  {
    label: "Dashboard",
    href: "/admin",
    icon: LayoutDashboard,
  },
  {
    label: "Chat",
    href: "/chat",
    icon: MessageSquare,
  },
  {
    label: "Agents",
    href: "/admin/agents",
    icon: Bot,
  },
  {
    label: "MCP Tools",
    href: "/admin/mcp-tools",
    icon: Wrench,
  },
  {
    label: "RAG Documents",
    href: "/admin/rag",
    icon: FileText,
  },
  {
    label: "HITL Tasks",
    href: "/admin/hitl",
    icon: Clock3,
  },
  {
    label: "Tickets",
    href: "/admin/tickets",
    icon: Ticket,
  },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-64 border-r bg-background">
      <div className="flex h-16 items-center border-b px-6">
        <h1 className="text-lg font-semibold">
          AI Platform
        </h1>
      </div>

      <nav className="space-y-1 p-4">
        {navigation.map((item) => {
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}