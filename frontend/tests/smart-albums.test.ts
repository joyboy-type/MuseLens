import { describe, expect, it } from "vitest";
import { buildSmartAlbums } from "../lib/smart-albums";
import type { LibraryItem } from "../lib/types";

function item(image_id: string, tags: string[]): LibraryItem {
  return {
    image_id,
    filename: `${image_id}.jpg`,
    content_type: "image/jpeg",
    width: 100,
    height: 100,
    size_bytes: 10,
    created_at: "2026-07-22T00:00:00Z",
    tags: tags.map((slug) => ({ slug, label: slug, score: 1, source: "auto" })),
  };
}

describe("smart albums", () => {
  it("only exposes non-empty albums and counts each matching image once", () => {
    const albums = buildSmartAlbums([
      item("one", ["dog", "cat"]),
      item("two", ["cat"]),
      item("three", ["beach"]),
    ]);

    expect(albums.map(({ id, count }) => ({ id, count }))).toEqual([
      { id: "pets", count: 2 },
      { id: "travel", count: 1 },
    ]);
  });
});
