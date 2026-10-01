import { useNavigate } from "react-router-dom";

import { useKbsQuery } from "../api/queries/kbs";

type Props = { kbId: number | null; section: string };

/** Switches KB while staying in the same workbench section. */
export function KbSwitcher({ kbId, section }: Props) {
  const navigate = useNavigate();
  const kbs = useKbsQuery();
  const items = kbs.data ?? [];

  return (
    <label className="kb-switcher">
      <span className="eyebrow">当前知识库</span>
      <select
        aria-label="选择知识库"
        value={kbId ?? ""}
        disabled={kbs.isLoading}
        onChange={(event) => {
          const value = event.target.value;
          if (value === "__manage__") navigate("/kbs");
          else if (value) navigate(`/kbs/${value}/${section}`);
        }}
      >
        {kbId === null ? <option value="">未选择</option> : null}
        {items.map((kb) => (
          <option key={kb.id} value={kb.id}>
            {kb.name}
          </option>
        ))}
        <option value="__manage__">管理知识库…</option>
      </select>
    </label>
  );
}
