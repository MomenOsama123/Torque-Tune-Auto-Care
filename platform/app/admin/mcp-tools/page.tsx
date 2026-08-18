"use client";

import { useState } from "react";
import {
  Wrench,
  Plus,
  Trash2,
  Power,
} from "lucide-react";

const initialTools = [
  {
    id: "search",
    name: "Web Search",
    description: "Search external information.",
    agent: "General Agent",
    status: "Enabled",
  },
  {
    id: "database",
    name: "Database Query",
    description: "Query application data.",
    agent: "Planning Agent",
    status: "Enabled",
  },
  {
    id: "calculator",
    name: "Calculator",
    description: "Perform mathematical calculations.",
    agent: "General Agent",
    status: "Disabled",
  },
  {
    id: "documents",
    name: "Document Search",
    description: "Search indexed RAG documents.",
    agent: "Support Agent",
    status: "Enabled",
  },
];

export default function MCPToolsPage() {
  const [tools, setTools] = useState(initialTools);

  function toggleTool(id: string) {
    setTools((current) =>
      current.map((tool) =>
        tool.id === id
          ? {
              ...tool,
              status:
                tool.status === "Enabled"
                  ? "Disabled"
                  : "Enabled",
            }
          : tool
      )
    );
  }

  function deleteTool(id: string) {
    setTools((current) =>
      current.filter((tool) => tool.id !== id)
    );
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">
            MCP Tools
          </h1>

          <p className="mt-2 text-muted-foreground">
            Manage tools available to your AI agents.
          </p>
        </div>

        <button
          onClick={() =>
            alert("Add tool form will be connected to the MCP server.")
          }
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          Add Tool
        </button>
      </div>

      {/* Tools */}
      <div className="overflow-hidden rounded-xl border">
        <div className="grid grid-cols-12 border-b bg-muted/40 px-5 py-3 text-sm font-medium">
          <div className="col-span-3">Tool</div>
          <div className="col-span-4">Description</div>
          <div className="col-span-2">Agent</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-1">Actions</div>
        </div>

        {tools.map((tool) => (
          <div
            key={tool.id}
            className="grid grid-cols-12 items-center border-b px-5 py-4 last:border-b-0"
          >
            {/* Tool */}
            <div className="col-span-3 flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
                <Wrench className="h-4 w-4" />
              </div>

              <div>
                <p className="text-sm font-medium">
                  {tool.name}
                </p>

                <p className="text-xs text-muted-foreground">
                  {tool.id}
                </p>
              </div>
            </div>

            {/* Description */}
            <div className="col-span-4 text-sm text-muted-foreground">
              {tool.description}
            </div>

            {/* Agent */}
            <div className="col-span-2 text-sm">
              {tool.agent}
            </div>

            {/* Status */}
            <div className="col-span-2">
              <span
                className={`rounded-full px-2.5 py-1 text-xs ${
                  tool.status === "Enabled"
                    ? "bg-green-100 text-green-700"
                    : "bg-gray-100 text-gray-600"
                }`}
              >
                {tool.status}
              </span>
            </div>

            {/* Actions */}
            <div className="col-span-1 flex gap-1">
              <button
                onClick={() => toggleTool(tool.id)}
                className="rounded-md p-2 hover:bg-muted"
                title="Enable / Disable"
              >
                <Power className="h-4 w-4" />
              </button>

              <button
                onClick={() => deleteTool(tool.id)}
                className="rounded-md p-2 text-red-500 hover:bg-muted"
                title="Delete"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}