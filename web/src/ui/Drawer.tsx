import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

type Props = {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
};

export function Drawer({ open, title, onClose, children, footer, width = 560 }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" style={{ width: `min(100%, ${width}px)` }} onClick={(event) => event.stopPropagation()}>
        <header className="drawer-header">
          <h3>{title}</h3>
          <button type="button" className="icon-button" aria-label="关闭" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <div className="drawer-body">{children}</div>
        {footer ? <footer className="drawer-footer">{footer}</footer> : null}
      </aside>
    </div>
  );
}
