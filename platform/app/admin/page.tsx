import {
  Bot,
  Wrench,
  FileText,
  Clock3,
  Ticket,
} from "lucide-react";

const stats = [
  {
    title: "Active Agents",
    value: "3",
    icon: Bot,
  },
  {
    title: "MCP Tools",
    value: "12",
    icon: Wrench,
  },
  {
    title: "RAG Documents",
    value: "24",
    icon: FileText,
  },
  {
    title: "HITL Tasks",
    value: "4",
    icon: Clock3,
  },
  {
    title: "Open Tickets",
    value: "2",
    icon: Ticket,
  },
];

export default function AdminDashboard() {
  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold">
          Dashboard
        </h1>

        <p className="mt-2 text-muted-foreground">
          Monitor your AI agents and platform activity.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        {stats.map((stat) => {
          const Icon = stat.icon;

          return (
            <div
              key={stat.title}
              className="rounded-xl border p-5"
            >
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {stat.title}
                </p>

                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>

              <p className="mt-3 text-3xl font-semibold">
                {stat.value}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}