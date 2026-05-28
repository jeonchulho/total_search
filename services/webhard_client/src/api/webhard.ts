import { HttpClient } from "../lib/http";
import type {
  AccessibleFolder,
  FileItem,
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  SharePayload,
  ShareResponse,
  TrashItem,
  VersionItem,
} from "../types";

interface FilesResponse {
  files: FileItem[];
}

interface SharedFilesResponse {
  shared_files: FileItem[];
}

interface TrashResponse {
  trash: TrashItem[];
}

interface AccessibleFoldersResponse {
  accessible_folders: AccessibleFolder[];
}

interface SharedFoldersResponse {
  shared_folders: AccessibleFolder[];
}

interface VersionsResponse {
  versions: VersionItem[];
}

export class WebhardApi {
  constructor(private readonly http: HttpClient) {}

  setToken(token: string | null): void {
    this.http.setToken(token);
  }

  register(payload: RegisterRequest): Promise<RegisterResponse> {
    return this.http.request<RegisterResponse>("/nc/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  login(payload: LoginRequest): Promise<LoginResponse> {
    return this.http.request<LoginResponse>("/nc/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  createFolder(path: string): Promise<{ path: string }> {
    return this.http.request<{ path: string }>("/nc/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  }

  listAccessibleFolders(): Promise<AccessibleFoldersResponse> {
    return this.http.request<AccessibleFoldersResponse>("/nc/folders/accessible");
  }

  listSharedFolders(): Promise<SharedFoldersResponse> {
    return this.http.request<SharedFoldersResponse>("/nc/folders/shared");
  }

  listFiles(prefix = "", includeDeleted = false, ownerId?: number): Promise<FilesResponse> {
    const search = new URLSearchParams();
    if (prefix) {
      search.set("prefix", prefix);
    }
    if (includeDeleted) {
      search.set("include_deleted", "true");
    }
    if (typeof ownerId === "number") {
      search.set("owner_id", String(ownerId));
    }
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return this.http.request<FilesResponse>(`/nc/files${suffix}`);
  }

  listSharedFiles(): Promise<SharedFilesResponse> {
    return this.http.request<SharedFilesResponse>("/nc/files/shared");
  }

  listTrash(): Promise<TrashResponse> {
    return this.http.request<TrashResponse>("/nc/files/trash");
  }

  restoreFile(fileId: number): Promise<{ status: string }> {
    return this.http.request<{ status: string }>(`/nc/files/${fileId}/restore`, {
      method: "POST",
    });
  }

  moveToTrash(fileId: number): Promise<{ status: string }> {
    return this.http.request<{ status: string }>(`/nc/files/${fileId}/trash`, {
      method: "POST",
    });
  }

  uploadFile(path: string, file: File): Promise<{ file_id: number; version_no: number }> {
    const form = new FormData();
    form.append("file", file);
    return this.http.request<{ file_id: number; version_no: number }>(
      `/nc/files/upload?path=${encodeURIComponent(path)}`,
      { method: "POST", body: form },
      60000,
    );
  }

  createShare(fileId: number, payload: SharePayload): Promise<ShareResponse> {
    return this.http.request<ShareResponse>(`/nc/files/${fileId}/share`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  getDownloadUrl(fileId: number): Promise<{ url: string }> {
    return this.http.request<{ url: string }>(`/nc/files/${fileId}/download-url`);
  }

  listVersions(fileId: number): Promise<VersionsResponse> {
    return this.http.request<VersionsResponse>(`/nc/files/${fileId}/versions`);
  }
}
