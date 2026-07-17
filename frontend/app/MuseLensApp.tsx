"use client";

import { PhotoGrid } from "@/components/PhotoGrid";
import { SearchBar } from "@/components/SearchBar";
import {
  createImportJob,
  getHealth,
  getImportJob,
  getLatestImportJob,
  imageUrl,
  listImages,
  retryImportJob,
  searchImages,
} from "@/lib/api";
import type { Health, ImportJob, LibraryItem } from "@/lib/types";
import {
  Check,
  ChevronRight,
  CloudOff,
  FolderOpen,
  Images,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  Search,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

const SUGGESTIONS = ["户外的人", "一只狗", "蓝色天空", "运动场景"];

export function MuseLensApp() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importJob, setImportJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const searchRequestRef = useRef(0);
  const importActive =
    uploading || importJob?.status === "queued" || importJob?.status === "running";
  const activeJobId = importJob?.job_id;
  const activeJobStatus = importJob?.status;

  const refreshLibrary = useCallback(async () => {
    const [library, status] = await Promise.all([listImages(), getHealth()]);
    setItems(library);
    setHealth(status);
  }, []);

  useEffect(() => {
    Promise.allSettled([listImages(), getHealth(), getLatestImportJob()]).then(
      ([library, status, latestJob]) => {
        if (library.status === "fulfilled") setItems(library.value);
        if (status.status === "fulfilled") setHealth(status.value);
        if (latestJob.status === "fulfilled") setImportJob(latestJob.value);
        const failed = [library, status].find((result) => result.status === "rejected");
        if (failed?.status === "rejected") {
          setError(failed.reason instanceof Error ? failed.reason.message : "本地服务连接失败");
        }
      },
    );
    fileRef.current?.setAttribute("webkitdirectory", "");
    fileRef.current?.setAttribute("directory", "");
  }, []);

  useEffect(() => {
    if (!activeJobId || !activeJobStatus || !["queued", "running"].includes(activeJobStatus)) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const next = await getImportJob(activeJobId);
        if (cancelled) return;
        setImportJob(next);
        if (["queued", "running"].includes(next.status)) {
          timer = setTimeout(poll, 800);
          return;
        }
        setUploading(false);
        setActiveQuery("");
        setQuery("");
        await refreshLibrary();
        if (next.status === "completed") {
          setNotice(
            `导入完成：新增 ${next.imported_files} 张，跳过 ${next.duplicate_files} 张重复图片`,
          );
        } else {
          setError(next.error ?? "部分图片处理失败，可以重试");
        }
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "无法读取导入进度");
          timer = setTimeout(poll, 1600);
        }
      }
    }

    timer = setTimeout(poll, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [activeJobId, activeJobStatus, refreshLibrary]);

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape") setSelected(null);
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  async function runSearch(nextQuery = query) {
    const normalized = nextQuery.trim();
    if (!normalized) return;
    setBusy(true);
    const requestId = ++searchRequestRef.current;
    setError("");
    setActiveQuery(normalized);
    try {
      const [results, status] = await Promise.all([searchImages(normalized), getHealth()]);
      if (requestId !== searchRequestRef.current) return;
      setItems(results);
      setHealth(status);
    } catch (reason) {
      if (requestId === searchRequestRef.current) {
        setError(reason instanceof Error ? reason.message : "搜索失败");
      }
    } finally {
      if (requestId === searchRequestRef.current) setBusy(false);
    }
  }

  async function clearSearch() {
    searchRequestRef.current += 1;
    setQuery("");
    setActiveQuery("");
    setBusy(true);
    try {
      await refreshLibrary();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleFolder(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []).filter((file) =>
      ["image/jpeg", "image/png", "image/webp"].includes(file.type),
    );
    event.target.value = "";
    if (!files.length) {
      setNotice("所选文件夹中没有支持的图片");
      return;
    }
    setUploading(true);
    setError("");
    setNotice(`正在安全暂存 ${files.length} 张图片…`);
    try {
      const job = await createImportJob(files);
      setImportJob(job);
      setNotice(`后台任务已创建，正在处理 ${job.total_files} 张图片`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导入失败");
      setUploading(false);
    }
  }

  async function retryJob() {
    if (!importJob) return;
    setError("");
    setNotice("正在重新处理失败的图片…");
    try {
      setImportJob(await retryImportJob(importJob.job_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重试失败");
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-mark" aria-label="MuseLens">
          <Sparkles size={21} />
        </div>
        <nav>
          <button className="nav-button active" aria-label="图片库" title="图片库">
            <Images size={20} />
          </button>
          <button className="nav-button" onClick={() => searchRef.current?.focus()} aria-label="搜索" title="搜索">
            <Search size={20} />
          </button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="privacy-dot" title="所有数据均保存在本机">
          <LockKeyhole size={16} />
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="wordmark">
            <span>MuseLens</span>
            <small>LOCAL AI GALLERY</small>
          </div>
          <SearchBar
            value={query}
            onChange={setQuery}
            onSubmit={() => runSearch()}
            onClear={clearSearch}
            inputRef={searchRef}
            busy={busy}
          />
          <input
            ref={fileRef}
            className="visually-hidden"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            onChange={handleFolder}
          />
          <button className="import-button" onClick={() => fileRef.current?.click()} disabled={importActive}>
            {importActive ? <LoaderCircle className="spin" size={17} /> : <FolderOpen size={17} />}
            <span>{importActive ? "后台索引中" : "导入文件夹"}</span>
          </button>
        </header>

        <div className="content-wrap">
          <section className="hero-row">
            <div>
              <div className="eyebrow">
                {activeQuery ? "SEMANTIC RESULTS" : "YOUR PRIVATE LIBRARY"}
              </div>
              <h1>{activeQuery ? `“${activeQuery}”` : "用语言，重新发现照片"}</h1>
              <p>
                {activeQuery
                  ? `按语义相关度展示 ${items.length} 个结果`
                  : "无需标签或整理文件名，描述你记得的画面即可。"}
              </p>
            </div>
            <div className="status-cluster">
              <span className="status-chip">
                <span className={health ? "live-dot" : "live-dot offline"} />
                {health ? "本地服务在线" : "正在连接"}
              </span>
              <span className="count-chip">{health?.indexed_images ?? items.length} 张已索引</span>
            </div>
          </section>

          {!activeQuery && items.length > 0 && (
            <div className="suggestion-row" aria-label="搜索建议">
              <span>快速探索</span>
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => {
                    setQuery(suggestion);
                    runSearch(suggestion);
                  }}
                >
                  {suggestion}<ChevronRight size={13} />
                </button>
              ))}
            </div>
          )}

          {(error || notice) && (
            <div className={error ? "message error" : "message success"} role="status">
              {error ? <CloudOff size={17} /> : <Check size={17} />}
              <span>{error || notice}</span>
              <button onClick={() => { setError(""); setNotice(""); }} aria-label="关闭消息">
                <X size={15} />
              </button>
            </div>
          )}

          {importJob && (
            <section className={`import-progress ${importJob.status}`} aria-live="polite">
              <div className="import-progress-icon">
                {importActive ? (
                  <LoaderCircle className="spin" size={18} />
                ) : importJob.status === "completed" ? (
                  <Check size={18} />
                ) : (
                  <CloudOff size={18} />
                )}
              </div>
              <div className="import-progress-body">
                <div className="import-progress-title">
                  <strong>
                    {importActive
                      ? "正在后台建立图片索引"
                      : importJob.status === "completed"
                        ? "图片索引已完成"
                        : "部分图片需要重新处理"}
                  </strong>
                  <span>{importJob.processed_files} / {importJob.total_files}</span>
                </div>
                <div className="progress-track" aria-label="导入进度">
                  <span
                    style={{
                      width: `${Math.round(
                        (importJob.processed_files / Math.max(importJob.total_files, 1)) * 100,
                      )}%`,
                    }}
                  />
                </div>
                <div className="import-progress-meta">
                  <span>新增 {importJob.imported_files}</span>
                  <span>重复 {importJob.duplicate_files}</span>
                  <span>失败 {importJob.failed_files}</span>
                </div>
              </div>
              {(importJob.status === "failed" || importJob.status === "partial") && (
                <button className="retry-button" onClick={retryJob}>
                  <RotateCcw size={14} /> 重试
                </button>
              )}
              {!importActive && importJob.status === "completed" && (
                <button
                  className="dismiss-job"
                  onClick={() => setImportJob(null)}
                  aria-label="收起导入进度"
                >
                  <X size={15} />
                </button>
              )}
            </section>
          )}

          {busy ? (
            <div className="loading-state">
              <LoaderCircle className="spin" size={25} />
              <span>正在理解你的描述…</span>
            </div>
          ) : items.length ? (
            <PhotoGrid items={items} onOpen={setSelected} />
          ) : (
            <section className="empty-state">
              <div className="empty-icon">{activeQuery ? <Search size={25} /> : <Upload size={25} />}</div>
              <h2>
                {error
                  ? "暂时无法读取图片库"
                  : activeQuery
                    ? "没有足够相关的图片"
                    : "从一个图片文件夹开始"}
              </h2>
              <p>
                {activeQuery
                  ? "系统不会为了凑数返回低相关结果。当前模型优先支持英文描述，可以尝试更具体的查询。"
                  : "图片只会复制到 MuseLens 专用目录，原始文件不会被移动或修改。"}
              </p>
              {activeQuery ? (
                <button onClick={clearSearch}><X size={17} /> 清除搜索</button>
              ) : (
                <button onClick={() => fileRef.current?.click()} disabled={importActive}>
                  <FolderOpen size={17} /> 选择图片文件夹
                </button>
              )}
            </section>
          )}
        </div>
      </section>

      {selected && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label={selected.filename} onClick={() => setSelected(null)}>
          <button className="lightbox-close" onClick={() => setSelected(null)} aria-label="关闭预览">
            <X size={20} />
          </button>
          <div className="lightbox-content" onClick={(event) => event.stopPropagation()}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={imageUrl(selected.image_id)} alt={selected.filename} />
            <div className="lightbox-meta">
              <div>
                <span>本地图片</span>
                <strong>{selected.filename}</strong>
              </div>
              {selected.score !== undefined && (
                <span className="lightbox-score">语义相似度 {selected.score.toFixed(3)}</span>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
