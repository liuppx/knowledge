import { useState } from "react";

import { messageFor } from "../../api/client";
import type { KnowledgeBase } from "../../api/endpoints/kbs";
import { useDeleteKbMutation } from "../../api/queries/kbs";
import { forgetKbId } from "../../app/lastKb";
import { ConfirmDialog, Drawer, useToast } from "../../ui";
import { KbSettingsForm } from "./KbSettingsForm";

type Props = {
  editing: KnowledgeBase | null;
  deleting: KnowledgeBase | null;
  onClose: () => void;
  onDeleted?: (kb: KnowledgeBase) => void;
};

/** Shared edit drawer + delete confirmation used by the KB list and the overview page. */
export function KbManageDialogs({ editing, deleting, onClose, onDeleted }: Props) {
  const toast = useToast();
  const remove = useDeleteKbMutation();
  const [busy, setBusy] = useState(false);

  async function confirmDelete() {
    if (!deleting || busy) return;
    setBusy(true);
    try {
      await remove.mutateAsync(deleting.id);
      forgetKbId(deleting.id);
      toast.success(`知识库「${deleting.name}」已删除`);
      onDeleted?.(deleting);
      onClose();
    } catch (cause) {
      toast.error(messageFor(cause, "删除失败"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Drawer open={editing !== null} title={editing ? `编辑 ${editing.name}` : ""} onClose={onClose}>
        {editing ? <KbSettingsForm key={editing.id} kb={editing} onSaved={onClose} onCancel={onClose} /> : null}
      </Drawer>
      <ConfirmDialog
        open={deleting !== null}
        title={`删除知识库「${deleting?.name ?? ""}」？`}
        description="将移除其来源、文档、Evidence、知识项、发布版本与授权，且不可恢复。依赖该知识库的消费方会立刻失去访问。"
        confirmLabel="删除"
        danger
        busy={busy}
        onConfirm={() => void confirmDelete()}
        onCancel={onClose}
      />
    </>
  );
}
