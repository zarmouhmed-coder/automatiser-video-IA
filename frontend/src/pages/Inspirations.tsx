import { useState } from "react";
import { api, fileUrl, fmtDate } from "../api";
import { Empty, PageHead, SeriesPill, useAction, usePoll } from "../ui";

export function Palette({ colors }: { colors?: string[] }) {
  return (
    <div className="row" style={{ gap: 4 }}>
      {(colors || []).map((c) => <span key={c} title={c} style={{ width: 22, height: 22, borderRadius: 6, background: c, border: "1px solid #fff3" }} />)}
    </div>
  );
}

export function InspirationCard({ i, onDelete }: { i: any; onDelete?: () => void }) {
  const p = i.profile || {};
  return (
    <div className="list-item">
      <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
        {i.thumbnail_path ? <img src={fileUrl(i.thumbnail_path)} alt="" style={{ width: 70, borderRadius: 8, flexShrink: 0 }} />
          : <div style={{ width: 70, height: 110, borderRadius: 8, background: "#000", flexShrink: 0 }} />}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="row between">
            <span className="small"><b>{i.title || i.url || "Référence"}</b> {i.author && <span className="muted">· @{i.author}</span>}</span>
            <span className="row">
              {i.series_id ? <SeriesPill id={i.series_id} /> : <span className="pill gray">toutes séries</span>}
              <span className={`pill ${i.status === "ready" ? "green" : i.status === "partial" ? "amber" : "red"}`}>
                {{ ready: "analyse complète", partial: "couleurs seulement", error: "erreur" }[i.status as string] || i.status}
              </span>
            </span>
          </div>
          {i.url && <a className="tiny" href={i.url} target="_blank" rel="noreferrer">{i.url}</a>}
          {p.embed_url && <a className="tiny" style={{ marginLeft: 8 }} href={p.embed_url} target="_blank" rel="noreferrer">▶ voir sur TikTok</a>}
          <Palette colors={p.palette} />
          <div className="tiny" style={{ marginTop: 4 }}>{p.description}</div>
          {p.note && <div className="tiny muted">{p.note}</div>}
          {i.error && <div className="lock tiny">{i.error}</div>}
          <div className="row tiny muted" style={{ marginTop: 4 }}>
            <span>{i.kind} · {fmtDate(i.created_at)}</span>
            {onDelete && <button className="sm ghost" onClick={onDelete}>Supprimer</button>}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Inspirations() {
  const { data, reload } = usePoll<any[]>("/api/inspirations", 0);
  const [url, setUrl] = useState("");
  const [series, setSeries] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const { run, busy } = useAction();
  return (
    <div className="stack">
      <PageHead title="Inspirations" sub="Donnez une référence (TikTok, vidéo, capture) : le studio en reprend le rythme, l'énergie et les couleurs — jamais le contenu." />
      <div className="grid g2">
        <div className="panel">
          <h2>Lien TikTok</h2>
          <div className="field"><input placeholder="https://www.tiktok.com/@compte/video/…" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
          <div className="field"><label>Série</label>
            <select value={series} onChange={(e) => setSeries(e.target.value)}><option value="">Toutes</option><option value="horror">Horreur</option><option value="football">Football</option><option value="isekai">Isekai</option></select></div>
          <button className="primary" disabled={busy || !url.trim()} onClick={() => run(() => api.post("/api/inspirations/link", { url, series_id: series || null }), "Lien analysé").then(() => { setUrl(""); reload(); })}>Analyser le lien</button>
          <p className="tiny muted" style={{ marginTop: 8 }}>Le lien donne le titre, l'auteur et les couleurs de la miniature (API officielle de TikTok). TikTok n'autorise pas le téléchargement de ses vidéos : pour copier le <b>rythme de montage</b> et le <b>mouvement</b>, importez aussi la vidéo ci-contre.</p>
        </div>
        <div className="panel">
          <h2>Vidéo ou capture d'écran</h2>
          <div className="field"><input type="file" accept="video/*,image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} /></div>
          <button className="primary" disabled={busy || !file} onClick={() => {
            const fd = new FormData();
            fd.append("file", file!);
            fd.append("series_id", series);
            fd.append("url", url);
            run(() => api.post("/api/inspirations/upload", fd), "Référence analysée").then(() => { setFile(null); reload(); });
          }}>Analyser le fichier</button>
          <p className="tiny muted" style={{ marginTop: 8 }}>Mesuré : nombre de plans, durée moyenne d'un plan, coupes/minute, intensité du mouvement, luminosité, contraste, saturation et palette. Appliqué ensuite : durée des plans, énergie de la caméra, étalonnage et couleur d'accent des titres.</p>
        </div>
      </div>
      <div className="panel">
        <h2>Références enregistrées</h2>
        {data && !data.length && <Empty>Aucune inspiration. Ajoutez un lien ou une vidéo.</Empty>}
        {data?.map((i) => <InspirationCard key={i.id} i={i} onDelete={() => run(() => api.del(`/api/inspirations/${i.id}`), "Supprimée").then(reload)} />)}
      </div>
    </div>
  );
}
