import { useState } from "react";
import { Link } from "react-router-dom";

import type { SearchHit } from "../../api/endpoints/search";
import { Badge } from "../../ui";

function highlight(text: string, query: string) {
  const needle = query.trim();
  if (!needle) return text;
  const index = text.toLowerCase().indexOf(needle.toLowerCase());
  if (index < 0) return text;
  return (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, index + needle.length)}</mark>
      {text.slice(index + needle.length)}
    </>
  );
}

/** One search hit with its provenance chain: item/evidence links, sources, health, audit info. */
export function HitCard({ hit, kbId, query }: { hit: SearchHit; kbId: number; query: string }) {
  const [showAudit, setShowAudit] = useState(false);
  const isFormal = hit.result_kind === "formal" || hit.knowledge_item_id != null;
  const body = isFormal ? hit.statement : hit.text;
  const audit = hit.audit_info ?? {};

  return (
    <article className="hit">
      <header className="hit-header">
        <Badge tone={isFormal ? "info" : "neutral"}>{isFormal ? "正式知识" : "Evidence"}</Badge>
        <span className="mono muted">score {hit.score.toFixed(3)}</span>
        <Badge status={hit.content_health_status} title="内容健康" />
        {hit.source_health_summary && hit.source_health_summary !== hit.content_health_status ? <Badge status={hit.source_health_summary} title="来源健康" /> : null}
      </header>
      {isFormal ? (
        <h4>
          <Link to={`/kbs/${kbId}/production?item=${hit.knowledge_item_id}`}>{hit.title || `知识项 #${hit.knowledge_item_id}`}</Link>
          {hit.item_type ? <span className="muted"> · {hit.item_type}</span> : null}
        </h4>
      ) : (
        <h4>
          <Link to={`/kbs/${kbId}/production?evidence=${hit.evidence_id}`}>Evidence #{hit.evidence_id}</Link>
          {hit.evidence_type ? <span className="muted"> · {hit.evidence_type}</span> : null}
        </h4>
      )}
      {body ? <p className="hit-body">{highlight(body, query)}</p> : null}
      {hit.evidence_summaries?.length ? (
        <ul className="hit-evidence">
          {hit.evidence_summaries.map((summary) => (
            <li key={summary.evidence_id}>
              <Link to={`/kbs/${kbId}/production?evidence=${summary.evidence_id}`}>#{summary.evidence_id}</Link> <span>{summary.text_excerpt}</span>
              <span className="muted mono"> {summary.source_ref}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {hit.source_refs?.length ? (
        <p className="muted mono hit-sources" title={hit.source_refs.join("\n")}>
          {hit.source_refs.join(" · ")}
        </p>
      ) : null}
      {hit.source_health_details?.length ? (
        <ul className="hit-health">
          {hit.source_health_details.map((detail, index) => (
            <li key={`${detail.asset_path}-${index}`}>
              <Badge status={detail.availability_status} />
              <span className="mono ellipsis">{detail.asset_path}</span>
              {detail.asset_id ? (
                <Link className="text-link" to={`/kbs/${kbId}/assets?tab=sources`}>
                  资产 #{detail.asset_id}
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {Object.keys(audit).length ? (
        <>
          <button type="button" className="text-link as-button" onClick={() => setShowAudit((value) => !value)}>
            {showAudit ? "收起排序依据" : "查看排序依据"}
          </button>
          {showAudit ? <pre className="pre-json">{JSON.stringify(audit, null, 2)}</pre> : null}
        </>
      ) : null}
    </article>
  );
}
