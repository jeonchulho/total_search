export class HttpError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

export class HttpClient {
  private readonly baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  async request<T>(
    path: string,
    init: RequestInit = {},
    timeoutMs = 15000,
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const headers = new Headers(init.headers || {});
    if (this.token) {
      headers.set("Authorization", `Bearer ${this.token}`);
    }

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        signal: controller.signal,
      });

      const contentType = response.headers.get("content-type") || "";
      const isJson = contentType.includes("application/json");
      const body = isJson ? await response.json() : await response.text();

      if (!response.ok) {
        const detail =
          typeof body === "object" && body !== null && "detail" in body
            ? String((body as { detail: string }).detail)
            : `Request failed (${response.status})`;
        throw new HttpError(response.status, detail);
      }

      return body as T;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new HttpError(408, "요청 시간이 초과되었습니다.");
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
}
