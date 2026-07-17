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
};

export type Health = {
  status: string;
  indexed_images: number;
  model_loaded: boolean;
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
