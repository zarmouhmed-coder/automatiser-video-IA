import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, SERIES_COLORS } from "./api";

// ---------------------------------------------------------------- données

export function usePoll<T>(url: string | null, intervalMs = 2500) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const urlRef = useRef(url);
  urlRef.current = url;
  const load = useCallback(async () => {
    if (!urlRef.current) return;
    try {
      const d = await api.get<T>(urlRef.current);
      setData(d);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    setData(null);
    load();
    if (!intervalMs) return;
    const t = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, intervalMs);
    return () => clearInterval(t);
  }, [url, intervalMs, load]);
  return { data, error, reload: load };
}

// ---------------------------------------------------------------- toasts

type Toast = { id: number; msg: string; err?: boolean };
const ToastCtx = createContext<(msg: string, err?: boolean) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((msg: string, err = false) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, msg, err }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), err ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.err ? "err" : ""}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

/** Exécute une action API avec retour visuel (toast succès/erreur). */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
      setBusy(true);
      try {
        const r = await fn();
        if (ok) toast(ok);
        return r;
      } catch (e: any) {
        toast(e.message || String(e), true);
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );
  return { run, busy };
}

// ---------------------------------------------------------------- éléments

export function SeriesPill({ id, name }: { id: string; name?: string }) {
  const c = SERIES_COLORS[id] || "#00e5ff";
  return (
    <span className="pill" style={{ color: c, borderColor: c + "88", background: c + "12" }}>
      {name || { horror: "Horreur", football: "Football", isekai: "Isekai" }[id] || id}
    </span>
  );
}

const STATUS: Record<string, [string, string]> = {
  in_progress: ["En production", ""],
  waiting_validation: ["En attente de validation", "amber"],
  ready_to_publish: ["Prêt à publier", "green"],
  published: ["Publié", "green"],
  rejected: ["Rejeté", "red"],
  queued: ["En file", "gray"],
  running: ["En cours", ""],
  done: ["Terminé", "green"],
  failed: ["Échec", "red"],
  cancelled: ["Annulé", "gray"],
  pending: ["En attente", "amber"],
  approved: ["Approuvé", "green"],
  changes_requested: ["Modifs demandées", "amber"],
  superseded: ["Remplacé", "gray"],
  open: ["Vote ouvert", "amber"],
  result_entered: ["Résultat à valider", "amber"],
  validated: ["Validé", "green"],
  analyzed: ["Analysé", ""],
  accepted: ["Accepté", "green"],
  adapted: ["Adapté", "green"],
  proposed: ["Proposé", "amber"],
  canon: ["Canon", "green"],
};

export function Status({ s }: { s: string }) {
  const [label, cls] = STATUS[s] || [s, "gray"];
  return <span className={`pill ${cls}`}>{label}</span>;
}

export function StageBar({ ep, accent }: { ep: { stage_index?: number; stage_total?: number; stage?: string }; accent?: string }) {
  const total = ep.stage_total || 1;
  const idx = ep.stage_index ?? 0;
  return (
    <div className="stages" style={{ ["--accent" as any]: accent }} title={ep.stage}>
      {Array.from({ length: total }, (_, i) => (
        <i key={i} className={i < idx ? "done" : i === idx ? "now" : ""} />
      ))}
    </div>
  );
}

export function JobProgress({ job }: { job: any }) {
  if (job.status === "running" && job.progress != null)
    return (
      <div className="progress" title={`${Math.round(job.progress * 100)} %`}>
        <span style={{ width: `${Math.round(job.progress * 100)}%` }} />
      </div>
    );
  if (job.status === "running") return <div className="indeterminate" title="Durée inconnue : pas de pourcentage inventé" />;
  return null;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function PageHead({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children && <div className="row">{children}</div>}
    </div>
  );
}

export function CopyBox({ text, label }: { text: string; label?: string }) {
  const toast = useToast();
  return (
    <div className="field">
      <div className="row between">
        {label && <label>{label}</label>}
        <button
          className="sm ghost"
          onClick={() => {
            navigator.clipboard?.writeText(text).then(
              () => toast("Copié dans le presse-papiers"),
              () => toast("Copie impossible : sélectionnez le texte", true),
            );
          }}
        >
          Copier
        </button>
      </div>
      <div className="copy-box">{text}</div>
    </div>
  );
}
