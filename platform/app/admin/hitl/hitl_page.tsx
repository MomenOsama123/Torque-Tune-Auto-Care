"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Clock3, RefreshCw, X } from "lucide-react";

import {
  fetchHitlTasks,
  GRAPH_LABELS,
  submitManagerDecision,
  type HitlTask,
} from "@/lib/api";

// A task is "still waiting" only while its latest checkpoint is
// paused_hitl. If a decision resumes it straight into paused_external
// or completed, it should disappear from this list on the next refresh
// -- refetching from the server (rather than optimistically editing
// local state) is what keeps this page honest about what's actually
// still pending.

function formatPayloadValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase());
}

export default function HITLPage() {
  const [tasks, setTasks] = useState<HitlTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchHitlTasks();
      setTasks(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not reach the backend API."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setError(null);
      try {
        const data = await fetchHitlTasks();
        if (!cancelled) setTasks(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not reach the backend API."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  async function decide(task: HitlTask, approved: boolean) {
    setActingOn(task.thread_id);
    setActionError(null);
    try {
      if (
        task.graph !== "purchase_order" &&
        task.graph !== "warranty_claim" &&
        task.graph !== "inventory_approval"
      ) {
        throw new Error(`Unrecognized graph type: ${task.graph}`);
      }
      await submitManagerDecision({
        graph: task.graph,
        threadId: task.thread_id,
        approved,
      } as Parameters<typeof submitManagerDecision>[0]);
      await load();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to submit decision."
      );
    } finally {
      setActingOn(null);
    }
  }

  return (
    <div className="p-8">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">HITL Tasks</h1>
          <p className="mt-2 text-muted-foreground">
            Real threads currently paused on a state graph, waiting for a
            manager decision.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex shrink-0 items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Couldn&apos;t load HITL tasks</p>
            <p className="mt-1 text-red-600">{error}</p>
            <p className="mt-1 text-red-600">
              Is the API running? (<code>uvicorn api.api:app --reload</code>{" "}
              from the repo root)
            </p>
          </div>
        </div>
      )}

      {actionError && (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{actionError}</p>
        </div>
      )}

      {loading && !error && (
        <p className="text-sm text-muted-foreground">Loading HITL tasks…</p>
      )}

      {!loading && !error && tasks.length === 0 && (
        <div className="rounded-xl border bg-background p-8 text-center text-sm text-muted-foreground">
          No pending HITL tasks right now.
        </div>
      )}

      <div className="space-y-4">
        {tasks.map((task) => (
          <div
            key={task.thread_id}
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
                      {GRAPH_LABELS[task.graph] ?? task.graph}
                    </h2>
                    <span className="rounded-full bg-yellow-100 px-2.5 py-1 text-xs text-yellow-700">
                      Pending
                    </span>
                  </div>

                  <p className="mt-2 text-sm text-muted-foreground">
                    {task.reason
                      ? humanizeKey(task.reason)
                      : "Paused for manager review."}
                  </p>

                  {task.payload && Object.keys(task.payload).length > 0 && (
                    <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3">
                      {Object.entries(task.payload).map(([key, value]) => (
                        <div key={key}>
                          <dt className="font-medium text-foreground/70">
                            {humanizeKey(key)}
                          </dt>
                          <dd className="truncate">
                            {formatPayloadValue(value)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}

                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                    <span>Node: {task.node}</span>
                    <span>
                      {new Date(task.created_at).toLocaleString()}
                    </span>
                    <span title={task.thread_id}>
                      Thread: {task.thread_id.slice(0, 12)}…
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => decide(task, true)}
                  disabled={actingOn === task.thread_id}
                  className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50"
                >
                  <Check className="h-4 w-4" />
                  {actingOn === task.thread_id ? "Approving…" : "Approve"}
                </button>

                <button
                  onClick={() => decide(task, false)}
                  disabled={actingOn === task.thread_id}
                  className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-red-600 hover:bg-muted disabled:opacity-50"
                >
                  <X className="h-4 w-4" />
                  {actingOn === task.thread_id ? "Rejecting…" : "Reject"}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
