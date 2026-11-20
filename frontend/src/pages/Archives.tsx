import { Link } from "react-router-dom";
import { fileUrl, fmtBytes, fmtDate } from "../api";
import { Empty, PageHead, SeriesPill, Status, usePoll } from "../ui";

export default function Archives() {
  const { data } = usePoll<any>("/api/archives", 8000);
  return (
    <div className="stack">
      <PageHead title="Archives" sub={data ? `Tout est stocké localement dans ${data.data_dir}` : "Épisodes, sources, versions et MP4 sur votre PC."} />
      <div className="panel">
        <h2>Épisodes</h2>
        {data && !data.episodes.length && <Empty>Aucun épisode.</Empty>}
        <table>
          <thead><tr><th>Série</th><th>Ép.</th><th>Titre</th><th>Statut</th><th>Versions</th><th>Vidéos</th><th>Pack</th></tr></thead>
          <tbody>
            {data?.episodes.map((e: any) => (
              <tr key={e.id}>
                <td><SeriesPill id={e.series_id} /></td>
                <td>{e.number}</td>
                <td><Link to={`/scenarios?ep=${e.id}`}>{e.title || e.intent.slice(0, 40)}</Link><div className="tiny muted">{fmtDate(e.created_at)}</div></td>
                <td><Status s={e.status} /><div className="tiny muted">{e.stage_label}</div></td>
                <td className="small">{e.script_versions} script(s) · {e.storyboard_versions} storyboard(s)</td>
                <td className="small">{e.renders.map((r: any) => (
                  <div key={r.id}><a href={fileUrl(r.path)} target="_blank" rel="noreferrer">{r.kind}</a> <span className="muted">{r.width}×{r.height} · {fmtBytes(r.size_bytes)}</span></div>
                ))}{!e.renders.length && <span className="muted">—</span>}</td>
                <td className="tiny mono">{e.pack_folder || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <h2>Sauvegardes de la base</h2>
        <p className="small muted">Une sauvegarde est faite chaque jour au démarrage et avant toute migration (jamais supprimée). Bouton « Sauvegarder maintenant » dans Paramètres.</p>
        {data?.backups.map((b: any) => <div key={b.name} className="small mono">{b.name} · {fmtBytes(b.size)}</div>)}
        {data && !data.backups.length && <p className="small muted">Aucune sauvegarde pour l'instant.</p>}
      </div>
    </div>
  );
}
