import { useEffect, type ReactNode } from "react";

type Props = {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onCancel}>
      <div className="modal" role="alertdialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <h3>{title}</h3>
        {description ? <div className="muted">{description}</div> : null}
        <div className="modal-actions">
          <button type="button" className="outline-button" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button type="button" className={danger ? "danger-button" : "primary-button"} onClick={onConfirm} disabled={busy}>
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
