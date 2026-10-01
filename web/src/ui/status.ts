export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

// Mapping of backend status literals (knowledge/models/entities.py constants plus task
// queue states) to a visual tone. Mirrors the legacy console's toneForTaskStatus /
// toneForTaskItemStatus so the port reads the same at a glance.
const TONES: Record<Tone, readonly string[]> = {
  success: [
    "succeeded", "indexed", "deleted", "synced", "available", "published", "active", "completed",
    "accepted", "confirmed", "ok", "healthy", "final", "configured", "enabled", "parsed", "done",
  ],
  danger: ["failed", "missing", "rejected", "revoked", "revoked_local", "invalid", "error", "source_missing", "cancel_failed"],
  warning: [
    "pending", "running", "cancel_requested", "partial_success", "syncing", "pending_sync", "pending_review",
    "changed", "missing_unconfirmed", "draft", "ready_for_review", "preparing", "queued", "expired", "suspended",
    "stale", "mock-or-not-configured", "processing", "uploading",
  ],
  info: ["canceled", "cancelled", "rolled_back", "skipped", "superseded", "archived", "merged", "discovered", "ignored", "hotfix", "disabled"],
  neutral: [],
};

const LABELS: Record<string, string> = {
  pending: "排队中",
  running: "执行中",
  cancel_requested: "取消中",
  canceled: "已取消",
  cancelled: "已取消",
  succeeded: "成功",
  failed: "失败",
  partial_success: "部分成功",
  indexed: "已索引",
  deleted: "已删除",
  skipped: "已跳过",
  rolled_back: "已回退",
  pending_sync: "待同步",
  syncing: "同步中",
  synced: "已同步",
  source_missing: "来源缺失",
  disabled: "已禁用",
  enabled: "已启用",
  discovered: "已发现",
  available: "可用",
  changed: "已变更",
  missing: "缺失",
  missing_unconfirmed: "疑似缺失",
  ignored: "已忽略",
  pending_review: "待审核",
  accepted: "已接受",
  rejected: "已拒绝",
  merged: "已合并",
  candidate: "候选",
  confirmed: "已确认",
  archived: "已归档",
  draft: "草稿",
  ready_for_review: "待评审",
  active: "生效",
  hotfix: "热修",
  preparing: "准备中",
  published: "已发布",
  superseded: "已被取代",
  expired: "已过期",
  suspended: "已暂停",
  revoked: "已吊销",
  revoked_local: "本地已吊销",
  invalid: "无效",
  queued: "已排队",
  completed: "已完成",
  stale: "过期",
  error: "错误",
  ok: "正常",
  healthy: "健康",
  configured: "已配置",
  "mock-or-not-configured": "未配置（mock）",
  latest_published: "最新发布",
  pinned_release: "固定版本",
  read: "读凭证",
  read_write: "写凭证",
};

export function toneForStatus(status: string | null | undefined): Tone {
  const value = String(status ?? "").toLowerCase();
  for (const tone of ["success", "danger", "warning", "info"] as const) {
    if (TONES[tone].includes(value)) return tone;
  }
  return "neutral";
}

export function statusLabel(status: string | null | undefined): string {
  if (status === null || status === undefined || status === "") return "—";
  return LABELS[String(status).toLowerCase()] ?? String(status);
}
