import Link from "next/link";
import {
  LayoutDashboard,
  Bot,
  Wrench,
  FileText,
  Clock3,
  Ticket,
  MessageSquare,
} from "lucide-react";

const links = [
  {
    name: "Dashboard",
    href: "/admin",
    icon: LayoutDashboard,
  },
  {
    name: "Agents",
    href: "/admin/agents",
    icon: Bot,
  },
  {
    name: "MCP Tools",
    href: "/admin/mcp-tools",
    icon: Wrench,
  },
  {
    name: "RAG Documents",
    href: "/admin/rag",
    icon: FileText,
  },
  {
    name: "HITL Tasks",
    href: "/admin/hitl",
    icon: Clock3,
  },
  {
    name: "Tickets",
    href: "/admin/tickets",
    icon: Ticket,
  },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 w-64 border-r bg-background">
        <div className="flex h-16 items-center border-b px-6">
          <h1 className="text-lg font-semibold">
            AI Platform
          </h1>
        </div>

        <nav className="space-y-1 p-4">
          {links.map((link) => {
            const Icon = link.icon;

            return (
              <Link
                key={link.href}
                href={link.href}
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Icon className="h-4 w-4" />
                {link.name}
              </Link>
            );
          })}

          <div className="my-4 border-t" />

          <Link
            href="/chat"
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <MessageSquare className="h-4 w-4" />
            User Chat
          </Link>
        </nav>
      </aside>

      <main className="ml-64 min-h-screen">
        {children}
      </main>
    </div>
  );
}