import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Bot,
  Clock3,
  FileText,
  Ticket,
  Wrench,
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
    <div className="min-h-screen p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold">
          Dashboard
        </h1>

        <p className="mt-2 text-muted-foreground">
          Monitor agents, tools, documents, tasks, and tickets.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        {stats.map((stat) => {
          const Icon = stat.icon;

          return (
            <Card key={stat.title}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">
                  {stat.title}
                </CardTitle>

                <Icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>

              <CardContent>
                <div className="text-2xl font-bold">
                  {stat.value}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>

          <CardContent>
            <p className="text-sm text-muted-foreground">
              No recent activity.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System Status</CardTitle>
          </CardHeader>

          <CardContent>
            <p className="text-sm text-muted-foreground">
              All services are running.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}