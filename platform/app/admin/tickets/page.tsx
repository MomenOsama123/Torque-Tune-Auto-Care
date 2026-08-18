"use client";

import { useState } from "react";
import {
  Ticket,
  AlertCircle,
  CheckCircle2,
  Play,
} from "lucide-react";

const initialTickets = [
  {
    id: "TCK-001",
    title: "Planning node failed",
    agent: "Planning Agent",
    node: "plan_task",
    error: "Tool execution timeout",
    status: "Open",
    created: "10 min ago",
  },
  {
    id: "TCK-002",
    title: "Database connection failed",
    agent: "Support Agent",
    node: "fetch_customer",
    error: "Database connection unavailable",
    status: "Investigating",
    created: "25 min ago",
  },
  {
    id: "TCK-003",
    title: "External API error",
    agent: "General Agent",
    node: "external_search",
    error: "API returned 500",
    status: "Resolved",
    created: "1 hour ago",
  },
];

export default function TicketsPage() {
  const [tickets, setTickets] = useState(initialTickets);

  function resolveTicket(id: string) {
    setTickets((current) =>
      current.map((ticket) =>
        ticket.id === id
          ? { ...ticket, status: "Resolved" }
          : ticket
      )
    );
  }

  function resumeTicket(id: string) {
    console.log("Resume workflow:", id);

    setTickets((current) =>
      current.map((ticket) =>
        ticket.id === id
          ? { ...ticket, status: "Resolved" }
          : ticket
      )
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold">
          Tickets
        </h1>

        <p className="mt-2 text-muted-foreground">
          Monitor failures and recover interrupted workflows.
        </p>
      </div>

      <div className="space-y-4">
        {tickets.map((ticket) => (
          <div
            key={ticket.id}
            className="rounded-xl border p-6"
          >
            <div className="flex items-start justify-between gap-6">
              <div className="flex gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  {ticket.status === "Resolved" ? (
                    <CheckCircle2 className="h-5 w-5" />
                  ) : (
                    <AlertCircle className="h-5 w-5" />
                  )}
                </div>

                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="font-semibold">
                      {ticket.title}
                    </h2>

                    <span
                      className={`rounded-full px-2.5 py-1 text-xs ${
                        ticket.status === "Resolved"
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {ticket.status}
                    </span>
                  </div>

                  <p className="mt-2 text-sm text-muted-foreground">
                    {ticket.error}
                  </p>

                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                    <span>
                      Agent: {ticket.agent}
                    </span>

                    <span>
                      Node: {ticket.node}
                    </span>

                    <span>
                      {ticket.created}
                    </span>

                    <span>
                      ID: {ticket.id}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex shrink-0 gap-2">
                {ticket.status !== "Resolved" && (
                  <button
                    onClick={() =>
                      resolveTicket(ticket.id)
                    }
                    className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    Resolve
                  </button>
                )}

                <button
                  onClick={() =>
                    resumeTicket(ticket.id)
                  }
                  className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground hover:opacity-90"
                >
                  <Play className="h-4 w-4" />
                  Resume
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}