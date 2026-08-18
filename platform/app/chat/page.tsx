"use client";

import { useState } from "react";
import { Send, Bot, User } from "lucide-react";

const agents = [
  {
    id: "general",
    name: "General Agent",
    description: "General purpose AI assistant",
  },
  {
    id: "planning",
    name: "Planning Agent",
    description: "Handles planning and task decomposition",
  },
  {
    id: "support",
    name: "Support Agent",
    description: "Handles support and troubleshooting",
  },
];

export default function ChatPage() {
  const [selectedAgent, setSelectedAgent] = useState("general");
  const [message, setMessage] = useState("");

  const currentAgent = agents.find(
    (agent) => agent.id === selectedAgent
  );

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    if (!message.trim()) return;

    console.log({
      agent: selectedAgent,
      message,
    });

    setMessage("");
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Header */}
      <header className="flex h-16 items-center justify-between border-b px-6">
        <div>
          <h1 className="text-lg font-semibold">
            AI Assistant
          </h1>

          <p className="text-sm text-muted-foreground">
            Stateful AI Platform
          </p>
        </div>

        {/* Agent Switcher */}
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            Agent
          </span>

          <select
            value={selectedAgent}
            onChange={(event) =>
              setSelectedAgent(event.target.value)
            }
            className="rounded-md border bg-background px-3 py-2 text-sm"
          >
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Agent Info */}
      <div className="border-b px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
            <Bot className="h-5 w-5" />
          </div>

          <div>
            <p className="font-medium">
              {currentAgent?.name}
            </p>

            <p className="text-sm text-muted-foreground">
              {currentAgent?.description}
            </p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto flex max-w-4xl flex-col gap-6">

          {/* Assistant Message */}
          <div className="flex gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted">
              <Bot className="h-4 w-4" />
            </div>

            <div className="max-w-[75%] rounded-lg border bg-muted/40 px-4 py-3">
              <p className="text-sm">
                Hello! I'm {currentAgent?.name}.
                How can I help you today?
              </p>
            </div>
          </div>

          {/* User Message */}
          <div className="flex justify-end gap-3">
            <div className="max-w-[75%] rounded-lg bg-primary px-4 py-3 text-primary-foreground">
              <p className="text-sm">
                Welcome to the AI Platform.
              </p>
            </div>

            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted">
              <User className="h-4 w-4" />
            </div>
          </div>

        </div>
      </main>

      {/* Input */}
      <footer className="border-t p-4">
        <form
          onSubmit={handleSubmit}
          className="mx-auto flex max-w-4xl gap-3"
        >
          <input
            value={message}
            onChange={(event) =>
              setMessage(event.target.value)
            }
            placeholder={`Message ${currentAgent?.name}...`}
            className="flex-1 rounded-lg border bg-background px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-ring"
          />

          <button
            type="submit"
            className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>
      </footer>
    </div>
  );
}