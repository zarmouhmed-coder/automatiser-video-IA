import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, SERIES_COLORS } from "../api";
import { SeriesPill, StageBar, Status, useAction, usePoll } from "../ui";

export function useSelectedEpisode() {
  const [params, setParams] = useSearchParams();
  const id = params.get("ep");
  return [id ? Number(id) : null, (v: number) => setParams({ ep: String(v) })] as const;
}

export function EpisodeList({ selected, onSelect }: { selected: number | null; onSelect: (id: number) => void }) {
  const [filter, setFilter] = useState("");
  const { data } = usePoll<any[]>(`/api/episodes${filter ? `?series_id=${filter}` : ""}`, 3000);
  return (
    <div className="panel">
      <div className="row between">
        <h2>Épisodes</h2>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: "auto" }}>
          <option value="">Toutes séries</option>
          <option value="horror">A · Horreur</option>
          <option value="football">B · Football</option>
          <option value="isekai">C · Isekai</option>
        </select>
      </div>
      {!data?.length && <p className="small muted">Aucun épisode. Créez-en un dans « Création ».</p>}
      {data?.map((e) => (
        <div key={e.id} className={`list-item clickable ${selected === e.id ? "selected" : ""}`} onClick={() => onSelect(e.id)}>
          <div className="row between small">
            <span>
              <SeriesPill id={e.series_id} /> <b>Ép. {e.number}</b>
            </span>
            <Status s={e.status} />
          </div>
          <div className="small" style={{ marginTop: 4 }}>{e.title || <span className="muted">{e.intent.slice(0, 60)}</span>}</div>
          <StageBar ep={e} accent={SERIES_COLORS[e.series_id]} />
          <div className="tiny muted">{e.stage_label}</div>
        </div>
      ))}
    </div>
  );
}

export function GateBar({ detail, stage, reload, extra }: { detail: any; stage: string; reload: () => void; extra?: React.ReactNode }) {
  const gate = detail.gates.find((g: any) => g.status === "pending" && g.stage === stage);
  const [note, setNote] = useState("");
  const { run, busy } = useAction();
  if (!gate) return null;
  const decide = (action: string) =>
    run(() => api.post(`/api/gates/${gate.id}/decide`, { action, note }),
      { approve: "Validé : étape suivante lancée", changes: "Modification demandée", reject: "Rejeté" }[action]).then(() => {
      setNote("");
      reload();
    });
  return (
    <div className="panel" style={{ ["--accent" as any]: "var(--amber)", borderColor: "rgba(255,176,0,.45)" }}>
      <h2 style={{ color: "var(--amber)" }}>Votre validation est requise</h2>
      <textarea rows={2} placeholder="Note (obligatoire pour une demande de modification ; mémorisée par l'agent)"
        value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="primary" disabled={busy} onClick={() => decide("approve")}>✓ Approuver</button>
        <button className="amber" disabled={busy || !note.trim()} onClick={() => decide("changes")}>✎ Demander une modification</button>
        <button className="danger" disabled={busy} onClick={() => confirm("Rejeter cet épisode ?") && decide("reject")}>✕ Rejeter</button>
        {extra}
      </div>
    </div>
  );
}

export function JobsPanel({ detail, reload }: { detail: any; reload: () => void }) {
  const { run } = useAction();
  const active = detail.jobs.filter((j: any) => ["queued", "running"].includes(j.status));
  const failed = detail.jobs[0] && ["failed", "cancelled"].includes(detail.jobs[0].status) ? detail.jobs[0] : null;
  return (
    <>
      {active.map((j: any) => (
        <div key={j.id} className="list-item">
          <div className="row between small">
            <span><span className="dot live" /> <b>{j.kind}</b> — {j.message}</span>
            <button className="sm danger" onClick={() => run(() => api.post(`/api/jobs/${j.id}/cancel`), "Annulation demandée").then(reload)}>
              Annuler
            </button>
          </div>
          <div style={{ marginTop: 6 }}>
            {j.status === "running" && j.progress != null ? (
              <div className="progress"><span style={{ width: `${Math.round(j.progress * 100)}%` }} /></div>
            ) : j.status === "running" ? <div className="indeterminate" /> : <span className="tiny muted">En file d'attente…</span>}
          </div>
        </div>
      ))}
      {failed && !active.length && (
        <div className="lock">
          <b>{failed.status === "failed" ? "Échec" : "Annulée"} — {failed.kind}</b> : {failed.error || failed.message}
          <div style={{ marginTop: 8 }}>
            <button className="sm amber" onClick={() => run(() => api.post(`/api/episodes/${detail.episode.id}/retry`), "Étape relancée").then(reload)}>
              ↻ Relancer l'étape
            </button>
          </div>
        </div>
      )}
    </>
  );
}
