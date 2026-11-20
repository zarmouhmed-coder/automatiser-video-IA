import { Link } from "react-router-dom";
import { api, fmtDate } from "../api";
import { Empty, PageHead, SeriesPill, Status, useAction, usePoll } from "../ui";

const PAGE_FOR_STAGE: Record<string, string> = { script: "/scenarios", storyboard: "/production", preview: "/production", final: "/production" };

export default function Validations() {
  const { data, reload } = usePoll<any[]>("/api/validations", 3000);
  const { run, busy } = useAction();
  const items = data || [];
  const groups: [string, string][] = [
    ["gate", "Livrables de production"], ["vote", "Votes du public"], ["canon", "Propositions de canon"],
    ["character", "Nouveaux personnages"], ["observer", "Observateurs (isekai)"],
  ];
  return (
    <div className="stack">
      <PageHead title="Validations" sub="Rien n'avance ni ne devient canon sans votre accord : approuvez, modifiez ou rejetez chaque élément." />
      {data && items.length === 0 && <Empty>Tout est à jour. Aucune validation en attente.</Empty>}
      {groups.map(([type, label]) => {
        const list = items.filter((i) => i.type === type);
        if (!list.length) return null;
        return (
          <div key={type} className="panel">
            <h2>{label} ({list.length})</h2>
            {list.map((i) => (
              <div key={`${type}-${i.id}`} className="list-item">
                <div className="row between">
                  <span className="row"><SeriesPill id={i.series_id} /> <span>{i.title}</span></span>
                  <span className="tiny muted">{fmtDate(i.created_at)}</span>
                </div>
                <div className="row" style={{ marginTop: 8 }}>
                  {type === "gate" && (
                    <Link to={`${PAGE_FOR_STAGE[i.stage]}?ep=${i.episode_id}`}><button className="primary sm">Examiner et décider →</button></Link>
                  )}
                  {type === "canon" && (
                    <>
                      <button className="sm primary" disabled={busy} onClick={() => run(() => api.post(`/api/facts/${i.id}/decide`, { action: "accept" }), "Ajouté au canon").then(reload)}>Accepter</button>
                      <button className="sm amber" disabled={busy} onClick={() => {
                        const t = prompt("Version modifiée du fait :", i.title);
                        if (t) run(() => api.post(`/api/facts/${i.id}/decide`, { action: "accept", final_text: t }), "Version modifiée ajoutée au canon").then(reload);
                      }}>Modifier puis accepter</button>
                      <button className="sm danger" disabled={busy} onClick={() => run(() => api.post(`/api/facts/${i.id}/decide`, { action: "reject" }), "Rejeté").then(reload)}>Rejeter</button>
                    </>
                  )}
                  {type === "character" && (
                    <>
                      <button className="sm primary" onClick={() => run(() => api.patch(`/api/characters/${i.id}`, { status: "canon" }), "Personnage ajouté au canon").then(reload)}>Accepter</button>
                      <button className="sm danger" onClick={() => run(() => api.patch(`/api/characters/${i.id}`, { status: "rejected" }), "Personnage rejeté").then(reload)}>Rejeter</button>
                      <Link to="/bible" className="small">Modifier dans la bible</Link>
                    </>
                  )}
                  {type === "vote" && (<><Status s={i.status} /><Link to="/communaute"><button className="sm amber">Saisir / valider le résultat →</button></Link></>)}
                  {type === "observer" && (<><Status s={i.status} /><Link to="/communaute?tab=observers"><button className="sm amber">Analyser / décider →</button></Link></>)}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
