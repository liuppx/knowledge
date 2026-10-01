import { useEffect, useMemo, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { isTaskActive, tasksApi, type BindingTaskCreateRequest, type Task, type TaskCreateRequest, type TaskType } from "../endpoints/tasks";
import { documentKeys } from "./documents";
import { kbKeys } from "./kbs";
import { sourceKeys } from "./sources";
import { warehouseKeys } from "./warehouse";

// Same cadence as the legacy console (TASK_POLL_INTERVAL_MS).
export const TASK_POLL_INTERVAL_MS = 3000;

export const taskKeys = {
  list: ["tasks"] as const,
  items: (taskId: number) => ["tasks", taskId, "items"] as const,
};

/** All of the wallet's tasks; polls while any task is active. */
export function useTasksQuery() {
  return useQuery({
    queryKey: taskKeys.list,
    queryFn: tasksApi.list,
    refetchInterval: (query) => (query.state.data?.some((task) => isTaskActive(task.status)) ? TASK_POLL_INTERVAL_MS : false),
  });
}

/** Tasks for one KB, newest first, plus the queries that must refresh when one settles. */
export function useKbTasks(kbId: number) {
  const tasks = useTasksQuery();
  const client = useQueryClient();
  const kbTasks = useMemo(() => (tasks.data ?? []).filter((task) => task.kb_id === kbId).sort((a, b) => b.id - a.id), [tasks.data, kbId]);
  const previous = useRef<Map<number, string>>(new Map());

  useEffect(() => {
    const settled = kbTasks.some((task) => {
      const before = previous.current.get(task.id);
      return before !== undefined && isTaskActive(before) && !isTaskActive(task.status);
    });
    previous.current = new Map(kbTasks.map((task) => [task.id, task.status]));
    if (!settled) return;
    // A finished import/reindex/delete changes documents, bindings and KB stats.
    void client.invalidateQueries({ queryKey: documentKeys.list(kbId) });
    void client.invalidateQueries({ queryKey: warehouseKeys.bindings(kbId) });
    void client.invalidateQueries({ queryKey: sourceKeys.list(kbId) });
    void client.invalidateQueries({ queryKey: kbKeys.stats(kbId) });
    void client.invalidateQueries({ queryKey: kbKeys.workbench(kbId) });
  }, [kbTasks, kbId, client]);

  return { ...tasks, kbTasks, hasActive: kbTasks.some((task) => isTaskActive(task.status)) };
}

export function useTaskItemsQuery(taskId: number | null, active = false) {
  return useQuery({
    queryKey: taskKeys.items(taskId ?? 0),
    queryFn: () => tasksApi.items(taskId as number),
    enabled: taskId !== null,
    refetchInterval: active ? TASK_POLL_INTERVAL_MS : false,
  });
}

function useAfterTaskChange() {
  const client = useQueryClient();
  return (task: Task) => {
    void client.invalidateQueries({ queryKey: taskKeys.list });
    void client.invalidateQueries({ queryKey: kbKeys.workbench(task.kb_id) });
  };
}

export function useCreateTaskMutation(kbId: number) {
  const after = useAfterTaskChange();
  return useMutation({
    mutationFn: ({ type, payload }: { type: TaskType; payload: TaskCreateRequest }) => tasksApi.create(kbId, type, payload),
    onSuccess: after,
  });
}

export function useCreateTaskFromBindingsMutation(kbId: number) {
  const after = useAfterTaskChange();
  return useMutation({
    mutationFn: ({ type, payload }: { type: TaskType; payload: BindingTaskCreateRequest }) => tasksApi.createFromBindings(kbId, type, payload),
    onSuccess: after,
  });
}

export function useRetryTaskMutation() {
  const after = useAfterTaskChange();
  return useMutation({ mutationFn: (taskId: number) => tasksApi.retry(taskId), onSuccess: after });
}

export function useCancelTaskMutation() {
  const after = useAfterTaskChange();
  return useMutation({ mutationFn: (taskId: number) => tasksApi.cancel(taskId), onSuccess: after });
}

export function useProcessPendingMutation() {
  const client = useQueryClient();
  return useMutation({ mutationFn: () => tasksApi.processPending(), onSuccess: () => client.invalidateQueries({ queryKey: taskKeys.list }) });
}
