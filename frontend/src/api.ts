// Client API minimal. Toutes les données viennent du serveur local (aucun service externe).
export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const r = await fetch(url, init);
  const text = await r.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!r.ok) {
    const msg =
      (data && (data.error || (typeof data.detail === "string" ? data.detail : null))) ||
      (data && Array.isArray(data.detail) ? data.detail.map((d: any) => d.msg).join(" ; ") : null) ||
      `Erreur ${r.status}`;
    throw new ApiError(msg, r.status, data?.code);
  }
  return data as T;
}

export const api = {
  get: <T = any>(u: string) => request<T>("GET", u),
  post: <T = any>(u: string, b?: unknown) => request<T>("POST", u, b ?? {}),
  put: <T = any>(u: string, b?: unknown) => request<T>("PUT", u, b ?? {}),
  patch: <T = any>(u: string, b?: unknown) => request<T>("PATCH", u, b ?? {}),
  del: <T = any>(u: string) => request<T>("DELETE", u),
};

export const fileUrl = (rel?: string | null) => (rel ? `/files/${rel}` : "");

export const SERIES_COLORS: Record<string, string> = {
  horror: "#ff4d6d",
  football: "#3ddc84",
  isekai: "#b48cff",
};

export function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

export function fmtBytes(n: number) {
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} Mo`;
  if (n > 1e3) return `${(n / 1e3).toFixed(0)} Ko`;
  return `${n} o`;
}
