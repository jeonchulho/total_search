import "./styles.css";

import { WebhardApi } from "./api/webhard";
import { config } from "./config";
import { HttpClient, HttpError } from "./lib/http";
import { sessionStore } from "./lib/storage";
import type { AccessibleFolder, FileItem, VersionItem } from "./types";

interface AppState {
  token: string | null;
  username: string | null;
  files: FileItem[];
  sharedFiles: FileItem[];
  accessibleFolders: AccessibleFolder[];
  sharedFolders: AccessibleFolder[];
}

const initialSession = sessionStore.load();
const http = new HttpClient(config.apiBaseUrl);
const api = new WebhardApi(http);
api.setToken(initialSession.token);

const state: AppState = {
  token: initialSession.token,
  username: initialSession.username,
  files: [],
  sharedFiles: [],
  accessibleFolders: [],
  sharedFolders: [],
};

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("App root not found");
}

app.innerHTML = `
  <div class="shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">Enterprise Webhard</p>
        <h1>${config.appTitle}</h1>
      </div>
      <div class="session">
        <span id="sessionLabel">로그인 필요</span>
        <button id="logoutBtn" class="ghost" disabled>로그아웃</button>
      </div>
    </header>

    <main class="grid">
      <section class="card">
        <h2>인증</h2>
        <form id="registerForm" class="stack">
          <h3>회원가입</h3>
          <input name="username" placeholder="username" minlength="3" required />
          <input name="password" type="password" placeholder="password" minlength="8" required />
          <button type="submit">가입</button>
        </form>
        <form id="loginForm" class="stack">
          <h3>로그인</h3>
          <input name="username" placeholder="username" minlength="3" required />
          <input name="password" type="password" placeholder="password" minlength="8" required />
          <button type="submit">로그인</button>
        </form>
      </section>

      <section class="card">
        <h2>폴더</h2>
        <form id="folderForm" class="inline">
          <input name="path" placeholder="team/docs" required />
          <button type="submit">폴더 생성</button>
        </form>
        <div class="two-col">
          <div>
            <h3>접근 가능한 폴더</h3>
            <ul id="accessibleFolders" class="list"></ul>
          </div>
          <div>
            <h3>공유 받은 폴더</h3>
            <ul id="sharedFolders" class="list"></ul>
          </div>
        </div>
      </section>

      <section class="card wide">
        <h2>파일</h2>
        <form id="uploadForm" class="inline-wrap">
          <input name="path" placeholder="team/docs/hello.txt" required />
          <input name="file" type="file" required />
          <button type="submit">업로드</button>
        </form>

        <form id="browseForm" class="inline-wrap">
          <input name="prefix" placeholder="prefix (예: team)" />
          <input name="ownerId" type="number" min="1" placeholder="owner_id(공유 폴더 조회 시)" />
          <button type="submit">파일 조회</button>
        </form>

        <div class="two-col">
          <div>
            <h3>파일 목록</h3>
            <ul id="fileList" class="list"></ul>
          </div>
          <div>
            <h3>공유 파일</h3>
            <ul id="sharedFileList" class="list"></ul>
          </div>
        </div>
      </section>

      <section class="card">
        <h2>파일 액션</h2>
        <form id="fileActionForm" class="stack">
          <input name="fileId" type="number" min="1" placeholder="file_id" required />
          <div class="inline-wrap">
            <button type="button" data-action="download">다운로드 URL</button>
            <button type="button" data-action="versions">버전 목록</button>
            <button type="button" data-action="trash">휴지통 이동</button>
            <button type="button" data-action="restore">복원</button>
          </div>
        </form>
        <pre id="actionOutput" class="output"></pre>
      </section>

      <section class="card">
        <h2>공유 링크 생성</h2>
        <form id="shareForm" class="stack">
          <input name="fileId" type="number" min="1" placeholder="file_id" required />
          <input name="expiresInSec" type="number" min="60" max="2592000" value="3600" required />
          <input name="password" placeholder="옵션: 비밀번호" />
          <input name="maxDownloads" type="number" min="1" placeholder="옵션: 최대 다운로드 횟수" />
          <label><input name="allowDownload" type="checkbox" checked /> 다운로드 허용</label>
          <label><input name="allowUpload" type="checkbox" /> 업로드 허용</label>
          <label><input name="oneTime" type="checkbox" /> 1회성 링크</label>
          <button type="submit">공유 생성</button>
        </form>
      </section>
    </main>

    <div id="toast" class="toast" aria-live="polite"></div>
  </div>
`;

const q = <T extends HTMLElement>(selector: string): T => {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`Missing element: ${selector}`);
  return el;
};

const sessionLabel = q<HTMLSpanElement>("#sessionLabel");
const logoutBtn = q<HTMLButtonElement>("#logoutBtn");
const accessibleFoldersEl = q<HTMLUListElement>("#accessibleFolders");
const sharedFoldersEl = q<HTMLUListElement>("#sharedFolders");
const fileListEl = q<HTMLUListElement>("#fileList");
const sharedFileListEl = q<HTMLUListElement>("#sharedFileList");
const actionOutputEl = q<HTMLPreElement>("#actionOutput");
const toastEl = q<HTMLDivElement>("#toast");

function notify(message: string, isError = false): void {
  toastEl.textContent = message;
  toastEl.classList.toggle("error", isError);
  toastEl.classList.add("show");
  window.setTimeout(() => toastEl.classList.remove("show"), 2600);
}

function setSession(token: string | null, username: string | null): void {
  state.token = token;
  state.username = username;
  api.setToken(token);
  if (token && username) {
    sessionStore.save(token, username);
    sessionLabel.textContent = `${username} 로그인됨`;
    logoutBtn.disabled = false;
  } else {
    sessionStore.clear();
    sessionLabel.textContent = "로그인 필요";
    logoutBtn.disabled = true;
  }
}

function renderFolders(): void {
  accessibleFoldersEl.innerHTML = state.accessibleFolders
    .map(
      (item) =>
        `<li><strong>${item.folder_path}</strong> <small>owner:${item.owner_id} | ${item.source} | R:${item.can_read ? 1 : 0} U:${item.can_upload ? 1 : 0} M:${item.can_manage ? 1 : 0}</small></li>`,
    )
    .join("");

  sharedFoldersEl.innerHTML = state.sharedFolders
    .map((item) => `<li><strong>${item.folder_path}</strong> <small>owner:${item.owner_id}</small></li>`)
    .join("");
}

function renderFiles(): void {
  fileListEl.innerHTML = state.files
    .map((item) => `<li><strong>${item.logical_path}</strong> <small>id:${item.file_id} | v:${item.current_version}</small></li>`)
    .join("");

  sharedFileListEl.innerHTML = state.sharedFiles
    .map((item) => `<li><strong>${item.logical_path}</strong> <small>id:${item.file_id} | v:${item.current_version}</small></li>`)
    .join("");
}

function showJson(data: unknown): void {
  actionOutputEl.textContent = JSON.stringify(data, null, 2);
}

async function withGuard<T>(task: () => Promise<T>): Promise<T | undefined> {
  try {
    return await task();
  } catch (error) {
    if (error instanceof HttpError) {
      if (error.status === 401) {
        setSession(null, null);
      }
      notify(error.detail, true);
      return undefined;
    }
    notify("예상치 못한 오류가 발생했습니다.", true);
    return undefined;
  }
}

async function refreshDashboard(): Promise<void> {
  if (!state.token) {
    return;
  }

  const [folders, sharedFolders, files, sharedFiles] = await Promise.all([
    withGuard(() => api.listAccessibleFolders()),
    withGuard(() => api.listSharedFolders()),
    withGuard(() => api.listFiles()),
    withGuard(() => api.listSharedFiles()),
  ]);

  state.accessibleFolders = folders?.accessible_folders || [];
  state.sharedFolders = sharedFolders?.shared_folders || [];
  state.files = files?.files || [];
  state.sharedFiles = sharedFiles?.shared_files || [];

  renderFolders();
  renderFiles();
}

q<HTMLFormElement>("#registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget as HTMLFormElement;
  const data = new FormData(form);
  const username = String(data.get("username") || "").trim();
  const password = String(data.get("password") || "").trim();
  const res = await withGuard(() => api.register({ username, password }));
  if (!res) return;
  notify(`가입 완료: ${res.username}`);
  form.reset();
});

q<HTMLFormElement>("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget as HTMLFormElement;
  const data = new FormData(form);
  const username = String(data.get("username") || "").trim();
  const password = String(data.get("password") || "").trim();
  const res = await withGuard(() => api.login({ username, password }));
  if (!res) return;
  setSession(res.access_token, res.username);
  notify("로그인 성공");
  await refreshDashboard();
});

logoutBtn.addEventListener("click", () => {
  setSession(null, null);
  state.files = [];
  state.sharedFiles = [];
  state.accessibleFolders = [];
  state.sharedFolders = [];
  renderFiles();
  renderFolders();
  showJson({ message: "logged out" });
});

q<HTMLFormElement>("#folderForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget as HTMLFormElement;
  const data = new FormData(form);
  const path = String(data.get("path") || "").trim();
  const res = await withGuard(() => api.createFolder(path));
  if (!res) return;
  notify(`폴더 생성: ${res.path}`);
  form.reset();
  await refreshDashboard();
});

q<HTMLFormElement>("#uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget as HTMLFormElement;
  const data = new FormData(form);
  const path = String(data.get("path") || "").trim();
  const file = data.get("file");
  if (!(file instanceof File)) {
    notify("파일을 선택해 주세요.", true);
    return;
  }
  const res = await withGuard(() => api.uploadFile(path, file));
  if (!res) return;
  notify(`업로드 완료: file_id=${res.file_id}`);
  form.reset();
  await refreshDashboard();
});

q<HTMLFormElement>("#browseForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget as HTMLFormElement;
  const data = new FormData(form);
  const prefix = String(data.get("prefix") || "").trim();
  const ownerRaw = String(data.get("ownerId") || "").trim();
  const ownerId = ownerRaw ? Number(ownerRaw) : undefined;
  const res = await withGuard(() => api.listFiles(prefix, false, Number.isFinite(ownerId) ? ownerId : undefined));
  if (!res) return;
  state.files = res.files;
  renderFiles();
  notify("파일 목록 갱신 완료");
});

q<HTMLFormElement>("#fileActionForm").addEventListener("click", async (event) => {
  const target = event.target as HTMLElement;
  const action = target.getAttribute("data-action");
  if (!action) return;

  const form = q<HTMLFormElement>("#fileActionForm");
  const data = new FormData(form);
  const fileId = Number(data.get("fileId"));
  if (!Number.isFinite(fileId) || fileId <= 0) {
    notify("올바른 file_id를 입력해 주세요.", true);
    return;
  }

  if (action === "download") {
    const res = await withGuard(() => api.getDownloadUrl(fileId));
    if (!res) return;
    showJson(res);
    window.open(res.url, "_blank", "noopener,noreferrer");
    return;
  }

  if (action === "versions") {
    const res = await withGuard(() => api.listVersions(fileId));
    if (!res) return;
    showJson(res);
    return;
  }

  if (action === "trash") {
    const res = await withGuard(() => api.moveToTrash(fileId));
    if (!res) return;
    showJson(res);
    await refreshDashboard();
    return;
  }

  if (action === "restore") {
    const res = await withGuard(() => api.restoreFile(fileId));
    if (!res) return;
    showJson(res);
    await refreshDashboard();
  }
});

q<HTMLFormElement>("#shareForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget as HTMLFormElement;
  const data = new FormData(form);

  const fileId = Number(data.get("fileId"));
  const expiresInSec = Number(data.get("expiresInSec"));
  const password = String(data.get("password") || "").trim();
  const maxDownloadsRaw = String(data.get("maxDownloads") || "").trim();

  if (!Number.isFinite(fileId) || fileId <= 0) {
    notify("유효한 file_id를 입력해 주세요.", true);
    return;
  }

  const payload = {
    expires_in_sec: expiresInSec,
    password: password || undefined,
    allow_download: Boolean(data.get("allowDownload")),
    allow_upload: Boolean(data.get("allowUpload")),
    one_time: Boolean(data.get("oneTime")),
    max_downloads: maxDownloadsRaw ? Number(maxDownloadsRaw) : undefined,
  };

  const res = await withGuard(() => api.createShare(fileId, payload));
  if (!res) return;
  showJson(res);
  notify(`공유 토큰 생성: ${res.share_token}`);
});

async function bootstrap(): Promise<void> {
  setSession(state.token, state.username);
  if (state.token) {
    await refreshDashboard();
  }
}

bootstrap().catch(() => {
  notify("앱 초기화 중 오류가 발생했습니다.", true);
});
