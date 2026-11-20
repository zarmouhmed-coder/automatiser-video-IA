import { useState } from "react";
import { api, fileUrl, fmtDate, SERIES_COLORS } from "../api";
import { PageHead, Status, useAction, usePoll } from "../ui";

export default function Bible() {
  const [sid, setSid] = useState("horror");
  const { data: b, reload } = usePoll<any>(`/api/series/${sid}/bible`, 0);
  const { data: agents } = usePoll<any[]>("/api/agents", 0);
  const { data: voices } = usePoll<any>("/api/voices", 0);
  const { data: sheets } = usePoll<any[]>(`/api/library?kind=expression&series_id=${sid}`, 0);
  const [fact, setFact] = useState("");
  const [tab, setTab] = useState("monde");
  const { run } = useAction();
  const accent = SERIES_COLORS[sid];
  const agent = agents?.find((a) => a.series_id === sid);

  const importFile = (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    run(() => api.post(`/api/series/${sid}/import-file`, fd)).then((r: any) => {
      if (r) alert(`Import terminé.\nAjoutés : ${r.added.length}\nDéjà présents (conservés, non écrasés) : ${r.skipped_existing.length}\n${r.errors.join("\n")}`);
      reload();
    });
  };

  return (
    <div className="stack">
      <PageHead title="Bibles des séries" sub="Personnages, relations, faits canoniques, chronologie, ton et direction artistique — persistants et indépendants.">
        {["horror", "football", "isekai"].map((s) => (
          <button key={s} className={sid === s ? "primary" : ""} style={sid === s ? { background: SERIES_COLORS[s], borderColor: SERIES_COLORS[s] } : {}} onClick={() => setSid(s)}>
            {{ horror: "A · Horreur", football: "B · Football", isekai: "C · Isekai" }[s]}
          </button>
        ))}
      </PageHead>
      {b && (
        <>
          <div className="panel" style={{ ["--accent" as any]: accent }}>
            <div className="row between"><h3>{b.name}</h3><span className="small muted">{b.genre}</span></div>
            <p>{b.bible.pitch}</p>
            {b.lock.locked && <div className="lock">🔒 {b.lock.reason}</div>}
          </div>
          <div className="tabs">
            {[["monde", "Monde & ton"], ["persos", `Personnages (${b.characters.length})`], ["canon", `Canon (${b.facts.length})`], ["codex", `Codex (${b.entries.length})`], ["chrono", "Chronologie & choix"], ["agent", "Agent scénariste"], ["import", "Import"]].map(([k, l]) => (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
          {tab === "monde" && (
            <div className="grid g2">
              <div className="panel"><h2>Ton</h2><p className="small">{b.bible.tone}</p><h2>Règles du monde</h2>
                <ul className="small">{b.bible.rules.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
                <h2>Politique de vote</h2><p className="small">{b.bible.vote_policy}</p></div>
              <div className="panel"><h2>Direction artistique</h2>
                <div className="row">{b.bible.art_direction.palette.map((c: string) => <span key={c} title={c} style={{ width: 34, height: 34, borderRadius: 8, background: c, border: "1px solid #fff2" }} />)}</div>
                <p className="small" style={{ marginTop: 10 }}><b>Lumière :</b> {b.bible.art_direction.lighting}</p>
                <p className="small"><b>Caméra :</b> {b.bible.art_direction.camera}</p>
                <p className="small"><b>Son :</b> {b.bible.sound_direction}</p></div>
            </div>
          )}
          {tab === "persos" && (
            <div className="grid g2">
              {b.characters.map((c: any) => {
                const sheet = sheets?.find((s) => s.asset_key === `char.${c.id}.sheet`);
                return (
                  <div key={c.id} className="panel" style={{ ["--accent" as any]: accent }}>
                    <div className="row between"><h3>{c.name}</h3><span className="row"><Status s={c.status} /><code className="tiny">{c.id}</code></span></div>
                    <p className="small muted">{c.role} · v{c.version}</p>
                    <p className="small">{c.description}</p>
                    <p className="small muted">{c.personality}</p>
                    {Object.keys(c.stats || {}).length > 0 && <p className="tiny mono">{JSON.stringify(c.stats)}</p>}
                    {b.relations.filter((r: any) => r.a_id === c.id || r.b_id === c.id).map((r: any) => <div key={r.id} className="tiny muted">↔ {r.a_id === c.id ? r.b_id : r.a_id} : {r.kind}</div>)}
                    <div className="row" style={{ marginTop: 8 }}>
                      <span className="tiny muted">Voix :</span>
                      <select style={{ width: "auto" }} value={c.voice?.gender || "M"} onChange={(e) => run(() => api.patch(`/api/characters/${c.id}`, { voice: { ...c.voice, gender: e.target.value } }), "Voix mise à jour (prochains rendus)").then(reload)}>
                        <option value="F">féminine</option><option value="M">masculine</option>
                      </select>
                      <span className="tiny muted">hauteur</span>
                      <select style={{ width: "auto" }} value={String(c.voice?.pitch ?? 1)} onChange={(e) => run(() => api.patch(`/api/characters/${c.id}`, { voice: { ...c.voice, pitch: +e.target.value } }), "Voix mise à jour").then(reload)}>
                        {[0.7, 0.8, 0.85, 0.9, 0.95, 1, 1.05, 1.1, 1.15, 1.2].map((x) => <option key={x} value={String(x)}>{x}</option>)}
                      </select>
                      {voices?.cast?.[sid]?.find((v: any) => v.id === c.id) && <span className="tiny mono muted">{voices.cast[sid].find((v: any) => v.id === c.id).fr}</span>}
                    </div>
                    {sheet && <img src={fileUrl(sheet.path)} alt={`Expressions de ${c.name}`} style={{ width: "100%", borderRadius: 8, marginTop: 8 }} loading="lazy" />}
                    {c.status === "proposed" && <div className="row" style={{ marginTop: 8 }}>
                      <button className="sm primary" onClick={() => run(() => api.patch(`/api/characters/${c.id}`, { status: "canon" }), "Ajouté au canon").then(reload)}>Rendre canon</button>
                      <button className="sm danger" onClick={() => run(() => api.patch(`/api/characters/${c.id}`, { status: "rejected" }), "Rejeté").then(reload)}>Rejeter</button></div>}
                  </div>
                );
              })}
            </div>
          )}
          {tab === "canon" && (
            <div className="panel">
              <div className="row"><input placeholder="Ajouter un fait canonique (vous seul pouvez le faire directement)" value={fact} onChange={(e) => setFact(e.target.value)} style={{ flex: 1 }} />
                <button disabled={!fact.trim()} onClick={() => run(() => api.post(`/api/series/${sid}/facts`, { text: fact }), "Fait ajouté au canon").then(() => { setFact(""); reload(); })}>Ajouter</button></div>
              <table style={{ marginTop: 10 }}><thead><tr><th>Fait</th><th>Catégorie</th><th>Source</th><th>Statut</th></tr></thead><tbody>
                {b.facts.map((f: any) => <tr key={f.id}><td className="small">{f.text}</td><td className="small">{f.category}</td><td className="small">{f.source}</td><td><Status s={f.status} /></td></tr>)}
              </tbody></table>
            </div>
          )}
          {tab === "codex" && (
            <div className="panel"><table><thead><tr><th>Type</th><th>Nom</th><th>Détails</th><th>Source</th></tr></thead><tbody>
              {b.entries.map((e: any) => <tr key={e.id}><td><span className="pill gray">{e.kind}</span></td><td className="small"><b>{e.name}</b><div className="tiny mono muted">{e.key}</div></td>
                <td className="tiny mono" style={{ maxWidth: 520, whiteSpace: "pre-wrap" }}>{e.kind === "document" ? String(e.data.text || "").slice(0, 400) : JSON.stringify(e.data, null, 1)}</td><td className="small">{e.source}</td></tr>)}
            </tbody></table></div>
          )}
          {tab === "chrono" && (
            <div className="grid g2">
              <div className="panel"><h2>Chronologie</h2>{!b.timeline.length && <p className="small muted">Ajoutée à chaque rendu final validé.</p>}
                {b.timeline.map((t: any) => <div key={t.id} className="list-item small"><b>{t.label}</b> — {t.text}</div>)}</div>
              <div className="panel"><h2>Historique des choix</h2>
                {b.choices.slice(0, 60).map((c: any) => <div key={c.id} className="small"><span className="muted">{fmtDate(c.created_at)}</span> · {c.summary}</div>)}</div>
            </div>
          )}
          {tab === "agent" && agent && (
            <div className="panel"><h2>{agent.name}</h2><p className="small">{agent.specialization}</p>
              <label>Consignes système</label><div className="copy-box small">{agent.system_prompt}</div>
              <p className="small" style={{ marginTop: 10 }}><b>Mémoire :</b> {agent.memory_policy}</p>
              <p className="small"><b>Règles de style :</b> {agent.style_rules.join(" · ")}</p>
              <h2 style={{ marginTop: 14 }}>Notes du directeur mémorisées</h2>
              {b.entries.filter((e: any) => e.kind === "agent_memory").map((e: any) => <div key={e.id} className="small">• {e.name}</div>)}
              <p className="tiny muted">Fichier de configuration : backend/app/agents/configs/{sid}.json</p></div>
          )}
          {tab === "import" && (
            <div className="panel">
              <h2>Importer une bible existante</h2>
              <p className="small">JSON (<code>characters</code>, <code>entries</code>, <code>facts</code>, <code>rules</code>) ou texte/Markdown (stocké comme document de référence). <b>Rien n'est jamais écrasé</b> : les éléments existants sont conservés et signalés. Un instantané de la bible est enregistré après chaque import.</p>
              <input type="file" accept=".json,.md,.txt" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
              <button style={{ marginTop: 12 }} onClick={() => run(() => api.post(`/api/series/${sid}/snapshot`), "Instantané JSON enregistré dans data/bibles")}>Enregistrer un instantané de la bible</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
