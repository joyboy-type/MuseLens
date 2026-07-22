import type { LibraryItem } from "./types";

export type SmartAlbumDefinition = {
  id: string;
  title: string;
  description: string;
  tags: string[];
};

export type SmartAlbum = SmartAlbumDefinition & {
  count: number;
  cover: LibraryItem;
};

export const SMART_ALBUMS: SmartAlbumDefinition[] = [
  { id: "people", title: "人物", description: "日常与共同记忆", tags: ["person"] },
  { id: "pets", title: "萌宠", description: "猫、狗与动物伙伴", tags: ["dog", "cat", "bird"] },
  {
    id: "travel",
    title: "旅行",
    description: "城市、海岸与远方",
    tags: ["travel", "beach", "mountain", "city", "airplane", "boat"],
  },
  { id: "food", title: "美食", description: "餐桌上的好味道", tags: ["food", "pizza", "cake"] },
  {
    id: "nature",
    title: "自然",
    description: "花卉、森林与山水",
    tags: ["nature", "flower", "forest", "water", "sunset", "snow", "wildlife"],
  },
];

export function buildSmartAlbums(items: LibraryItem[]): SmartAlbum[] {
  return SMART_ALBUMS.flatMap((definition) => {
    const accepted = new Set(definition.tags);
    const matches = items.filter((item) => item.tags.some((tag) => accepted.has(tag.slug)));
    return matches.length ? [{ ...definition, count: matches.length, cover: matches[0] }] : [];
  });
}
