import { request } from "../client";
import type { Schema } from "../types";

export type Task = Schema<"TaskResponse">;
export type TaskItem = Schema<"TaskItemRead">;
export type TaskCreateRequest = Schema<"TaskCreateRequest">;
export type BindingTaskCreateRequest = Schema<"BindingTaskCreateRequest">;
export type TaskType = "import" | "reindex" | "delete";

export const TASK_TYPE_LABELS: Record<string, string> = { import: "导入", reindex: "重建索引", delete: "删除索引" };

// Mirrors knowledge/services/task_queue.py ACTIVE_TASK_STATUSES.
export const ACTIVE_TASK_STATUSES = new Set(["pending", "running", "cancel_requested"]);
export const RETRYABLE_TASK_STATUSES = new Set(["failed", "partial_success"]);

export function isTaskActive(status: string | null | undefined): boolean {
  return ACTIVE_TASK_STATUSES.has(String(status ?? "").toLowerCase());
}

/** Human description of where a task sits in the queue (ported from the legacy console). */
export function describeTaskQueue(task: Task): string {
  if (task.status === "running") return "执行中";
  if (task.status === "cancel_requested") return "取消中，等待当前文件处理完成后自动回退";
  if (task.status === "canceled") return "已取消";
  if (task.status === "pending") {
    const queue = task.queue_position ? `排队中 · 第 ${task.queue_position} 位` : "排队中";
    return task.current_running_task_type ? `${queue} · 当前执行 ${task.current_running_task_type} #${task.current_running_task_id}` : queue;
  }
  return "已完成";
}

export const tasksApi = {
  list: () => request<Task[]>("/tasks"),
  get: (taskId: number) => request<Task>(`/tasks/${taskId}`),
  items: (taskId: number) => request<TaskItem[]>(`/tasks/${taskId}/items`),
  retry: (taskId: number) => request<Task>(`/tasks/${taskId}/retry`, { method: "POST" }),
  cancel: (taskId: number) => request<Task>(`/tasks/${taskId}/cancel`, { method: "POST" }),
  processPending: () => request<Record<string, unknown>>("/tasks/process-pending", { method: "POST" }),
  create: (kbId: number, type: TaskType, payload: TaskCreateRequest) => request<Task>(`/kbs/${kbId}/tasks/${type}`, { method: "POST", json: payload }),
  createFromBindings: (kbId: number, type: TaskType, payload: BindingTaskCreateRequest) =>
    request<Task>(`/kbs/${kbId}/tasks/${type}-from-bindings`, { method: "POST", json: payload }),
};
