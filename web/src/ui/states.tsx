import type { ReactNode } from "react";

import { messageFor } from "../api/client";

/** Empty states must tell the user what to do next (产品验证知识库 §5). */
export function EmptyState({ title, description, action }: { title: ReactNode; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-icon" aria-hidden="true">
        ∅
      </div>
      <p>
        <strong>{title}</strong>
      </p>
      {description ? <div className="muted">{description}</div> : null}
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function LoadingState({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="state-row muted" role="status">
      {label}
    </div>
  );
}

export function ErrorState({ error, fallback = "加载失败", onRetry }: { error: unknown; fallback?: string; onRetry?: () => void }) {
  return (
    <div className="alert" role="alert">
      <span>{messageFor(error, fallback)}</span>
      {onRetry ? (
        <button type="button" className="outline-button" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}
