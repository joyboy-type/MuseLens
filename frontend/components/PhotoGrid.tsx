import { thumbnailUrl } from "@/lib/api";
import type { LibraryItem } from "@/lib/types";
import { relevanceFor } from "@/lib/relevance";
import { ImageOff, Maximize2 } from "lucide-react";
import { useState } from "react";

type PhotoGridProps = {
  items: LibraryItem[];
  onOpen: (item: LibraryItem) => void;
};

export function PhotoGrid({ items, onOpen }: PhotoGridProps) {
  const [failed, setFailed] = useState<Set<string>>(new Set());

  return (
    <div className="photo-grid" aria-live="polite">
      {items.map((item, index) => {
        const broken = failed.has(item.image_id);
        return (
          <button
            className="photo-card"
            key={item.image_id}
            onClick={() => onOpen(item)}
            aria-label={`查看 ${item.filename}`}
            style={{ animationDelay: `${Math.min(index, 18) * 28}ms` }}
          >
            <span className="photo-frame">
              {broken ? (
                <span className="broken-image">
                  <ImageOff size={25} />
                  图片不可用
                </span>
              ) : (
                <img
                  src={thumbnailUrl(item.image_id, item.session_id)}
                  alt={item.filename}
                  loading="lazy"
                  decoding="async"
                  onError={() =>
                    setFailed((current) => new Set(current).add(item.image_id))
                  }
                />
              )}
              <span className="photo-overlay" aria-hidden="true">
                <span className="photo-name">{item.filename}</span>
                <span className="open-indicator">
                  <Maximize2 size={14} />
                </span>
              </span>
              {item.score != null && (() => {
                const relevance = relevanceFor(item, index, items);
                return relevance && (
                  <span
                    className={`relevance-pill ${relevance.tier}`}
                    title={`模型排序分 ${item.score.toFixed(3)}；该分数仅用于本次查询内排序`}
                  >
                    <i><span style={{ width: `${relevance.strength}%` }} /></i>
                    <b>#{index + 1}</b> {relevance.label}
                  </span>
                );
              })()}
              {item.tags.length > 0 && (
                <span className="photo-tags" aria-label="AI 自动标签">
                  {item.tags.slice(0, 2).map((tag) => (
                    <i key={tag.slug}>{tag.label}</i>
                  ))}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}
