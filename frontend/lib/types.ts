export type ImageRecord = {
  image_id: string;
  filename: string;
  content_type: string;
  width: number;
  height: number;
  size_bytes: number;
  created_at: string;
};

export type SearchHit = {
  image_id: string;
  filename: string;
  score?: number | null;
  content_type: string;
  width: number;
  height: number;
  size_bytes: number;
  created_at: string;
};

export type LibraryItem = ImageRecord & {
  score?: number | null;
  session_id?: string;
};

export type SearchSort = "relevance" | "newest" | "oldest" | "size_desc";
export type ImageOrientation = "landscape" | "portrait" | "square";
export type DatePreset = "all" | "week" | "month" | "year";

export type SearchFilters = {
  contentTypes: string[];
  orientations: ImageOrientation[];
  minWidth: number | null;
  maxSizeMB: number | null;
  datePreset: DatePreset;
  sort: SearchSort;
};

export type Health = {
  status: string;
  indexed_images: number;
  model_loaded: boolean;
  index_backend: "numpy" | "faiss";
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

export type DuplicateMember = ImageRecord & {
  distance_to_representative: number;
  recommended_keep: boolean;
};

export type DuplicateGroup = {
  group_id: string;
  members: DuplicateMember[];
  potential_savings_bytes: number;
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
