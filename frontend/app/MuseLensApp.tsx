import { PhotoGrid } from "@/components/PhotoGrid";
import { SearchBar } from "@/components/SearchBar";
import { FilterPanel } from "@/components/FilterPanel";
import {
  ImageSearchDialog,
  type ImageQueryCandidate,
} from "@/components/ImageSearchDialog";
import { DuplicateReviewDialog } from "@/components/DuplicateReviewDialog";
import { activeFilterCount, EMPTY_FILTERS } from "@/lib/search-filters";
import { buildSmartAlbums, type SmartAlbum } from "@/lib/smart-albums";
import { filenameEvidence, relevanceFor } from "@/lib/relevance";
import { monotonicNow } from "@/lib/timing";
import {
  createTemporaryGallery,
  createImportJob,
  createAlbum,
  deleteAlbum as deleteAlbumRequest,
  deleteImage,
  deleteTemporaryGallery,
  getHealth,
  getImportJob,
  getLatestImportJob,
  getTemporaryGallery,
  imageUrl,
  listImages,
  listAlbums,
  listTagCatalog,
  listDuplicateGroups,
  listTemporaryGalleryImages,
  retryImportJob,
  restoreImageAutoTags,
  renameAlbum,
  searchImages,
  searchImagesByImage,
  searchTemporaryGallery,
  searchTemporaryGalleryByImage,
  thumbnailUrl,
  updateImageTags,
  updateAlbumMembership,
} from "@/lib/api";
import type {
  Health,
  CustomAlbum,
  DuplicateGroup,
  DuplicateMember,
  ImportJob,
  LibraryItem,
  SearchFilters,
  TagCatalogItem,
  TemporaryGallery,
} from "@/lib/types";
import {
  Check,
  ChevronRight,
  Clock3,
  CloudOff,
  Copy,
  Heart,
  FolderOpen,
  Filter,
  Images,
  ImagePlus,
  LoaderCircle,
  LockKeyhole,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Search,
  ScanSearch,
  Sparkles,
  Tags,
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
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [searchMs, setSearchMs] = useState<number | null>(null);
  const [imageDialogOpen, setImageDialogOpen] = useState(false);
  const [pendingImageQuery, setPendingImageQuery] = useState<ImageQueryCandidate | null>(null);
  const [activeImageQuery, setActiveImageQuery] = useState<ImageQueryCandidate | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importJob, setImportJob] = useState<ImportJob | null>(null);
  const [temporaryGallery, setTemporaryGallery] = useState<TemporaryGallery | null>(null);
  const [galleryMode, setGalleryMode] = useState<"curated" | "temporary">("curated");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [tagCatalog, setTagCatalog] = useState<TagCatalogItem[]>([]);
  const [editingTags, setEditingTags] = useState(false);
  const [tagDraft, setTagDraft] = useState<string[]>([]);
  const [tagSaving, setTagSaving] = useState(false);
  const [albums, setAlbums] = useState<CustomAlbum[]>([]);
  const [albumEditorOpen, setAlbumEditorOpen] = useState(false);
  const [albumName, setAlbumName] = useState("");
  const [editingAlbum, setEditingAlbum] = useState<CustomAlbum | null>(null);
  const [albumSaving, setAlbumSaving] = useState(false);
  const [activeAlbum, setActiveAlbum] = useState<CustomAlbum | null>(null);
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [duplicateLoading, setDuplicateLoading] = useState(false);
  const [duplicateGroups, setDuplicateGroups] = useState<DuplicateGroup[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const searchRequestRef = useRef(0);
  const previewUrlsRef = useRef<Set<string>>(new Set());
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
  const filterCount = activeFilterCount(filters);
  const searchActive = Boolean(activeQuery || activeImageQuery || filterCount || activeAlbum);
  const retrievalEvidence = activeQuery ? filenameEvidence(activeQuery, items) : null;
  const availableTags = Array.from(
    new Map(items.flatMap((item) => item.tags).map((tag) => [tag.slug, tag])).values(),
  ).sort((left, right) => left.label.localeCompare(right.label, "zh-CN"));
  const smartAlbums = !searchActive ? buildSmartAlbums(items) : [];

  function createPreviewUrl(file: File): string {
    const url = URL.createObjectURL(file);
    previewUrlsRef.current.add(url);
    return url;
  }

  function releasePreviewUrl(candidate: ImageQueryCandidate | null) {
    if (!candidate || candidate.source !== "device") return;
    URL.revokeObjectURL(candidate.previewUrl);
    previewUrlsRef.current.delete(candidate.previewUrl);
  }

  useEffect(() => () => {
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrlsRef.current.clear();
  }, []);

  useEffect(() => {
    listTagCatalog().then(setTagCatalog).catch(() => undefined);
  }, []);

  const refreshLibrary = useCallback(async () => {
    const [library, status, savedAlbums] = await Promise.all([
      listImages(),
      getHealth(),
      listAlbums(),
    ]);
    setItems(library);
    setHealth(status);
    setAlbums(savedAlbums);
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
      if (event.key === "Escape") {
        setSelected(null);
        setFiltersOpen(false);
        setDuplicateOpen(false);
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  async function runSearch(nextQuery = query, nextFilters = filters) {
    setActiveAlbum(null);
    const normalized = nextQuery.trim();
    if (!normalized && activeFilterCount(nextFilters) === 0) {
      searchRequestRef.current += 1;
      setFilters(EMPTY_FILTERS);
      setActiveQuery("");
      setSearchMs(null);
      setBusy(true);
      try {
        setItems(
          temporaryActive && temporaryGallery
            ? await listTemporaryGalleryImages(temporaryGallery.session_id)
            : await listImages(),
        );
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "加载失败");
      } finally {
        setBusy(false);
      }
      return;
    }
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
    releasePreviewUrl(activeImageQuery);
    setActiveImageQuery(null);
    const startedAt = monotonicNow();
    try {
      const searchRequest = temporaryActive && temporaryGallery
        ? searchTemporaryGallery(temporaryGallery.session_id, normalized, nextFilters)
        : searchImages(normalized, nextFilters);
      const [results, status] = await Promise.all([searchRequest, getHealth()]);
      if (requestId !== searchRequestRef.current) return;
      setItems(results);
      setHealth(status);
      setSearchMs(Math.round(monotonicNow() - startedAt));
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
    setFilters(EMPTY_FILTERS);
    setFiltersOpen(false);
    setSearchMs(null);
    releasePreviewUrl(activeImageQuery);
    setActiveImageQuery(null);
    setActiveAlbum(null);
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

  function openSmartAlbum(album: SmartAlbum) {
    const nextFilters = { ...EMPTY_FILTERS, tags: album.tags };
    setQuery("");
    setFilters(nextFilters);
    runSearch("", nextFilters);
  }

  function openCustomAlbum(album: CustomAlbum) {
    setQuery("");
    setActiveQuery("");
    setFilters(EMPTY_FILTERS);
    setActiveAlbum(album);
    setItems((current) => current.filter((item) => album.image_ids.includes(item.image_id)));
  }

  function showAlbumEditor(album: CustomAlbum | null = null) {
    setEditingAlbum(album);
    setAlbumName(album?.name ?? "");
    setAlbumEditorOpen(true);
  }

  async function saveAlbum() {
    if (!albumName.trim()) return;
    setAlbumSaving(true);
    setError("");
    try {
      const saved = editingAlbum
        ? await renameAlbum(editingAlbum.album_id, albumName)
        : await createAlbum(albumName);
      setAlbums((current) => editingAlbum
        ? current.map((album) => album.album_id === saved.album_id ? saved : album)
        : [...current, saved]);
      setAlbumEditorOpen(false);
      setNotice(editingAlbum ? "相册名称已更新" : "相册已创建，可从图片预览中添加照片");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存相册失败");
    } finally {
      setAlbumSaving(false);
    }
  }

  async function removeAlbum(album: CustomAlbum) {
    setError("");
    try {
      await deleteAlbumRequest(album.album_id);
      setAlbums((current) => current.filter((item) => item.album_id !== album.album_id));
      if (activeAlbum?.album_id === album.album_id) await clearSearch();
      setNotice(`已删除相册“${album.name}”，原照片不受影响`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除相册失败");
    }
  }

  async function toggleAlbumMembership(album: CustomAlbum, imageId: string) {
    setAlbumSaving(true);
    setError("");
    try {
      const updated = await updateAlbumMembership(
        album.album_id,
        imageId,
        !album.image_ids.includes(imageId),
      );
      setAlbums((current) => current.map((item) =>
        item.album_id === updated.album_id ? updated : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新相册失败");
    } finally {
      setAlbumSaving(false);
    }
  }

  function selectImageQuery(file: File) {
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setError("查询图片仅支持 JPEG、PNG 和 WebP");
      return;
    }
    if (file.size > 12 * 1024 * 1024) {
      setError("查询图片不能超过 12 MB");
      return;
    }
    releasePreviewUrl(pendingImageQuery);
    setPendingImageQuery({
      file,
      previewUrl: createPreviewUrl(file),
      source: "device",
    });
    setError("");
  }

  function closeImageDialog() {
    if (busy) return;
    releasePreviewUrl(pendingImageQuery);
    setPendingImageQuery(null);
    setImageDialogOpen(false);
  }

  async function runImageSearch() {
    if (!pendingImageQuery) return;
    if (
      temporaryActive &&
      (!temporaryGallery || !["completed", "partial"].includes(temporaryGallery.status))
    ) {
      setError("请先上传图片并等待临时图库索引完成");
      return;
    }
    const candidate = pendingImageQuery;
    const startedAt = monotonicNow();
    const requestId = ++searchRequestRef.current;
    setBusy(true);
    setError("");
    try {
      const results = temporaryActive && temporaryGallery
        ? await searchTemporaryGalleryByImage(temporaryGallery.session_id, candidate.file)
        : await searchImagesByImage(candidate.file);
      if (requestId !== searchRequestRef.current) return;
      releasePreviewUrl(activeImageQuery);
      setItems(
        candidate.imageId
          ? results.filter((item) => item.image_id !== candidate.imageId)
          : results,
      );
      setActiveImageQuery(candidate);
      setPendingImageQuery(null);
      setImageDialogOpen(false);
      setQuery("");
      setActiveQuery("");
      setFilters(EMPTY_FILTERS);
      setFiltersOpen(false);
      setSearchMs(Math.round(monotonicNow() - startedAt));
    } catch (reason) {
      if (requestId === searchRequestRef.current) {
        setError(reason instanceof Error ? reason.message : "以图搜图失败");
      }
    } finally {
      if (requestId === searchRequestRef.current) setBusy(false);
    }
  }

  async function findSimilarFromLibrary(item: LibraryItem) {
    setError("");
    try {
      const response = await fetch(imageUrl(item.image_id, item.session_id));
      if (!response.ok) throw new Error("无法读取这张图片");
      const blob = await response.blob();
      const file = new File([blob], item.filename, { type: item.content_type });
      setPendingImageQuery({
        file,
        previewUrl: imageUrl(item.image_id, item.session_id),
        source: "library",
        imageId: item.image_id,
      });
      setSelected(null);
      setImageDialogOpen(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法准备查询图片");
    }
  }

  function openImage(item: LibraryItem) {
    setSelected(item);
    setTagDraft(item.tags.map((tag) => tag.slug));
    setEditingTags(false);
  }

  function closeImage() {
    if (tagSaving) return;
    setSelected(null);
    setEditingTags(false);
  }

  function toggleTagDraft(slug: string) {
    setTagDraft((current) =>
      current.includes(slug)
        ? current.filter((item) => item !== slug)
        : [...current, slug],
    );
  }

  function mergeUpdatedImage(updated: LibraryItem) {
    setItems((current) =>
      current.map((item) =>
        item.image_id === updated.image_id ? { ...item, ...updated } : item,
      ),
    );
    setSelected((current) =>
      current?.image_id === updated.image_id ? { ...current, ...updated } : current,
    );
  }

  async function saveManualTags() {
    if (!selected) return;
    setTagSaving(true);
    setError("");
    try {
      const updated = await updateImageTags(selected.image_id, tagDraft);
      mergeUpdatedImage(updated);
      setEditingTags(false);
      setNotice("标签已保存为人工修正");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "标签保存失败");
    } finally {
      setTagSaving(false);
    }
  }

  async function restoreSelectedAutoTags() {
    if (!selected) return;
    setTagSaving(true);
    setError("");
    try {
      const updated = await restoreImageAutoTags(selected.image_id);
      mergeUpdatedImage(updated);
      setTagDraft(updated.tags.map((tag) => tag.slug));
      setEditingTags(false);
      setNotice("已恢复 SigLIP2 自动标签");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "自动标签恢复失败");
    } finally {
      setTagSaving(false);
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
    releasePreviewUrl(activeImageQuery);
    setActiveImageQuery(null);
    setActiveAlbum(null);
    setSearchMs(null);
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
    releasePreviewUrl(activeImageQuery);
    setActiveImageQuery(null);
    setActiveAlbum(null);
    setSearchMs(null);
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
      releasePreviewUrl(activeImageQuery);
      setActiveImageQuery(null);
      setSearchMs(null);
      setItems(await listImages());
      setNotice("临时图库已立即清除");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法清除临时图库");
    } finally {
      setBusy(false);
    }
  }

  async function loadDuplicateGroups() {
    setDuplicateOpen(true);
    setDuplicateLoading(true);
    setError("");
    try {
      setDuplicateGroups(
        await listDuplicateGroups(
          temporaryActive && temporaryGallery
            ? temporaryGallery.session_id
            : undefined,
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法检查重复照片");
      setDuplicateOpen(false);
    } finally {
      setDuplicateLoading(false);
    }
  }

  async function removeDuplicate(member: DuplicateMember) {
    const confirmed = window.confirm(
      `删除 MuseLens 中的导入副本“${member.filename}”？你的原始照片不会被删除。`,
    );
    if (!confirmed) return;
    setDuplicateLoading(true);
    setError("");
    try {
      await deleteImage(member.image_id);
      const [groups] = await Promise.all([listDuplicateGroups(), refreshLibrary()]);
      setDuplicateGroups(groups);
      setNotice(`已删除导入副本“${member.filename}”，原始照片未受影响`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法删除导入副本");
    } finally {
      setDuplicateLoading(false);
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
            filterCount={filterCount}
            filtersOpen={filtersOpen}
            onToggleFilters={() => setFiltersOpen((open) => !open)}
            onOpenImageSearch={() => {
              setPendingImageQuery(null);
              setImageDialogOpen(true);
            }}
          />
          <FilterPanel
            availableTags={availableTags}
            open={filtersOpen}
            filters={filters}
            onChange={setFilters}
            onApply={() => {
              setFiltersOpen(false);
              runSearch(query, filters);
            }}
            onClose={() => setFiltersOpen(false)}
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
                {activeAlbum
                  ? "PERSONAL ALBUM"
                  : activeImageQuery
                  ? "VISUAL SIMILARITY RESULTS"
                  : searchActive
                  ? "SEMANTIC RESULTS"
                  : temporaryActive
                    ? "YOUR PRIVATE DEMO SESSION"
                    : demoMode
                    ? "CURATED DEMO LIBRARY"
                    : "YOUR PRIVATE LIBRARY"}
              </div>
              <h1>
                {activeAlbum
                  ? activeAlbum.name
                  : activeImageQuery
                  ? "找到相似的画面"
                  : activeQuery
                  ? `“${activeQuery}”`
                  : filterCount
                    ? "筛选后的图片"
                    : "用语言，重新发现照片"}
              </h1>
              <p>
                {activeAlbum
                  ? `你收藏到此相册的 ${items.length} 张照片，删除相册不会删除原图。`
                  : activeImageQuery
                  ? `根据构图、主体和视觉语义展示 ${items.length} 个相似结果`
                  : searchActive
                  ? `${activeQuery ? "语义与图片属性共同检索" : "按图片属性筛选"}，展示 ${items.length} 个结果`
                  : temporaryActive
                    ? "上传任意图片，现场建立只属于本次会话的语义索引。"
                    : demoMode
                    ? "在固定公开图库中体验中英文自然语言搜索。"
                    : "无需标签或整理文件名，描述你记得的画面即可。"}
              </p>
            </div>
            <div className="status-cluster">
              {!searchActive && items.length > 1 && (
                <button className="duplicate-trigger" onClick={loadDuplicateGroups}>
                  <Copy size={13} /> 重复照片
                </button>
              )}
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

          {activeImageQuery && (
            <section className="active-image-query" aria-label="当前查询图片">
              <img alt="当前查询图片" src={activeImageQuery.previewUrl} />
              <div>
                <span><ScanSearch size={13} /> 当前视觉查询</span>
                <strong>{activeImageQuery.file.name}</strong>
                <small>查询图仅参与特征提取，没有写入图片库</small>
              </div>
              <button onClick={() => {
                setPendingImageQuery(null);
                setImageDialogOpen(true);
              }}><ImagePlus size={14} /> 更换图片</button>
              <button className="clear-image-query" onClick={clearSearch} aria-label="清除图片查询">
                <X size={16} />
              </button>
            </section>
          )}

          {!searchActive && items.length > 0 && (
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

          {!searchActive && libraryWritable && (
            <section className="custom-albums" aria-labelledby="custom-albums-title">
              <div className="smart-albums-heading">
                <div>
                  <span><Heart size={13} /> 我的收藏</span>
                  <h2 id="custom-albums-title">自定义相册</h2>
                </div>
                <button className="new-album" onClick={() => showAlbumEditor()}>
                  <Plus size={13} /> 新建相册
                </button>
              </div>
              {albums.length === 0 ? (
                <button className="album-empty" onClick={() => showAlbumEditor()}>
                  <Plus size={17} />
                  <span><strong>建立第一个相册</strong><small>照片仍保留在原图库中</small></span>
                </button>
              ) : (
                <div className="custom-album-grid">
                  {albums.map((album) => {
                    const cover = items.find((item) => album.image_ids.includes(item.image_id));
                    return (
                      <article key={album.album_id} className="custom-album-card">
                        <button className="custom-album-open" onClick={() => openCustomAlbum(album)}>
                          {cover ? (
                            <img src={thumbnailUrl(cover.image_id)} alt="" loading="lazy" />
                          ) : (
                            <span className="custom-album-placeholder"><Images size={25} /></span>
                          )}
                          <span><strong>{album.name}</strong><small>{album.image_ids.length} 张照片</small></span>
                        </button>
                        <div>
                          <button onClick={() => showAlbumEditor(album)} aria-label={`重命名${album.name}`}>
                            <Pencil size={12} />
                          </button>
                          <button onClick={() => removeAlbum(album)} aria-label={`删除${album.name}`}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {smartAlbums.length > 0 && (
            <section className="smart-albums" aria-labelledby="smart-albums-title">
              <div className="smart-albums-heading">
                <div>
                  <span><Sparkles size={13} /> 自动整理</span>
                  <h2 id="smart-albums-title">智能相册</h2>
                </div>
                <small>随标签自动更新，无需移动原文件</small>
              </div>
              <div className="smart-album-grid">
                {smartAlbums.map((album) => (
                  <button key={album.id} onClick={() => openSmartAlbum(album)}>
                    <img
                      src={thumbnailUrl(album.cover.image_id, album.cover.session_id)}
                      alt=""
                      loading="lazy"
                    />
                    <span className="smart-album-shade" />
                    <span className="smart-album-copy">
                      <strong>{album.title}</strong>
                      <small>{album.description}</small>
                      <em>{album.count} 张照片 <ChevronRight size={13} /></em>
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {filterCount > 0 && (
            <div className="active-filters" aria-label="已应用筛选">
              <span><Filter size={13} /> 已应用</span>
              {filters.contentTypes.map((type) => (
                <button
                  key={type}
                  onClick={() => {
                    const next = { ...filters, contentTypes: filters.contentTypes.filter((item) => item !== type) };
                    setFilters(next);
                    runSearch(activeQuery, next);
                  }}
                >
                  {{ "image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WebP" }[type]} <X size={12} />
                </button>
              ))}
              {filters.orientations.map((orientation) => (
                <button
                  key={orientation}
                  onClick={() => {
                    const next = { ...filters, orientations: filters.orientations.filter((item) => item !== orientation) };
                    setFilters(next);
                    runSearch(activeQuery, next);
                  }}
                >
                  {{ landscape: "横图", portrait: "竖图", square: "方图" }[orientation]} <X size={12} />
                </button>
              ))}
              {filters.tags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => {
                    const next = { ...filters, tags: filters.tags.filter((item) => item !== tag) };
                    setFilters(next);
                    runSearch(activeQuery, next);
                  }}
                >
                  {availableTags.find((item) => item.slug === tag)?.label ?? tag} <X size={12} />
                </button>
              ))}
              {filters.datePreset !== "all" && (
                <button onClick={() => {
                  const next = { ...filters, datePreset: "all" as const };
                  setFilters(next);
                  runSearch(activeQuery, next);
                }}>
                  {{ week: "近 7 天", month: "近 30 天", year: "近一年" }[filters.datePreset]} <X size={12} />
                </button>
              )}
              {filters.minWidth && <button onClick={() => {
                const next = { ...filters, minWidth: null };
                setFilters(next);
                runSearch(activeQuery, next);
              }}>宽度 ≥ {filters.minWidth}px <X size={12} /></button>}
              {filters.maxSizeMB && <button onClick={() => {
                const next = { ...filters, maxSizeMB: null };
                setFilters(next);
                runSearch(activeQuery, next);
              }}>文件 ≤ {filters.maxSizeMB}MB <X size={12} /></button>}
              {filters.sort !== "relevance" && <button onClick={() => {
                const next = { ...filters, sort: "relevance" as const };
                setFilters(next);
                runSearch(activeQuery, next);
              }}>{{ newest: "最新导入", oldest: "最早导入", size_desc: "文件最大" }[filters.sort]} <X size={12} /></button>}
              <button
                className="clear-filter-chips"
                onClick={() => {
                  setFilters(EMPTY_FILTERS);
                  runSearch(activeQuery, EMPTY_FILTERS);
                }}
              >
                清除全部
              </button>
            </div>
          )}

          {!busy && activeQuery && items.length > 0 && retrievalEvidence && (
            <section className="retrieval-insight" aria-label="语义检索效果说明">
              <div className="insight-icon"><Sparkles size={17} /></div>
              <div className="insight-copy">
                <span>SEMANTIC EVIDENCE</span>
                <strong>
                  {retrievalEvidence.semanticOnly === retrievalEvidence.total
                    ? "这些结果来自画面理解，而不是文件名"
                    : "语义理解补充了文件名搜索的不足"}
                </strong>
                <p>
                  本次 {retrievalEvidence.total} 张结果中，{retrievalEvidence.semanticOnly} 张图片的文件名
                  不包含查询词，由 SigLIP2 根据画面与描述的语义关系召回。
                </p>
              </div>
              <div className="insight-metrics">
                <div><strong>{retrievalEvidence.total}</strong><span>语义结果</span></div>
                <div><strong>{retrievalEvidence.filenameMatches}</strong><span>文件名命中</span></div>
              </div>
            </section>
          )}

          {!busy && activeImageQuery && items.length > 0 && (
            <section className="retrieval-insight image-evidence" aria-label="视觉检索效果说明">
              <div className="insight-icon"><ScanSearch size={17} /></div>
              <div className="insight-copy">
                <span>VISUAL EVIDENCE</span>
                <strong>不依赖标签或文件名，直接比较画面内容</strong>
                <p>SigLIP2 将查询图和图库图片编码到同一向量空间，并按视觉语义距离排序。</p>
              </div>
              <div className="insight-metrics">
                <div><strong>{items.length}</strong><span>相似结果</span></div>
                <div><strong>{searchMs ?? "—"}</strong><span>处理毫秒</span></div>
              </div>
            </section>
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

          {!busy && searchActive && (
            <div className="results-toolbar">
              <div><strong>{items.length}</strong> 个匹配结果</div>
              <div>
                {searchMs !== null && <span><Clock3 size={13} /> {searchMs} ms</span>}
                {(activeQuery || activeImageQuery) && <span title="相关性根据当前查询的结果排名与分数差计算，不代表概率">相对相关性 · 非概率</span>}
                <span>最多展示 60 张</span>
              </div>
            </div>
          )}

          {busy ? (
            <div className="loading-state">
              <LoaderCircle className="spin" size={25} />
              <span>正在理解你的描述…</span>
            </div>
          ) : items.length ? (
            <PhotoGrid items={items} onOpen={openImage} />
          ) : (
            <section className="empty-state">
              <div className="empty-icon">{searchActive ? <Search size={25} /> : <Upload size={25} />}</div>
              <h2>
                {error
                  ? "暂时无法读取图片库"
                  : searchActive
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
                {searchActive
                  ? activeImageQuery
                    ? "系统已截断与查询图差距过大的结果。可以换一张主体更清晰的参考图片。"
                    : temporaryActive || !demoMode
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
              {searchActive ? (
                <button onClick={clearSearch}><X size={17} /> 清除当前查询</button>
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
        <div className="lightbox" role="dialog" aria-modal="true" aria-label={selected.filename} onClick={closeImage}>
          <button className="lightbox-close" onClick={closeImage} aria-label="关闭预览">
            <X size={20} />
          </button>
          <div className="lightbox-content" onClick={(event) => event.stopPropagation()}>
            <img src={imageUrl(selected.image_id, selected.session_id)} alt={selected.filename} />
            <div className="lightbox-meta">
              <div>
                <span>{selected.session_id ? "临时图片" : demoMode ? "演示图片" : "本地图片"}</span>
                <strong>{selected.filename}</strong>
                {selected.tags.length > 0 && (
                  <div className="lightbox-tags" aria-label="AI 自动标签">
                    {selected.tags.map((tag) => (
                      <i className={tag.source} key={tag.slug}>
                        {tag.label}{tag.source === "manual" ? " · 人工" : ""}
                      </i>
                    ))}
                  </div>
                )}
              </div>
              {selected.score != null && (() => {
                const index = items.findIndex((item) => item.image_id === selected.image_id);
                const relevance = relevanceFor(selected, Math.max(index, 0), items);
                return relevance && (
                  <div className="lightbox-relevance">
                    <strong>{relevance.label} · 第 {index + 1} 位</strong>
                    <span>模型排序分 {selected.score.toFixed(3)}，仅用于本次查询内比较</span>
                  </div>
                );
              })()}
              <button
                className="find-similar-button"
                onClick={() => findSimilarFromLibrary(selected)}
              >
                <ScanSearch size={14} /> 查找相似图片
              </button>
              {libraryWritable && !selected.session_id && (
                <button
                  className="tag-edit-button"
                  onClick={() => {
                    setTagDraft(selected.tags.map((tag) => tag.slug));
                    setEditingTags((current) => !current);
                  }}
                >
                  <Tags size={14} /> {editingTags ? "收起标签" : "修正标签"}
                </button>
              )}
            </div>
            {libraryWritable && !selected.session_id && (
              <section className="album-membership" aria-label="收藏到相册">
                <div><Heart size={13} /><strong>收藏到相册</strong></div>
                {albums.map((album) => (
                  <button
                    className={album.image_ids.includes(selected.image_id) ? "selected" : ""}
                    disabled={albumSaving}
                    key={album.album_id}
                    onClick={() => toggleAlbumMembership(album, selected.image_id)}
                  >
                    {album.image_ids.includes(selected.image_id) && <Check size={11} />}
                    {album.name}
                  </button>
                ))}
                <button className="create-inline" onClick={() => showAlbumEditor()}>
                  <Plus size={11} /> 新建
                </button>
              </section>
            )}
            {editingTags && libraryWritable && !selected.session_id && (
              <section className="tag-editor" aria-label="修正图片标签">
                <div className="tag-editor-heading">
                  <div>
                    <strong>人工修正标签</strong>
                    <span>选择更符合画面的标签，保存后不会被普通搜索覆盖。</span>
                  </div>
                  <div>
                    <button disabled={tagSaving} onClick={restoreSelectedAutoTags}>
                      <Sparkles size={13} /> 恢复自动
                    </button>
                    <button className="save-tags" disabled={tagSaving} onClick={saveManualTags}>
                      <Save size={13} /> {tagSaving ? "保存中" : "保存"}
                    </button>
                  </div>
                </div>
                <div className="tag-editor-options">
                  {tagCatalog.map((tag) => (
                    <button
                      className={tagDraft.includes(tag.slug) ? "selected" : ""}
                      key={tag.slug}
                      onClick={() => toggleTagDraft(tag.slug)}
                    >
                      {tag.label}
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>
        </div>
      )}

      {albumEditorOpen && (
        <div className="album-editor-scrim" role="dialog" aria-modal="true" aria-labelledby="album-editor-title">
          <form className="album-editor-dialog" onSubmit={(event) => {
            event.preventDefault();
            saveAlbum();
          }}>
            <div>
              <span><Heart size={14} /></span>
              <div>
                <h2 id="album-editor-title">{editingAlbum ? "重命名相册" : "新建相册"}</h2>
                <p>相册只保存引用，不会复制或移动原照片。</p>
              </div>
            </div>
            <label>
              相册名称
              <input
                autoFocus
                maxLength={60}
                onChange={(event) => setAlbumName(event.target.value)}
                placeholder="例如：暑假旅行"
                value={albumName}
              />
            </label>
            <footer>
              <button type="button" onClick={() => setAlbumEditorOpen(false)}>取消</button>
              <button className="primary" disabled={!albumName.trim() || albumSaving} type="submit">
                {albumSaving ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}
                保存
              </button>
            </footer>
          </form>
        </div>
      )}

      <ImageSearchDialog
        busy={busy}
        candidate={pendingImageQuery}
        onClose={closeImageDialog}
        onSearch={runImageSearch}
        onSelect={selectImageQuery}
        open={imageDialogOpen}
      />
      <DuplicateReviewDialog
        groups={duplicateGroups}
        loading={duplicateLoading}
        onClose={() => setDuplicateOpen(false)}
        onDelete={removeDuplicate}
        open={duplicateOpen}
        sessionId={temporaryActive ? temporaryGallery?.session_id : undefined}
        writable={libraryWritable && !temporaryActive}
      />
    </main>
  );
}
