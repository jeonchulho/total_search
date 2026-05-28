export type SubjectType = "user" | "group" | "public";

export interface RegisterRequest {
  username: string;
  password: string;
}

export interface RegisterResponse {
  user_id: number;
  username: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  username: string;
}

export interface AccessibleFolder {
  owner_id: number;
  folder_path: string;
  can_read: boolean;
  can_upload: boolean;
  can_manage: boolean;
  source: "owned" | "shared";
}

export interface FileItem {
  file_id: number;
  logical_path: string;
  current_version: number;
  is_deleted?: boolean;
  deleted_at?: string | null;
  updated_at?: string;
}

export interface TrashItem {
  file_id: number;
  logical_path: string;
  deleted_at: string;
}

export interface SharePayload {
  expires_in_sec: number;
  password?: string;
  allow_download: boolean;
  allow_upload: boolean;
  one_time: boolean;
  max_downloads?: number;
}

export interface ShareResponse {
  share_token: string;
  expires_at: string;
  share_url: string;
  password_protected: boolean;
  allow_download: boolean;
  allow_upload: boolean;
  one_time: boolean;
  max_downloads: number | null;
}

export interface VersionItem {
  version_id: number;
  version_no: number;
  object_name: string;
  size: number;
  etag: string;
  content_type: string;
  created_at: string;
  is_current: boolean;
}
