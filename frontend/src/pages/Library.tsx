import { useState } from "react";
import { api, fileUrl, fmtBytes, fmtDate } from "../api";
import { Empty, PageHead, useAction, usePoll } from "../ui";

const KINDS = ["character", "expression", "pose", "rig", "animation", "background", "palette", "effect", "subtitle_template",
  "voice", "music", "sfx", "code", "source", "export"];
const LABEL: Record<string, string> = {
  character: "Sprites personnages", expression: "Visages / expressions", pose: "Poses", rig: "Riggings", animation: "Animations",
  background: "Décors", palette: "Palettes", effect: "Effets", subtitle_template: "Modèles de sous-titres", voice: "Voix",
  music: "Musiques", sfx: "Sons", code: "Code", source: "Projets sources", export: "Exports",
};

function Preview({ a }: { a: any }) {
  const url = fileUrl(a.path);
  if (/\.(png|jpe?g|webp|svg)$/i.test(a.path)) return <img src={url} alt={a.name} loading="lazy" />;
  if (/\.(wav|mp3|ogg)$/i.test(a.path)) return <audio controls src={url} style={{ width: "100%" }} preload="none" />;
  if (/\.mp4$/i.test(a.path)) return <video src={url} controls preload="metadata" />;
  return <a href={url} target="_blank" rel="noreferrer" className="small">Ouvrir le fichier</a>;
}

export default function Library() {
  const [kind, setKind] = useState("");
  const { data, reload } = usePoll<any[]>(`/api/library${kind ? `?kind=${kind}` : ""}`, 6000);
  const { run, busy } = useAction();
  const [form, setForm] = useState({ asset_key: "", kind: "character", name: "", license: "", series_id: "" });
  const [file, setFile] = useState<File | null>(null);
  const [versions, setVersions] = useState<any[] | null>(null);

  const upload = () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));
    run(() => api.post("/api/library/upload", fd), "Élément ajouté (nouvelle version si la clé existait)").then(reload);
  };

  return (
    <div className="stack">
      <PageHead title="Bibliothèque" sub="Ressources réutilisables et versionnées, identifiants stables. Les éléments importés remplacent le rendu procédural.">
        <button disabled={busy} onClick={() => run(() => api.post("/api/library/generate"), "Régénération lancée (file d'attente)")}>↻ Régénérer les ressources procédurales</button>
      </PageHead>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 2fr) minmax(280px, 1fr)" }}>
        <div className="panel">
          <div className="row between">
            <h2>{kind ? LABEL[kind] : "Tous les éléments"} ({data?.length ?? "…"})</h2>
            <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ width: "auto" }}>
              <option value="">Tous les types</option>
              {KINDS.map((k) => <option key={k} value={k}>{LABEL[k]}</option>)}
            </select>
          </div>
          {data && !data.length && <Empty>Aucun élément de ce type. Importez-en un ou régénérez les ressources.</Empty>}
          <div className="thumbs" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))" }}>
            {data?.map((a) => (
              <div key={a.id} className="list-item" style={{ margin: 0 }}>
                <Preview a={a} />
                <div className="small" style={{ marginTop: 6 }}><b>{a.name}</b></div>
                <div className="tiny mono muted">{a.asset_key}</div>
                <div className="tiny muted">v{a.version} · {a.source} · {fmtBytes(a.meta.size || 0)}</div>
                <div className="tiny muted" title={a.license}>Droits : {a.license.slice(0, 60)}</div>
                {a.versions > 1 && <button className="sm ghost" onClick={() => api.get(`/api/library/${a.asset_key}/versions`).then(setVersions)}>{a.versions} versions</button>}
              </div>
            ))}
          </div>
        </div>
        <div className="stack">
          <div className="panel">
            <h2>Importer un élément</h2>
            <p className="tiny muted">Pour remplacer un personnage : clé <code>char.&lt;id&gt;.&lt;expression&gt;</code> (PNG transparent, ex. <code>char.hor.lea.scared</code>). Pour un décor : <code>bg.&lt;lieu&gt;</code> (ex. <code>bg.corridor</code>).</p>
            <div className="field"><label>Fichier</label><input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} /></div>
            <div className="field"><label>Clé stable</label><input className="mono" value={form.asset_key} onChange={(e) => setForm({ ...form, asset_key: e.target.value.toLowerCase() })} placeholder="char.hor.lea.scared" /></div>
            <div className="field"><label>Type</label><select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{KINDS.map((k) => <option key={k} value={k}>{LABEL[k]}</option>)}</select></div>
            <div className="field"><label>Nom</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div className="field"><label>Licence / droits (obligatoire)</label><input value={form.license} onChange={(e) => setForm({ ...form, license: e.target.value })} placeholder="Création personnelle, CC0, licence achetée…" /></div>
            <div className="field"><label>Série (facultatif)</label><select value={form.series_id} onChange={(e) => setForm({ ...form, series_id: e.target.value })}><option value="">Partagé</option><option value="horror">Horreur</option><option value="football">Football</option><option value="isekai">Isekai</option></select></div>
            <button className="primary" disabled={busy || !file || !form.asset_key || !form.name || !form.license} onClick={upload}>Importer</button>
          </div>
          {versions && (
            <div className="panel">
              <div className="row between"><h2>Historique des versions</h2><button className="sm ghost" onClick={() => setVersions(null)}>Fermer</button></div>
              {versions.map((v) => <div key={v.id} className="small">v{v.version} · {v.source} · {fmtDate(v.created_at)} · <a href={fileUrl(v.path)} target="_blank" rel="noreferrer">fichier</a></div>)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
