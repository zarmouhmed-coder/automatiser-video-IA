import { Link } from "react-router-dom";
import { api, fmtDate } from "../api";
import { Empty, PageHead, SeriesPill, Status, useAction, usePoll } from "../ui";
import EpisodeReview from "./EpisodeReview";

const PAGE_FOR_STAGE: Record<string, string> = { script: "/scenarios", storyboard: "/production", preview: "/production", final: "/production" };

export default function Validations() {
  const { data, reload } = usePoll<any[]>("/api/validations", 4000);
  const { data: episodes } = usePoll<any[]>("/api/episodes", 6000);
  const { run, busy } = useAction();
  const items = data || [];
  const epGates = items.filter((i) => i.type === "gate" && i.stage === "episode");
  const groups: [string, string][] = [
    ["gate", "Validations détaillées (ancien mode)"], ["vote", "Résultats de vote à saisir"], ["canon", "Propositions de canon"],
    ["character", "Nouveaux personnages"], ["observer", "Observateurs (isekai)"],
  ];
  return (
    <div className="stack">
      <PageHead title="Validations" sub="Une seule validation par épisode : regardez la vidéo, lisez l'explication, décidez." />
      {data && items.length === 0 && <Empty>Tout est à jour. Aucune validation en attente.</Empty>}
      {epGates.map((g) => {
        const ep = episodes?.find((e) => e.id === g.episode_id);
        return ep ? <EpisodeReview key={g.id} gate={g} episode={ep} onDone={reload} /> : null;
      })}
      {groups.map(([type, label]) => {
        const list = items.filter((i) => i.type === type && !(type === "gate" && i.stage === "episode"));
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
                      <button className="sm danger" disabled={busy} onClick={() => run(() => api.post(`/api/facts/${i.id}/decide`, { action: "reject" }), "Rejeté").then(reload)}>Rejeter</button>
                    </>
                  )}
                  {type === "character" && (
                    <>
                      <button className="sm primary" onClick={() => run(() => api.patch(`/api/characters/${i.id}`, { status: "canon" }), "Personnage ajouté au canon").then(reload)}>Accepter</button>
                      <button className="sm danger" onClick={() => run(() => api.patch(`/api/characters/${i.id}`, { status: "rejected" }), "Personnage rejeté").then(reload)}>Rejeter</button>
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
