import { Link } from "react-router-dom";
import { api, fileUrl, fmtDate } from "../api";
import { Empty, JobProgress, StageBar, Status, useAction, usePoll } from "../ui";

const KIND_LABEL: Record<string, string> = {
  script: "Écriture", scene_regen: "Réécriture de scène", critique: "Critique", storyboard: "Storyboard + traduction",
  assets: "Voix FR/EN", preview: "Prévisualisation", final: "Rendu vidéo", publish: "Packs de publication",
  library_seed: "Bibliothèque", inspiration_analyze: "Analyse d'inspiration", models_download: "Téléchargement des modèles",
};

export default function Dashboard() {
  const { data, reload } = usePoll<any>("/api/dashboard", 2500);
  const { run } = useAction();
  if (!data) return <p className="muted">Chargement…</p>;
  const paused = data.settings.queue_paused;
  const total = data.series.reduce((a: number, s: any) => a + s.episodes_total, 0);
  const published = data.series.reduce((a: number, s: any) => a + s.published, 0);
  const ready = data.series.reduce((a: number, s: any) => a + (s.counts.ready_to_publish || 0), 0);
  return (
    <div className="stack">
      <div className="hero">
        <h1>Votre studio multivers</h1>
        <p>Trois séries, une seule validation par épisode, versions française et anglaise, voix et sous-titres façon TikTok.
          Donnez une idée, choisissez un style, le studio s'occupe du reste.</p>
        <div className="row" style={{ marginTop: 14 }}>
          <Link to="/creation"><button className="primary">＋ Créer un épisode</button></Link>
          <Link to="/inspirations"><button>✦ Ajouter une recette depuis TikTok</button></Link>
        </div>
        <div className="kpis">
          <div className="kpi"><b>{total}</b><span>épisodes</span></div>
          <div className="kpi"><b>{data.validations_pending}</b><span>à valider</span></div>
          <div className="kpi"><b>{ready}</b><span>prêts à publier</span></div>
          <div className="kpi"><b>{published}</b><span>publiés</span></div>
          <div className="kpi"><b>{data.month_spend_usd.toFixed(2)} $</b><span>IA ce mois (budget {data.settings.budget_monthly_usd} $)</span></div>
        </div>
      </div>

      {data.validations_pending > 0 && (
        <div className="callout">
          <span className="big">✋</span>
          <div style={{ flex: 1 }}><b>{data.validations_pending} élément(s) attendent votre décision.</b>
            <div className="small muted">Les épisodes finis vous attendent avec les vidéos et l'explication complète.</div></div>
          <Link to="/validations"><button className="primary">Valider maintenant</button></Link>
        </div>
      )}

      <div className="grid g3">
        {data.series.map((s: any) => (
          <div key={s.id} className="panel scard" style={{ ["--accent" as any]: s.accent }}>
            <div className="cover" style={{ backgroundImage: s.cover ? `url(${fileUrl(s.cover)})` : undefined }}>
              <span className="code">SÉRIE {s.code}</span>
            </div>
            <div className="body">
              <h3>{s.name}</h3>
              <p className="small muted" style={{ minHeight: 40 }}>{s.pitch?.slice(0, 120)}{s.pitch?.length > 120 ? "…" : ""}</p>
              <div className="row small" style={{ gap: 16 }}>
                <span><b>{s.episodes_total}</b> <span className="muted">épisodes</span></span>
                <span><b>{s.published}</b> <span className="muted">publiés</span></span>
                {s.pending_gates > 0 && <span className="pill amber">{s.pending_gates} à valider</span>}
              </div>
              {s.current && (
                <div style={{ marginTop: 10 }}>
                  <div className="row between small"><span>Ép. {s.current.number} {s.current.title && `— ${s.current.title}`}</span><Status s={s.current.status} /></div>
                  <StageBar ep={s.current} accent={s.accent} />
                  <div className="tiny muted">{s.current.stage_label}</div>
                </div>
              )}
              {s.lock.locked ? <div className="lock" style={{ marginTop: 10 }}>🔒 {s.lock.reason}</div> : (
                <Link to={`/creation?series=${s.id}`}><button className="sm" style={{ marginTop: 12 }}>＋ Nouvel épisode</button></Link>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="grid g2">
        <div className="panel">
          <div className="row between">
            <h2>En cours</h2>
            <button className={`sm ${paused ? "amber" : "ghost"}`}
              onClick={() => run(() => api.post(`/api/queue/${paused ? "resume" : "pause"}`), paused ? "File reprise" : "File en pause").then(reload)}>
              {paused ? "▶ Reprendre" : "⏸ Pause"}
            </button>
          </div>
          {data.jobs.length === 0 ? <Empty>Rien en cours. Créez un épisode pour lancer le studio.</Empty> : data.jobs.map((j: any) => (
            <div key={j.id} className="list-item">
              <div className="row between small">
                <span><b>{KIND_LABEL[j.kind] || j.kind}</b> {j.episode_number && <span className="muted">· {j.series_id} ép. {j.episode_number}</span>}</span>
                <span className="row"><Status s={j.status} />
                  <button className="sm ghost" onClick={() => run(() => api.post(`/api/jobs/${j.id}/cancel`), "Annulation demandée")}>✕</button></span>
              </div>
              <div className="tiny muted" style={{ margin: "4px 0" }}>{j.message}</div>
              <JobProgress job={j} />
            </div>
          ))}
        </div>
        <div className="panel">
          <h2>Activité</h2>
          <div className="log" style={{ maxHeight: 300 }}>
            {data.recent_events.map((e: any) => <div key={e.id} className={e.level}>{fmtDate(e.ts)} · {e.message}</div>)}
          </div>
        </div>
      </div>
    </div>
  );
}
