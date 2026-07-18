import { ImagePlus, LoaderCircle, ScanSearch, ShieldCheck, X } from "lucide-react";
import { ChangeEvent, DragEvent, useRef, useState } from "react";

export type ImageQueryCandidate = {
  file: File;
  previewUrl: string;
  source: "device" | "library";
  imageId?: string;
};

type ImageSearchDialogProps = {
  open: boolean;
  candidate: ImageQueryCandidate | null;
  busy: boolean;
  onSelect: (file: File) => void;
  onSearch: () => void;
  onClose: () => void;
};

function fileSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function ImageSearchDialog({
  open,
  candidate,
  busy,
  onSelect,
  onSearch,
  onClose,
}: ImageSearchDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  if (!open) return null;

  function select(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onSelect(file);
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) onSelect(file);
  }

  return (
    <div className="image-search-scrim" role="presentation" onMouseDown={onClose}>
      <section
        aria-label="以图搜图"
        aria-modal="true"
        className="image-search-dialog"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header>
          <div>
            <span><ScanSearch size={17} /> 以图搜图</span>
            <small>上传一张参考图片，查找视觉内容最接近的画面</small>
          </div>
          <button aria-label="关闭" disabled={busy} onClick={onClose}><X size={18} /></button>
        </header>

        <input
          ref={inputRef}
          accept="image/jpeg,image/png,image/webp"
          className="visually-hidden"
          onChange={select}
          type="file"
        />

        {candidate ? (
          <div className="image-query-preview">
            <img alt="查询图片预览" src={candidate.previewUrl} />
            <div>
              <span>{candidate.source === "library" ? "来自当前图库" : "来自你的设备"}</span>
              <strong>{candidate.file.name}</strong>
              <small>{fileSize(candidate.file.size)} · {candidate.file.type.replace("image/", "").toUpperCase()}</small>
              <button disabled={busy} onClick={() => inputRef.current?.click()} type="button">
                更换图片
              </button>
            </div>
          </div>
        ) : (
          <div
            className={`image-dropzone ${dragging ? "dragging" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={drop}
            role="button"
            tabIndex={0}
          >
            <div><ImagePlus size={25} /></div>
            <strong>拖入图片，或点击选择</strong>
            <span>支持 JPEG、PNG、WebP，最大 12 MB</span>
          </div>
        )}

        <div className="image-query-privacy">
          <ShieldCheck size={15} />
          <span>查询图片仅用于本次特征提取，不会加入图库或永久保存。</span>
        </div>

        <footer>
          <button className="image-dialog-cancel" disabled={busy} onClick={onClose}>取消</button>
          <button
            className="image-dialog-submit"
            disabled={!candidate || busy}
            onClick={onSearch}
          >
            {busy ? <LoaderCircle className="spin" size={15} /> : <ScanSearch size={15} />}
            {busy ? "正在分析画面" : "查找相似图片"}
          </button>
        </footer>
      </section>
    </div>
  );
}
