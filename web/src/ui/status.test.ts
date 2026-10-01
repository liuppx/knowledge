import { describe, expect, it } from "vitest";

import { statusLabel, toneForStatus } from "./status";

describe("status tones", () => {
  it("mirrors the legacy console task tones", () => {
    expect(toneForStatus("succeeded")).toBe("success");
    expect(toneForStatus("canceled")).toBe("info");
    expect(toneForStatus("failed")).toBe("danger");
    expect(toneForStatus("cancel_requested")).toBe("warning");
    expect(toneForStatus("partial_success")).toBe("warning");
    expect(toneForStatus("pending")).toBe("warning");
  });

  it("covers entity enums and falls back to neutral", () => {
    expect(toneForStatus("published")).toBe("success");
    expect(toneForStatus("source_missing")).toBe("danger");
    expect(toneForStatus("pending_review")).toBe("warning");
    expect(toneForStatus("rolled_back")).toBe("info");
    expect(toneForStatus("something_else")).toBe("neutral");
    expect(toneForStatus(null)).toBe("neutral");
  });

  it("labels known statuses in Chinese and echoes unknown ones", () => {
    expect(statusLabel("running")).toBe("执行中");
    expect(statusLabel("latest_published")).toBe("最新发布");
    expect(statusLabel("custom_state")).toBe("custom_state");
    expect(statusLabel(undefined)).toBe("—");
  });
});
