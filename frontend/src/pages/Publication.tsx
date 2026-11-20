import { useState } from "react";
import { api, fileUrl, fmtDate } from "../api";
import { CopyBox, Empty, PageHead, SeriesPill, Status, useAction, usePoll } from "../ui";

function PackView({ item, reload }: { item: any; reload: () => void }) {
  const pack = item.pack?.content;
  const [pf, setPf] = useState("tiktok");
  const [url, setUrl] = useState("");
  const { run, busy } = useAction();
  if (!pack) return <Empty>Pack en préparation…</Empty>;
  const p = pack.platforms[pf];
  const e = item.episode;
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(220px, 300px) minmax(0, 1fr)" }}>
      <div className="stack">
        <video src={fileUrl(pack.files.video) + "#t=1.5"} controls playsInline preload="metadata" />
        <a href={fileUrl(pack.files.video)} download><button className="primary" style={{ width: "100%" }}>⤓ Télécharger le MP4</button></a>
        <img src={fileUrl(pack.files.thumbnail)} alt="Miniature" style={{ width: "100%", borderRadius: 10 }} />
        <a href={fileUrl(pack.files.thumbnail)} download className="small">⤓ Miniature</a>
        <a href={fileUrl(pack.files.txt)} target="_blank" rel="noreferrer" className="small">Ouvrir pack.txt</a>
        <p className="tiny muted mono">{pack.folder}</p>
      </div>
      <div>
        <div className="tabs">
          {Object.entries(pack.platforms).map(([k, v]: any) => <button key={k} className={pf === k ? "on" : ""} onClick={() => setPf(k)}>{v.label}</button>)}
        </div>
        <CopyBox label="Titre" text={p.title} />
        <CopyBox label="Description" text={p.description} />
        <CopyBox label="Hashtags" text={p.hashtags.join(" ")} />
        <CopyBox label="Commentaire à épingler" text={p.pinned_comment} />
        {p.poll && <CopyBox label="Sondage (options courtes)" text={[p.poll.question, ...p.poll.options.map((o: string) => `• ${o}`)].join("\n")} />}
        <p className="tiny muted">{pack.disclosure} Activez l'étiquette « contenu généré par IA » si la plateforme la propose.</p>
        <hr />
        <h2>Après avoir publié vous-même</h2>
        {e.published_info?.platforms?.map((x: any, i: number) => <div key={i} className="small">✓ {x.platform} · {fmtDate(x.at)} {x.url && <a href={x.url} target="_blank" rel="noreferrer">lien</a>}</div>)}
        <div className="row" style={{ marginTop: 8 }}>
          <input style={{ maxWidth: 340 }} placeholder="Lien de la publication (facultatif)" value={url} onChange={(ev) => setUrl(ev.target.value)} />
          <button className="amber" disabled={busy} onClick={() => run(() => api.post(`/api/episodes/${e.id}/published`, { platform: p.label, url }),
            e.ends_with_vote ? "Marqué publié : le vote est ouvert dans Communauté" : "Marqué comme publié").then(reload)}>
            Marquer publié sur {p.label}
          </button>
        </div>
        {e.ends_with_vote ? <p className="tiny muted">Cet épisode se termine sur un vote : une fois publié, saisissez le résultat officiel dans Communauté pour débloquer l'épisode suivant.</p> : null}
      </div>
    </div>
  );
}

export default function Publication() {
  const { data, reload } = usePoll<any[]>("/api/publication", 5000);
  const [sel, setSel] = useState<number | null>(null);
  const item = data?.find((x) => x.episode.id === sel) || data?.[0];
  return (
    <div className="stack">
      <PageHead title="Publication" sub="Packs prêts à publier depuis votre téléphone. Aucune publication automatique." />
      {data && !data.length && <Empty>Aucun épisode prêt. Un pack est créé après la validation du rendu final.</Empty>}
      {data && data.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: "minmax(220px, 280px) minmax(0, 1fr)" }}>
          <div className="panel">
            {data.map((x) => (
              <div key={x.episode.id} className={`list-item clickable ${item?.episode.id === x.episode.id ? "selected" : ""}`} onClick={() => setSel(x.episode.id)}>
                <div className="row between"><SeriesPill id={x.episode.series_id} /><Status s={x.episode.status} /></div>
                <div className="small" style={{ marginTop: 4 }}>Ép. {x.episode.number} — {x.episode.title}</div>
              </div>
            ))}
          </div>
          <div className="panel">{item && <PackView key={item.episode.id} item={item} reload={reload} />}</div>
        </div>
      )}
    </div>
  );
}
