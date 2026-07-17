import type {
  Health,
  ImageRecord,
  ImportJob,
  ImportResult,
  LibraryItem,
  SearchHit,
  TemporaryGallery,
} from "./types";

export const API_BASE =
  import.meta.env.VITE_MUSELENS_API ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function imageUrl(imageId: string, sessionId?: string): string {
  return sessionId
    ? `${API_BASE}/v1/demo/sessions/${sessionId}/images/${imageId}/content`
    : `${API_BASE}/v1/images/${imageId}/content`;
}

export function thumbnailUrl(imageId: string, sessionId?: string): string {
  return sessionId
    ? `${API_BASE}/v1/demo/sessions/${sessionId}/images/${imageId}/thumbnail`
    : `${API_BASE}/v1/images/${imageId}/thumbnail`;
}

export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

export function listImages(): Promise<ImageRecord[]> {
  return request<ImageRecord[]>("/v1/images");
}

export async function searchImages(query: string): Promise<LibraryItem[]> {
  const hits = await request<SearchHit[]>("/v1/search/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: 12 }),
  });
  return hits.map((hit) => ({ ...hit, content_type: "image/jpeg" }));
}

export function importImages(files: File[]): Promise<ImportResult[]> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<ImportResult[]>("/v1/images/batch", {
    method: "POST",
    body: form,
  });
}

export function createImportJob(files: File[]): Promise<ImportJob> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<ImportJob>("/v1/import-jobs", {
    method: "POST",
    body: form,
  });
}

export function getImportJob(jobId: string): Promise<ImportJob> {
  return request<ImportJob>(`/v1/import-jobs/${jobId}`);
}

export function getLatestImportJob(): Promise<ImportJob | null> {
  return request<ImportJob | null>("/v1/import-jobs/latest");
}

export function retryImportJob(jobId: string): Promise<ImportJob> {
  return request<ImportJob>(`/v1/import-jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export function createTemporaryGallery(files: File[]): Promise<TemporaryGallery> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<TemporaryGallery>("/v1/demo/sessions", {
    method: "POST",
    body: form,
  });
}

export function getTemporaryGallery(sessionId: string): Promise<TemporaryGallery> {
  return request<TemporaryGallery>(`/v1/demo/sessions/${sessionId}`);
}

export async function listTemporaryGalleryImages(sessionId: string): Promise<LibraryItem[]> {
  const images = await request<ImageRecord[]>(`/v1/demo/sessions/${sessionId}/images`);
  return images.map((image) => ({ ...image, session_id: sessionId }));
}

export async function searchTemporaryGallery(
  sessionId: string,
  query: string,
): Promise<LibraryItem[]> {
  const hits = await request<SearchHit[]>(`/v1/demo/sessions/${sessionId}/search/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: 12 }),
  });
  return hits.map((hit) => ({
    ...hit,
    content_type: "image/jpeg",
    session_id: sessionId,
  }));
}

export function deleteTemporaryGallery(sessionId: string): Promise<void> {
  return request<void>(`/v1/demo/sessions/${sessionId}`, { method: "DELETE" });
}
