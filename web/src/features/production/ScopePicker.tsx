import { useMemo, useState } from "react";

import type { Scope } from "../../api/endpoints/production";
import { useAllAssetsQuery, useSourcesQuery } from "../../api/queries/sources";

type Props = { kbId: number; value: Scope | null; onChange: (scope: Scope | null) => void };

/** Source / asset selector shared by evidence building and candidate generation. */
export function ScopePicker({ kbId, value, onChange }: Props) {
  const sources = useSourcesQuery(kbId);
  const assets = useAllAssetsQuery(kbId);
  const [sourceId, setSourceId] = useState<number | null>(value?.kind === "source" ? value.id : null);
  const assetOptions = useMemo(() => (assets.data ?? []).filter((asset) => sourceId === null || asset.source_id === sourceId), [assets.data, sourceId]);

  return (
    <div className="scope-picker">
      <select
        aria-label="来源"
        value={sourceId ?? ""}
        onChange={(event) => {
          const id = event.target.value ? Number(event.target.value) : null;
          setSourceId(id);
          onChange(id ? { kind: "source", id } : null);
        }}
      >
        <option value="">全部来源</option>
        {(sources.data ?? []).map((source) => (
          <option key={source.id} value={source.id}>
            {source.source_path}
          </option>
        ))}
      </select>
      <select
        aria-label="资产"
        value={value?.kind === "asset" ? value.id : ""}
        onChange={(event) => {
          const id = event.target.value ? Number(event.target.value) : null;
          onChange(id ? { kind: "asset", id } : sourceId ? { kind: "source", id: sourceId } : null);
        }}
      >
        <option value="">{sourceId ? "该来源全部资产" : "全部资产"}</option>
        {assetOptions.map((asset) => (
          <option key={asset.id} value={asset.id}>
            {asset.asset_name} · {asset.availability_status}
          </option>
        ))}
      </select>
    </div>
  );
}
