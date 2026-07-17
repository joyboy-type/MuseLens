export type ImageRecord = {
  image_id: string;
  filename: string;
  content_type: string;
};

export type SearchHit = {
  image_id: string;
  filename: string;
  score: number;
};

export type LibraryItem = ImageRecord & {
  score?: number;
  session_id?: string;
};

export type Health = {
  status: string;
  indexed_images: number;
  model_loaded: boolean;
  mode: "local" | "demo";
  library_writable: boolean;
  temporary_galleries_enabled: boolean;
  temporary_gallery_max_files: number;
  temporary_gallery_ttl_seconds: number;
  temporary_gallery_max_sessions: number;
};

export type ImportResult = ImageRecord & {
  duplicate: boolean;
  sha256: string;
};

export type ImportJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "failed";

export type ImportJob = {
  job_id: string;
  status: ImportJobStatus;
  total_files: number;
  processed_files: number;
  imported_files: number;
  duplicate_files: number;
  failed_files: number;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type TemporaryGallery = {
  session_id: string;
  status: ImportJobStatus;
  total_files: number;
  processed_files: number;
  imported_files: number;
  duplicate_files: number;
  failed_files: number;
  error: string | null;
  created_at: string;
  expires_at: string;
};
