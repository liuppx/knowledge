import type { ReactNode } from "react";

import { statusLabel, toneForStatus, type Tone } from "./status";

type Props = {
  /** Backend status literal; label and tone are derived unless overridden. */
  status?: string | null;
  tone?: Tone;
  children?: ReactNode;
  title?: string;
};

export function Badge({ status, tone, children, title }: Props) {
  const resolvedTone = tone ?? toneForStatus(status);
  return (
    <span className={`badge badge-${resolvedTone}`} title={title ?? (status ?? undefined)} data-status={status ?? undefined}>
      {children ?? statusLabel(status)}
    </span>
  );
}
