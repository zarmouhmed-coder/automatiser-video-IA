import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, fmtDate } from "../api";
import { Empty, PageHead, SeriesPill, Status, useAction, usePoll } from "../ui";

function VoteCard({ v, reload }: { v: any; reload: () => void }) {
  const [platform, setPlatform] = useState(v.platform || "TikTok");
  const [at, setAt] = useState(v.result_at || new Date().toISOString().slice(0, 16));
  const [winner, setWinner] = useState(v.winner || "");
  const [counts, setCounts] = useState<Record<string, number>>(v.counts || {});
  const { run, busy } = useAction();
  return (
    <div className="list-item">
      <div className="row between">
        <span className="row"><SeriesPill id={v.series_id} /> <b>Ép. {v.episode_number}</b> — {v.question}</span>
        <Status s={v.status} />
      </div>
      {v.status === "validated" ? (
        <p className="small" style={{ marginTop: 6 }}>✓ Décision officielle : <b>{v.winner}</b> ({v.platform}, {v.result_at}) — validé le {fmtDate(v.validated_at)}. Définitif et historisé.</p>
      ) : (
        <div style={{ marginTop: 10 }}>
          <div className="grid g3">
            <div className="field"><label>Plateforme de référence</label><input value={platform} onChange={(e) => setPlatform(e.target.value)} /></div>
            <div className="field"><label>Date/heure du résultat</label><input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></div>
            <div className="field"><label>Décision gagnante</label>
              <select value={winner} onChange={(e) => setWinner(e.target.value)}>
                <option value="">— choisir —</option>
                {v.options.map((o: string) => <option key={o}>{o}</option>)}
              </select></div>
          </div>
          <div className="row">
            {v.options.map((o: string) => (
              <div key={o} style={{ width: 160 }}><label>Voix « {o} » (facultatif)</label>
                <input type="number" min={0} value={counts[o] ?? ""} onChange={(e) => setCounts({ ...counts, [o]: +e.target.value })} /></div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <button disabled={busy || !winner} onClick={() => run(() => api.post(`/api/votes/${v.id}/result`, { platform, result_at: at, winner, counts }), "Résultat enregistré : validez-le pour débloquer la suite").then(reload)}>
              1. Enregistrer le résultat
            </button>
            <button className="primary" disabled={busy || v.status !== "result_entered"} onClick={() =>
              confirm(`Valider officiellement « ${v.winner} » ? Cette décision sera définitive.`) &&
              run(() => api.post(`/api/votes/${v.id}/validate`), "Résultat validé : la série est débloquée").then(reload)}>
              2. Valider le résultat officiel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Observers() {
  const { data, reload } = usePoll<any[]>("/api/observers", 4000);
  const { run, busy } = useAction();
  const [form, setForm] = useState({ pseudo: "", pseudo_kind: "fictif", kind: "capacite", content: "", target_character: "" });
  const [bulk, setBulk] = useState("");
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(280px, 1fr) minmax(0, 1.6fr)" }}>
      <div className="stack">
        <div className="panel" style={{ ["--accent" as any]: "#b48cff" }}>
          <h2>Nouvelle proposition</h2>
          <p className="tiny muted">Réservé à « L'Archive d'Aldhra ». Saisie manuelle uniquement ; pseudo fictif ou consenti.</p>
          <div className="field"><label>Pseudo</label><input value={form.pseudo} onChange={(e) => setForm({ ...form, pseudo: e.target.value })} /></div>
          <div className="grid g2">
            <div className="field"><label>Nature du pseudo</label><select value={form.pseudo_kind} onChange={(e) => setForm({ ...form, pseudo_kind: e.target.value })}><option value="fictif">fictif</option><option value="consenti">consenti</option></select></div>
            <div className="field"><label>Type</label><select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}><option value="capacite">capacité</option><option value="cadeau">cadeau</option><option value="commentaire">commentaire</option></select></div>
          </div>
          <div className="field"><label>Proposition</label><textarea rows={3} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} /></div>
          <div className="field"><label>Personnage ciblé (id, facultatif)</label><input placeholder="isk.elio" value={form.target_character} onChange={(e) => setForm({ ...form, target_character: e.target.value })} /></div>
          <button className="primary" disabled={busy} onClick={() => run(() => api.post("/api/observers", form), "Proposition ajoutée").then((r) => { if (r) setForm({ ...form, content: "" }); reload(); })}>Ajouter</button>
        </div>
        <div className="panel">
          <h2>Import en lot</h2>
          <p className="tiny muted">Une ligne par proposition : <code>pseudo | capacite|cadeau|commentaire | contenu</code></p>
          <textarea rows={4} value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder="Veilleur_42 | cadeau | Une boussole qui pointe vers le mana" />
          <button disabled={busy || !bulk.trim()} onClick={() => run(() => api.post("/api/observers/import", { text: bulk }), "Import terminé").then((r: any) => { if (r?.errors?.length) alert(r.errors.join("\n")); setBulk(""); reload(); })}>Importer</button>
        </div>
      </div>
      <div className="panel">
        <h2>Propositions</h2>
        {!data?.length && <Empty>Aucune proposition.</Empty>}
        {data?.map((o) => (
          <div key={o.id} className="list-item">
            <div className="row between"><span><b>{o.pseudo}</b> <span className="pill gray">{o.pseudo_kind}</span> <span className="pill gray">{o.kind}</span></span><Status s={o.status} /></div>
            <p className="small" style={{ margin: "6px 0" }}>{o.content} {o.target_character && <span className="muted">→ {o.target_character}</span>}</p>
            {o.analysis?.verdict && (
              <div className={`issue ${o.analysis.verdict === "incompatible" ? "forte" : o.analysis.verdict === "a_adapter" ? "moyenne" : ""}`}>
                <b>Analyse de l'agent : {o.analysis.verdict}</b> <span className="tiny muted">({o.analysis.source})</span>
                <ul className="small" style={{ margin: "4px 0", paddingLeft: 18 }}>{(o.analysis.reasons || []).map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
                {o.analysis.adaptation && <div className="small">Adaptation proposée : <i>{o.analysis.adaptation}</i></div>}
              </div>
            )}
            {o.final_text && <p className="small">✓ Canon : {o.final_text}</p>}
            {["pending", "analyzed"].includes(o.status) && (
              <div className="row">
                <button className="sm" disabled={busy} onClick={() => run(() => api.post(`/api/observers/${o.id}/analyze`), "Analyse terminée").then(reload)}>Analyser la compatibilité</button>
                {o.status === "analyzed" && (
                  <>
                    <button className="sm primary" disabled={o.analysis.verdict === "incompatible"} onClick={() => run(() => api.post(`/api/observers/${o.id}/decide`, { action: "accept" }), "Accepté : ajouté au canon").then(reload)}>Accepter</button>
                    <button className="sm amber" onClick={() => {
                      const t = prompt("Texte adapté (deviendra canon) :", o.analysis.adaptation || o.content);
                      if (t) run(() => api.post(`/api/observers/${o.id}/decide`, { action: "adapt", final_text: t }), "Version adaptée ajoutée au canon").then(reload);
                    }}>Adapter</button>
                    <button className="sm danger" onClick={() => run(() => api.post(`/api/observers/${o.id}/decide`, { action: "reject" }), "Rejeté").then(reload)}>Rejeter</button>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Comments() {
  const [series, setSeries] = useState("horror");
  const { data, reload } = usePoll<any[]>(`/api/comments?series_id=${series}`, 5000);
  const [text, setText] = useState("");
  const [author, setAuthor] = useState("");
  const [platform, setPlatform] = useState("TikTok");
  const { run } = useAction();
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(280px, 1fr) minmax(0, 1.6fr)" }}>
      <div className="panel">
        <h2>Saisir un commentaire</h2>
        <div className="field"><label>Série</label><select value={series} onChange={(e) => setSeries(e.target.value)}><option value="horror">A · Horreur</option><option value="football">B · Football</option><option value="isekai">C · Isekai</option></select></div>
        <div className="grid g2">
          <div className="field"><label>Auteur (facultatif)</label><input value={author} onChange={(e) => setAuthor(e.target.value)} /></div>
          <div className="field"><label>Plateforme</label><input value={platform} onChange={(e) => setPlatform(e.target.value)} /></div>
        </div>
        <div className="field"><label>Commentaire</label><textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} /></div>
        <button className="primary" disabled={!text.trim()} onClick={() => run(() => api.post("/api/comments", { series_id: series, text, author, platform }), "Commentaire enregistré").then(() => { setText(""); reload(); })}>Enregistrer</button>
        <p className="tiny muted" style={{ marginTop: 8 }}>Aucune collecte automatique. Cochez « inspiration » pour qu'un commentaire soit transmis à l'agent scénariste (comme simple idée, jamais comme canon).</p>
      </div>
      <div className="panel">
        <h2>Commentaires saisis</h2>
        {!data?.length && <Empty>Aucun commentaire pour cette série.</Empty>}
        {data?.map((c) => (
          <div key={c.id} className="list-item">
            <div className="row between tiny muted"><span>{c.author || "anonyme"} · {c.platform} · {fmtDate(c.created_at)}</span>
              <span className="row">
                <label className="row" style={{ margin: 0 }}><input type="checkbox" checked={!!c.use_as_inspiration} onChange={(e) => api.patch(`/api/comments/${c.id}`, { use_as_inspiration: e.target.checked }).then(reload)} /> inspiration</label>
                <button className="sm ghost" onClick={() => api.del(`/api/comments/${c.id}`).then(reload)}>Supprimer</button>
              </span></div>
            <div className="small">{c.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Community() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "votes";
  const { data: votes, reload } = usePoll<any[]>("/api/votes", 4000);
  const { data: choices } = usePoll<any[]>("/api/choices", 8000);
  return (
    <div className="stack">
      <PageHead title="Communauté" sub="Votes, commentaires saisis à la main et Observateurs/sponsors (isekai). Vous gardez la main sur tout." />
      <div className="tabs">
        {[["votes", "Votes"], ["comments", "Commentaires"], ["observers", "Observateurs · Isekai"], ["history", "Historique des choix"]].map(([k, l]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setParams({ tab: k })}>{l}</button>
        ))}
      </div>
      {tab === "votes" && (
        <div className="panel">
          <h2>Votes</h2>
          <p className="small muted">Un vote s'ouvre quand vous marquez comme publié un épisode qui se termine sur un vote. L'épisode suivant de la série reste bloqué jusqu'à la validation du résultat officiel.</p>
          {!votes?.length ? <Empty>Aucun vote pour l'instant.</Empty> : votes.map((v) => <VoteCard key={v.id + v.status} v={v} reload={reload} />)}
        </div>
      )}
      {tab === "comments" && <Comments />}
      {tab === "observers" && <Observers />}
      {tab === "history" && (
        <div className="panel">
          <h2>Tous les choix (historisés)</h2>
          <table><thead><tr><th>Date</th><th>Série</th><th>Type</th><th>Décision</th></tr></thead><tbody>
            {choices?.map((c) => <tr key={c.id}><td className="small">{fmtDate(c.created_at)}</td><td><SeriesPill id={c.series_id} /></td><td><span className="pill gray">{c.kind}</span></td><td className="small">{c.summary}</td></tr>)}
          </tbody></table>
        </div>
      )}
    </div>
  );
}
