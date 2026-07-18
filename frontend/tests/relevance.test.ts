import { describe, expect, it } from "vitest";
import { filenameEvidence, relevanceFor } from "../lib/relevance";
import type { LibraryItem } from "../lib/types";

function item(imageId: string, filename: string, score: number): LibraryItem {
  return {
    image_id: imageId,
    filename,
    content_type: "image/jpeg",
    width: 500,
    height: 320,
    size_bytes: 1000,
    created_at: "2026-07-01T00:00:00Z",
    score,
  };
}

describe("relevance presentation", () => {
  it("uses query-relative labels instead of treating cosine score as probability", () => {
    const items = [item("1", "one.jpg", 0.12), item("2", "two.jpg", 0.114)];

    expect(relevanceFor(items[0], 0, items)?.label).toBe("最佳匹配");
    expect(relevanceFor(items[1], 1, items)?.label).not.toBe("最佳匹配");
  });

  it("counts results recovered without filename keyword matches", () => {
    const items = [item("1", "12345.jpg", 0.12), item("2", "dog-at-park.jpg", 0.11)];

    expect(filenameEvidence("dog", items)).toEqual({
      filenameMatches: 1,
      semanticOnly: 1,
      total: 2,
    });
  });
});
