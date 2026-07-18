import type { LibraryItem } from "./types";

export type RelevanceTier = "best" | "high" | "related" | "explore";

export type RelevancePresentation = {
  tier: RelevanceTier;
  label: string;
  strength: number;
};

const TIER_LABELS: Record<RelevanceTier, string> = {
  best: "最佳匹配",
  high: "高度相关",
  related: "相关",
  explore: "延伸结果",
};

export function relevanceFor(
  item: LibraryItem,
  index: number,
  items: LibraryItem[],
): RelevancePresentation | null {
  if (item.score == null) return null;
  const scored = items.filter((candidate) => candidate.score != null);
  const top = scored[0]?.score ?? item.score;
  const bottom = scored.at(-1)?.score ?? item.score;
  const gap = top - item.score;
  const position = index / Math.max(scored.length - 1, 1);

  let tier: RelevanceTier;
  if (index === 0) tier = "best";
  else if (gap <= 0.008 && position <= 0.35) tier = "high";
  else if (gap <= 0.022 && position <= 0.75) tier = "related";
  else tier = "explore";

  const scoreRange = Math.max(top - bottom, 0.0001);
  const relativePosition = (item.score - bottom) / scoreRange;
  const strength = Math.round(58 + Math.max(0, Math.min(1, relativePosition)) * 42);
  return { tier, label: TIER_LABELS[tier], strength };
}

function queryTerms(query: string): string[] {
  const normalized = query.trim().toLocaleLowerCase();
  const latinTerms = normalized.match(/[a-z0-9]{2,}/g) ?? [];
  const cjkTerms = normalized.match(/[\u3400-\u9fff]{1,}/g) ?? [];
  return [...new Set([...latinTerms, ...cjkTerms])];
}

export function filenameEvidence(query: string, items: LibraryItem[]) {
  const terms = queryTerms(query);
  const filenameMatches = terms.length
    ? items.filter((item) => {
        const filename = item.filename.toLocaleLowerCase();
        return terms.some((term) => filename.includes(term));
      }).length
    : 0;
  return {
    filenameMatches,
    semanticOnly: Math.max(0, items.length - filenameMatches),
    total: items.length,
  };
}
