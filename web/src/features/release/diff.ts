import type { ReleaseItem } from "../../api/endpoints/releases";

export type ReleaseDiff = {
  added: ReleaseItem[];
  removed: ReleaseItem[];
  changed: { before: ReleaseItem; after: ReleaseItem }[];
  unchanged: number;
};

/** Compare two releases by knowledge_item_id; a different revision/version hash counts as changed. */
export function diffReleases(before: ReleaseItem[], after: ReleaseItem[]): ReleaseDiff {
  const beforeById = new Map(before.map((item) => [item.knowledge_item_id, item]));
  const afterById = new Map(after.map((item) => [item.knowledge_item_id, item]));
  const diff: ReleaseDiff = { added: [], removed: [], changed: [], unchanged: 0 };
  for (const item of after) {
    const previous = beforeById.get(item.knowledge_item_id);
    if (!previous) diff.added.push(item);
    else if (previous.knowledge_item_revision_id !== item.knowledge_item_revision_id || previous.item_version_hash !== item.item_version_hash) diff.changed.push({ before: previous, after: item });
    else diff.unchanged += 1;
  }
  for (const item of before) if (!afterById.has(item.knowledge_item_id)) diff.removed.push(item);
  return diff;
}
