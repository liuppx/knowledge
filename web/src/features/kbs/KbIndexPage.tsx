import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateKbMutation, useKbsQuery } from "../../api/queries/kbs";
import { Badge, DataTable, EmptyState, ErrorState, LoadingState, formatDateTime, useToast } from "../../ui";
import { messageFor } from "../../api/client";

export function KbIndexPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const kbs = useKbsQuery();
  const create = useCreateKbMutation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || create.isPending) return;
    try {
      const kb = await create.mutateAsync({ name: name.trim(), description: description.trim() });
      setName("");
      setDescription("");
      toast.success(`知识库「${kb.name}」已创建`);
      navigate(`/kbs/${kb.id}/overview`);
    } catch (cause) {
      toast.error(messageFor(cause, "创建知识库失败"));
    }
  }

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Knowledge bases</p>
          <h1>知识库</h1>
        </div>
      </header>
      <section className="panel">
        <h2>新建知识库</h2>
        <form className="form-row" onSubmit={submit}>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="名称，例如 Knowledge Product Handbook" aria-label="知识库名称" />
          <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="描述（可选）" aria-label="知识库描述" />
          <button type="submit" className="primary-button" disabled={!name.trim() || create.isPending}>
            {create.isPending ? "正在创建…" : "创建"}
          </button>
        </form>
      </section>
      <section className="panel">
        <h2>全部知识库</h2>
        {kbs.isLoading ? <LoadingState /> : null}
        {kbs.isError ? <ErrorState error={kbs.error} fallback="加载知识库失败" onRetry={() => void kbs.refetch()} /> : null}
        {kbs.data ? (
          <DataTable
            rows={kbs.data}
            rowKey={(kb) => kb.id}
            onRowClick={(kb) => navigate(`/kbs/${kb.id}/overview`)}
            empty={<EmptyState title="还没有知识库" description="先创建一个知识库，再从 Warehouse 绑定目录或上传文件开始导入。" />}
            columns={[
              { key: "name", header: "名称", render: (kb) => <strong>{kb.name}</strong> },
              { key: "description", header: "描述", render: (kb) => <span className="muted">{kb.description || "—"}</span> },
              { key: "status", header: "状态", render: (kb) => <Badge status={kb.status} />, width: "110px" },
              { key: "updated", header: "更新时间", render: (kb) => formatDateTime(kb.updated_at), width: "180px" },
            ]}
          />
        ) : null}
      </section>
    </>
  );
}
