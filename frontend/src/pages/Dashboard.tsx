import { Link } from "react-router-dom";
import { api, fmtDate } from "../api";
import { Empty, JobProgress, PageHead, StageBar, Status, useAction, usePoll } from "../ui";

export default function Dashboard() {
  const { data, reload } = usePoll<any>("/api/dashboard", 2500);
  const { run } = useAction();
  if (!data) return <p className="muted">Chargement…</p>;
  const paused = data.settings.queue_paused;
  return (
    <div className="stack">
      <PageHead title="Dashboard" sub="Progression réelle des trois séries, tâches et validations en attente.">
        <Link to="/creation">
          <button className="primary">＋ Nouvel épisode</button>
        </Link>
        <button
          className={paused ? "amber" : ""}
          onClick={() => run(() => api.post(`/api/queue/${paused ? "resume" : "pause"}`), paused ? "File reprise" : "File en pause").then(reload)}
        >
          {paused ? "▶ Reprendre la file" : "⏸ Mettre la file en pause"}
        </button>
      </PageHead>

      <div className="grid g3">
        {data.series.map((s: any) => (
          <div key={s.id} className="panel series-card" style={{ ["--accent" as any]: s.accent }}>
            <div className="row between">
              <span className="series-code">SÉRIE {s.code}</span>
              {s.pending_gates > 0 && <span className="pill amber">{s.pending_gates} à valider</span>}
            </div>
            <h3 style={{ marginTop: 6 }}>{s.name}</h3>
            <p className="muted small">{s.genre}</p>
            <div className="row" style={{ gap: 22 }}>
              <div>
                <div className="big-num">{s.episodes_total}</div>
                <div className="tiny muted">épisodes</div>
              </div>
              <div>
                <div className="big-num">{s.published}</div>
                <div className="tiny muted">publiés</div>
              </div>
              <div>
                <div className="big-num">{s.counts.ready_to_publish || 0}</div>
                <div className="tiny muted">prêts</div>
              </div>
            </div>
            <hr />
            {s.current ? (
              <div>
                <div className="row between small">
                  <span>
                    Ép. {s.current.number} {s.current.title && `— ${s.current.title}`}
                  </span>
                  <Status s={s.current.status} />
                </div>
                <StageBar stage={s.current.stage} accent={s.accent} />
                <div className="small muted">Étape : {s.current.stage_label}</div>
              </div>
            ) : (
              <p className="small muted">Aucun épisode en cours.</p>
            )}
            {s.lock.locked && <div className="lock" style={{ marginTop: 10 }}>🔒 {s.lock.reason}</div>}
          </div>
        ))}
      </div>

      <div className="grid g2">
        <div className="panel">
          <div className="row between">
            <h2>File d'attente</h2>
            <span className="small muted">3 workflows max · 1 rendu lourd à la fois</span>
          </div>
          {data.jobs.length === 0 ? (
            <Empty>Aucune tâche en cours.</Empty>
          ) : (
            data.jobs.map((j: any) => (
              <div key={j.id} className="list-item">
                <div className="row between small">
                  <span>
                    <b>{j.kind}</b> {j.episode_number && <span className="muted">· ép. {j.episode_number} ({j.series_id})</span>}
                    {j.heavy ? <span className="pill amber" style={{ marginLeft: 6 }}>rendu lourd</span> : null}
                  </span>
                  <span className="row">
                    <Status s={j.status} />
                    <button className="sm danger" onClick={() => run(() => api.post(`/api/jobs/${j.id}/cancel`), "Annulation demandée")}>
                      Annuler
                    </button>
                  </span>
                </div>
                <div className="tiny muted" style={{ margin: "4px 0" }}>{j.message}</div>
                <JobProgress job={j} />
              </div>
            ))
          )}
        </div>
        <div className="panel">
          <div className="row between">
            <h2>Activité récente</h2>
            <Link to="/validations" className="small">
              {data.validations_pending} validation(s) en attente →
            </Link>
          </div>
          <div className="log" style={{ maxHeight: 300 }}>
            {data.recent_events.map((e: any) => (
              <div key={e.id} className={e.level}>
                {fmtDate(e.ts)} · {e.message}
              </div>
            ))}
          </div>
          <p className="tiny muted" style={{ marginTop: 8 }}>
            Dépenses IA du mois : {data.month_spend_usd.toFixed(2)} $ / budget {data.settings.budget_monthly_usd} $
          </p>
        </div>
      </div>
    </div>
  );
}
