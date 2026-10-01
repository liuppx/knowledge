import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import type { Tone } from "./status";

type Toast = { id: number; message: string; tone: Tone };
type ToastApi = {
  notify: (message: string, tone?: Tone) => void;
  success: (message: string) => void;
  error: (message: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);
const DISMISS_MS = 4500;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((current) => current.filter((toast) => toast.id !== id)), []);
  const notify = useCallback(
    (message: string, tone: Tone = "info") => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, message, tone }]);
      window.setTimeout(() => dismiss(id), DISMISS_MS);
    },
    [dismiss],
  );
  const api = useMemo<ToastApi>(
    () => ({ notify, success: (message) => notify(message, "success"), error: (message) => notify(message, "danger") }),
    [notify],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.tone}`}>
            <span>{toast.message}</span>
            <button type="button" className="toast-close" aria-label="关闭" onClick={() => dismiss(toast.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used within ToastProvider");
  return api;
}
