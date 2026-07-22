import type { SearchFilters } from "./types";

export const EMPTY_FILTERS: SearchFilters = {
  contentTypes: [],
  orientations: [],
  tags: [],
  minWidth: null,
  maxSizeMB: null,
  datePreset: "all",
  sort: "relevance",
};

export function activeFilterCount(filters: SearchFilters): number {
  return (
    filters.contentTypes.length +
    filters.orientations.length +
    filters.tags.length +
    Number(filters.minWidth !== null) +
    Number(filters.maxSizeMB !== null) +
    Number(filters.datePreset !== "all") +
    Number(filters.sort !== "relevance")
  );
}
