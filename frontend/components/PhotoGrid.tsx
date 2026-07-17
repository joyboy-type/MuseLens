import { thumbnailUrl } from "@/lib/api";
import type { LibraryItem } from "@/lib/types";
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
                  src={thumbnailUrl(item.image_id)}
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
              {item.score !== undefined && (
                <span className="score-pill">相似度 {item.score.toFixed(3)}</span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}
