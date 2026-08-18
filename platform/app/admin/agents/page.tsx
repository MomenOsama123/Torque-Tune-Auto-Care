"use client";

import { useState } from "react";
import { Bot, Edit3, Power } from "lucide-react";

const initialAgents = [
  {
    id: "general",
    name: "General Agent",
    description: "Handles general user requests.",
    status: "Active",
    tools: 4,
  },
  {
    id: "planning",
    name: "Planning Agent",
    description: "Breaks complex tasks into smaller steps.",
    status: "Active",
    tools: 5,
  },
  {
    id: "support",
    name: "Support Agent",
    description: "Handles troubleshooting and support requests.",
    status: "Inactive",
    tools: 3,
  },
];

export default function AgentsPage() {
  const [agents, setAgents] = useState(initialAgents);

  function toggleAgent(id: string) {
    setAgents((current) =>
      current.map((agent) =>
        agent.id === id
          ? {
              ...agent,
              status:
                agent.status === "Active"
                  ? "Inactive"
                  : "Active",
            }
          : agent
      )
    );
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold">
          Agents
        </h1>

        <p className="mt-2 text-muted-foreground">
          Manage the AI agents available on the platform.
        </p>
      </div>

      {/* Agent Cards */}
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="rounded-xl border bg-background p-6"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <Bot className="h-5 w-5" />
                </div>

                <div>
                  <h2 className="font-semibold">
                    {agent.name}
                  </h2>

                  <p className="text-xs text-muted-foreground">
                    {agent.tools} MCP tools
                  </p>
                </div>
              </div>

              <span
                className={`rounded-full px-2.5 py-1 text-xs ${
                  agent.status === "Active"
                    ? "bg-green-100 text-green-700"
                    : "bg-gray-100 text-gray-600"
                }`}
              >
                {agent.status}
              </span>
            </div>

            <p className="mt-5 text-sm text-muted-foreground">
              {agent.description}
            </p>

            <div className="mt-6 flex gap-2">
              <button
                className="flex flex-1 items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted"
                onClick={() =>
                  console.log("Edit agent:", agent.id)
                }
              >
                <Edit3 className="h-4 w-4" />
                Edit
              </button>

              <button
                className="flex items-center justify-center rounded-lg border px-3 py-2 hover:bg-muted"
                onClick={() => toggleAgent(agent.id)}
                title="Toggle agent"
              >
                <Power className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}