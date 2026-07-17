import { PhotoGrid } from "@/components/PhotoGrid";
import { SearchBar } from "@/components/SearchBar";
import {
  createTemporaryGallery,
  createImportJob,
  deleteTemporaryGallery,
  getHealth,
  getImportJob,
  getLatestImportJob,
  getTemporaryGallery,
  imageUrl,
  listImages,
  listTemporaryGalleryImages,
  retryImportJob,
  searchImages,
  searchTemporaryGallery,
} from "@/lib/api";
import type { Health, ImportJob, LibraryItem, TemporaryGallery } from "@/lib/types";
import {
  Check,
  ChevronRight,
  Clock3,
  CloudOff,
  FolderOpen,
  Images,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

const SUGGESTIONS = ["户外的人", "一只狗", "蓝色天空", "运动场景"];
const TEMPORARY_SESSION_KEY = "muselens-temporary-gallery";

export function MuseLensApp() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importJob, setImportJob] = useState<ImportJob | null>(null);
  const [temporaryGallery, setTemporaryGallery] = useState<TemporaryGallery | null>(null);
  const [galleryMode, setGalleryMode] = useState<"curated" | "temporary">("curated");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const searchRequestRef = useRef(0);
  const importActive =
    uploading ||
    importJob?.status === "queued" ||
    importJob?.status === "running" ||
    temporaryGallery?.status === "queued" ||
    temporaryGallery?.status === "running";
  const libraryWritable = health?.library_writable === true;
  const demoMode = health?.mode === "demo";
  const temporaryEnabled = health?.temporary_galleries_enabled === true;
  const temporaryActive = galleryMode === "temporary";
  const activeJobId = importJob?.job_id;
  const activeJobStatus = importJob?.status;
  const temporarySessionId = temporaryGallery?.session_id;
  const temporaryStatus = temporaryGallery?.status;

  const refreshLibrary = useCallback(async () => {
    const [library, status] = await Promise.all([listImages(), getHealth()]);
    setItems(library);
    setHealth(status);
  }, []);

  useEffect(() => {
    Promise.allSettled([listImages(), getHealth()]).then(
      async ([library, status]) => {
        if (library.status === "fulfilled") setItems(library.value);
        if (status.status === "fulfilled") {
          setHealth(status.value);
          if (status.value.library_writable) {
            const latestJob = await getLatestImportJob().catch(() => null);
            setImportJob(latestJob);
          } else if (status.value.temporary_galleries_enabled) {
            const sessionId = sessionStorage.getItem(TEMPORARY_SESSION_KEY);
            if (sessionId) {
              try {
                const temporary = await getTemporaryGallery(sessionId);
                setTemporaryGallery(temporary);
                setGalleryMode("temporary");
                if (["completed", "partial"].includes(temporary.status)) {
                  setItems(await listTemporaryGalleryImages(sessionId));
                }
              } catch {
                sessionStorage.removeItem(TEMPORARY_SESSION_KEY);
              }
            }
          }
        }
        const failed = [library, status].find((result) => result.status === "rejected");
        if (failed?.status === "rejected") {
          setError(failed.reason instanceof Error ? failed.reason.message : "本地服务连接失败");
        }
      },
    );
  }, []);

  useEffect(() => {
    const input = fileRef.current;
    if (!input) return;
    if (libraryWritable) {
      input.setAttribute("webkitdirectory", "");
      input.setAttribute("directory", "");
    } else {
      input.removeAttribute("webkitdirectory");
      input.removeAttribute("directory");
    }
  }, [libraryWritable, temporaryEnabled]);

  useEffect(() => {
    if (!activeJobId || !activeJobStatus || !["queued", "running"].includes(activeJobStatus)) {
      return;
    }
    const jobId = activeJobId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const next = await getImportJob(jobId);
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
    if (
      !temporarySessionId ||
      !temporaryStatus ||
      !["queued", "running"].includes(temporaryStatus)
    ) {
      return;
    }
    const sessionId = temporarySessionId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function pollTemporaryGallery() {
      try {
        const next = await getTemporaryGallery(sessionId);
        if (cancelled) return;
        setTemporaryGallery(next);
        if (["queued", "running"].includes(next.status)) {
          timer = setTimeout(pollTemporaryGallery, 900);
          return;
        }
        setUploading(false);
        if (["completed", "partial"].includes(next.status)) {
          setItems(await listTemporaryGalleryImages(sessionId));
          setNotice(
            `临时索引完成：可搜索 ${next.imported_files} 张，重复 ${next.duplicate_files} 张`,
          );
        } else {
          setError(next.error ?? "临时图库建立失败");
        }
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "无法读取临时图库进度");
          sessionStorage.removeItem(TEMPORARY_SESSION_KEY);
          setTemporaryGallery(null);
          setUploading(false);
        }
      }
    }

    timer = setTimeout(pollTemporaryGallery, 600);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [temporarySessionId, temporaryStatus]);

  useEffect(() => {
    if (
      !temporaryGallery ||
      ["queued", "running"].includes(temporaryGallery.status)
    ) {
      return;
    }
    const sessionId = temporaryGallery.session_id;
    const delay = Math.max(0, Date.parse(temporaryGallery.expires_at) - Date.now());
    const timer = window.setTimeout(async () => {
      if (sessionStorage.getItem(TEMPORARY_SESSION_KEY) !== sessionId) return;
      sessionStorage.removeItem(TEMPORARY_SESSION_KEY);
      setTemporaryGallery(null);
      setGalleryMode("curated");
      setQuery("");
      setActiveQuery("");
      setItems(await listImages().catch(() => []));
      setNotice("临时图库已到期并自动清除");
    }, Math.min(delay, 2_147_483_647));
    return () => window.clearTimeout(timer);
  }, [temporaryGallery]);

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
    if (
      temporaryActive &&
      (!temporaryGallery || !["completed", "partial"].includes(temporaryGallery.status))
    ) {
      setError("请先上传图片并等待临时图库索引完成");
      return;
    }
    setBusy(true);
    const requestId = ++searchRequestRef.current;
    setError("");
    setActiveQuery(normalized);
    try {
      const searchRequest = temporaryActive && temporaryGallery
        ? searchTemporaryGallery(temporaryGallery.session_id, normalized)
        : searchImages(normalized);
      const [results, status] = await Promise.all([searchRequest, getHealth()]);
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
      if (temporaryActive && temporaryGallery) {
        setItems(await listTemporaryGalleryImages(temporaryGallery.session_id));
      } else {
        await refreshLibrary();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleFolder(event: ChangeEvent<HTMLInputElement>) {
    if (!libraryWritable && !temporaryEnabled) return;
    const files = Array.from(event.target.files ?? []).filter((file) =>
      ["image/jpeg", "image/png", "image/webp"].includes(file.type),
    );
    event.target.value = "";
    if (!files.length) {
      setNotice("所选文件夹中没有支持的图片");
      return;
    }
    if (
      temporaryEnabled &&
      health?.temporary_gallery_max_files &&
      files.length > health.temporary_gallery_max_files
    ) {
      setError(`公开演示每次最多上传 ${health.temporary_gallery_max_files} 张图片`);
      return;
    }
    setUploading(true);
    setError("");
    setNotice(`正在安全暂存 ${files.length} 张图片…`);
    try {
      if (libraryWritable) {
        const job = await createImportJob(files);
        setImportJob(job);
        setNotice(`后台任务已创建，正在处理 ${job.total_files} 张图片`);
      } else {
        if (temporaryGallery && !["queued", "running"].includes(temporaryGallery.status)) {
          await deleteTemporaryGallery(temporaryGallery.session_id).catch(() => undefined);
        }
        const temporary = await createTemporaryGallery(files);
        sessionStorage.setItem(TEMPORARY_SESSION_KEY, temporary.session_id);
        setTemporaryGallery(temporary);
        setGalleryMode("temporary");
        setItems([]);
        setQuery("");
        setActiveQuery("");
        setNotice(`临时图库已创建，正在处理 ${temporary.total_files} 张图片`);
      }
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

  async function activateCuratedGallery() {
    searchRequestRef.current += 1;
    setGalleryMode("curated");
    setQuery("");
    setActiveQuery("");
    setBusy(true);
    setError("");
    try {
      setItems(await listImages());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法加载示例图库");
    } finally {
      setBusy(false);
    }
  }

  async function activateTemporaryGallery() {
    searchRequestRef.current += 1;
    setGalleryMode("temporary");
    setQuery("");
    setActiveQuery("");
    setBusy(true);
    setError("");
    try {
      setItems(
        temporaryGallery && ["completed", "partial"].includes(temporaryGallery.status)
          ? await listTemporaryGalleryImages(temporaryGallery.session_id)
          : [],
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法加载临时图库");
    } finally {
      setBusy(false);
    }
  }

  async function clearTemporaryGallery() {
    if (!temporaryGallery || ["queued", "running"].includes(temporaryGallery.status)) return;
    setBusy(true);
    setError("");
    try {
      await deleteTemporaryGallery(temporaryGallery.session_id);
      sessionStorage.removeItem(TEMPORARY_SESSION_KEY);
      setTemporaryGallery(null);
      setGalleryMode("curated");
      setQuery("");
      setActiveQuery("");
      setItems(await listImages());
      setNotice("临时图库已立即清除");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法清除临时图库");
    } finally {
      setBusy(false);
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
        <div
          className="privacy-dot"
          title={demoMode ? "访客图片按会话隔离并自动删除" : "所有数据均保存在本机"}
        >
          <LockKeyhole size={16} />
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="wordmark">
            <span>MuseLens</span>
            <small>{demoMode ? "PUBLIC AI DEMO" : "LOCAL AI GALLERY"}</small>
          </div>
          <SearchBar
            value={query}
            onChange={setQuery}
            onSubmit={() => runSearch()}
            onClear={clearSearch}
            inputRef={searchRef}
            busy={busy}
          />
          {libraryWritable || temporaryEnabled ? (
            <>
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
                <span>
                  {importActive
                    ? "后台索引中"
                    : libraryWritable
                      ? "导入文件夹"
                      : "上传临时图库"}
                </span>
              </button>
            </>
          ) : (
            <span className="mode-badge"><LockKeyhole size={14} /> 固定演示图库</span>
          )}
        </header>

        <div className="content-wrap">
          {demoMode && temporaryEnabled && (
            <div className="gallery-mode-switch" aria-label="选择图库">
              <button
                className={!temporaryActive ? "active" : ""}
                onClick={activateCuratedGallery}
              >
                <Sparkles size={14} /> 示例图库
              </button>
              <button
                className={temporaryActive ? "active" : ""}
                onClick={activateTemporaryGallery}
              >
                <Images size={14} /> 我的临时图库
                {temporaryGallery && <span>{temporaryGallery.imported_files}</span>}
              </button>
              <small><Clock3 size={13} /> 上传内容 30 分钟后自动清除</small>
            </div>
          )}
          <section className="hero-row">
            <div>
              <div className="eyebrow">
                {activeQuery
                  ? "SEMANTIC RESULTS"
                  : temporaryActive
                    ? "YOUR PRIVATE DEMO SESSION"
                    : demoMode
                    ? "CURATED DEMO LIBRARY"
                    : "YOUR PRIVATE LIBRARY"}
              </div>
              <h1>{activeQuery ? `“${activeQuery}”` : "用语言，重新发现照片"}</h1>
              <p>
                {activeQuery
                  ? `按语义相关度展示 ${items.length} 个结果`
                  : temporaryActive
                    ? "上传任意图片，现场建立只属于本次会话的语义索引。"
                    : demoMode
                    ? "在固定公开图库中体验中英文自然语言搜索。"
                    : "无需标签或整理文件名，描述你记得的画面即可。"}
              </p>
            </div>
            <div className="status-cluster">
              <span className="status-chip">
                <span className={health ? "live-dot" : "live-dot offline"} />
                {health ? (demoMode ? "公开演示在线" : "本地服务在线") : "正在连接"}
              </span>
              <span className="count-chip">
                {temporaryActive
                  ? temporaryGallery?.imported_files ?? 0
                  : health?.indexed_images ?? items.length} 张已索引
              </span>
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

          {libraryWritable && importJob && (
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

          {temporaryEnabled && temporaryActive && temporaryGallery && (
            <section className={`import-progress ${temporaryGallery.status}`} aria-live="polite">
              <div className="import-progress-icon">
                {importActive ? (
                  <LoaderCircle className="spin" size={18} />
                ) : temporaryGallery.status === "completed" ? (
                  <Check size={18} />
                ) : (
                  <CloudOff size={18} />
                )}
              </div>
              <div className="import-progress-body">
                <div className="import-progress-title">
                  <strong>
                    {importActive
                      ? "正在为你的图片建立临时语义索引"
                      : temporaryGallery.status === "completed"
                        ? "临时图库可以搜索了"
                        : temporaryGallery.status === "partial"
                          ? "部分图片已可搜索"
                          : "临时图库建立失败"}
                  </strong>
                  <span>{temporaryGallery.processed_files} / {temporaryGallery.total_files}</span>
                </div>
                <div className="progress-track" aria-label="临时图库索引进度">
                  <span
                    style={{
                      width: `${Math.round(
                        (temporaryGallery.processed_files /
                          Math.max(temporaryGallery.total_files, 1)) * 100,
                      )}%`,
                    }}
                  />
                </div>
                <div className="import-progress-meta">
                  <span>可搜索 {temporaryGallery.imported_files}</span>
                  <span>重复 {temporaryGallery.duplicate_files}</span>
                  <span>失败 {temporaryGallery.failed_files}</span>
                  <span><Clock3 size={11} /> 本会话到期自动清除</span>
                </div>
              </div>
              {!importActive && (
                <button className="retry-button danger" onClick={clearTemporaryGallery}>
                  <Trash2 size={14} /> 立即清除
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
                    : temporaryActive
                      ? temporaryGallery
                        ? "图片仍在建立索引"
                        : "创建你的临时图库"
                    : demoMode
                      ? "演示图库尚未准备完成"
                      : "从一个图片文件夹开始"}
              </h2>
              <p>
                {activeQuery
                  ? temporaryActive || !demoMode
                    ? "用户图库始终保留最接近的结果，并按与最高分的差距截断较弱匹配。可以尝试更具体的中英文描述。"
                    : "系统不会为了凑数返回低相关结果。可以尝试更具体的中英文描述。"
                  : temporaryActive
                    ? temporaryGallery
                      ? "索引完成后，你可以用自然语言检索刚刚上传的任意图片。"
                      : `选择最多 ${health?.temporary_gallery_max_files ?? 30} 张图片；内容按会话隔离，并在 30 分钟后自动删除。`
                  : demoMode
                    ? "公开版本只读取固定样例，不会保存访客上传的图片。"
                    : "图片只会复制到 MuseLens 专用目录，原始文件不会被移动或修改。"}
              </p>
              {activeQuery ? (
                <button onClick={clearSearch}><X size={17} /> 清除搜索</button>
              ) : libraryWritable || (temporaryEnabled && temporaryActive) ? (
                <button onClick={() => fileRef.current?.click()} disabled={importActive}>
                  <FolderOpen size={17} /> {libraryWritable ? "选择图片文件夹" : "选择图片"}
                </button>
              ) : (
                <span className="mode-badge"><LockKeyhole size={14} /> 只读演示模式</span>
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
            <img src={imageUrl(selected.image_id, selected.session_id)} alt={selected.filename} />
            <div className="lightbox-meta">
              <div>
                <span>{selected.session_id ? "临时图片" : demoMode ? "演示图片" : "本地图片"}</span>
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
