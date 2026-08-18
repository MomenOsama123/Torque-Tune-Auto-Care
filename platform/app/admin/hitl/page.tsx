"use client";

import { useState } from "react";
import {
  Clock3,
  Check,
  X,
  Play,
} from "lucide-react";

const initialTasks = [
  {
    id: "HITL-001",
    agent: "Planning Agent",
    task: "Approve final execution plan",
    reason: "High-impact action requires human approval.",
    status: "Pending",
    created: "5 min ago",
  },
  {
    id: "HITL-002",
    agent: "Support Agent",
    task: "Approve customer response",
    reason: "Response contains sensitive information.",
    status: "Pending",
    created: "12 min ago",
  },
  {
    id: "HITL-003",
    agent: "General Agent",
    task: "Confirm external tool execution",
    reason: "Tool execution requires administrator approval.",
    status: "Approved",
    created: "30 min ago",
  },
];

export default function HITLPage() {
  const [tasks, setTasks] = useState(initialTasks);

  function updateTask(
    id: string,
    status: "Approved" | "Rejected"
  ) {
    setTasks((current) =>
      current.map((task) =>
        task.id === id
          ? { ...task, status }
          : task
      )
    );
  }

  function resumeTask(id: string) {
    console.log("Resume HITL task:", id);

    setTasks((current) =>
      current.map((task) =>
        task.id === id
          ? { ...task, status: "Approved" }
          : task
      )
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-semibold">
          HITL Tasks
        </h1>

        <p className="mt-2 text-muted-foreground">
          Review and control tasks waiting for human intervention.
        </p>
      </div>

      <div className="space-y-4">
        {tasks.map((task) => (
          <div
            key={task.id}
            className="rounded-xl border bg-background p-6"
          >
            <div className="flex items-start justify-between gap-6">
              <div className="flex gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <Clock3 className="h-5 w-5" />
                </div>

                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="font-semibold">
                      {task.task}
                    </h2>

                    <span
                      className={`rounded-full px-2.5 py-1 text-xs ${
                        task.status === "Pending"
                          ? "bg-yellow-100 text-yellow-700"
                          : task.status === "Approved"
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {task.status}
                    </span>
                  </div>

                  <p className="mt-2 text-sm text-muted-foreground">
                    {task.reason}
                  </p>

                  <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
                    <span>
                      Agent: {task.agent}
                    </span>

                    <span>
                      {task.created}
                    </span>

                    <span>
                      ID: {task.id}
                    </span>
                  </div>
                </div>
              </div>

              {task.status === "Pending" && (
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() =>
                      updateTask(task.id, "Approved")
                    }
                    className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted"
                  >
                    <Check className="h-4 w-4" />
                    Approve
                  </button>

                  <button
                    onClick={() =>
                      updateTask(task.id, "Rejected")
                    }
                    className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-red-600 hover:bg-muted"
                  >
                    <X className="h-4 w-4" />
                    Reject
                  </button>
                </div>
              )}

              {task.status === "Approved" && (
                <button
                  onClick={() => resumeTask(task.id)}
                  className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground hover:opacity-90"
                >
                  <Play className="h-4 w-4" />
                  Resume
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}