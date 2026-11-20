import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, SERIES_COLORS } from "../api";
import { Empty, PageHead, Status, useAction, usePoll } from "../ui";
import { EpisodeList, GateBar, JobsPanel, useSelectedEpisode } from "./common";

function ScriptView({ script, accent, canEdit, onRegen }: { script: any; accent: string; canEdit: boolean; onRegen: (i: number) => void }) {
  return (
    <div style={{ ["--accent" as any]: accent }}>
      <h3>{script.title}</h3>
      <p className="small"><b>Logline :</b> {script.logline}</p>
      <p className="small"><b>Accroche :</b> {script.hook}</p>
      {script.scenes.map((sc: any, i: number) => (
        <div key={sc.id} className="scene">
          <div className="row between">
            <b>Scène {i + 1} · {sc.location}</b>
            <span className="row">
              <span className="pill gray">♪ {sc.music}</span>
              {canEdit && <button className="sm amber" onClick={() => onRegen(i)}>↻ Réécrire cette scène seulement</button>}
            </span>
          </div>
          <p className="small muted">{sc.summary} {sc.mood && `· ${sc.mood}`}</p>
          {sc.shots.map((sh: any) => (
            <div key={sh.id} className="shot">
              <div className="meta">{sh.id}<br />{sh.kind}<br />{sh.duration}s · {sh.camera}</div>
              <div>
                {sh.caption && <div className="caption-chip">[{sh.caption}]</div>}
                {sh.text && <div><span className="speaker">{sh.speaker}</span> — {sh.text}</div>}
                {sh.narration && <div className="muted"><i>Voix off : {sh.narration}</i></div>}
                <div className="tiny muted">
                  {sh.characters.map((c: any) => `${c.id} (${c.expression}, ${c.facing}, ${c.position})`).join(" · ")}
                  {sh.sfx.length > 0 && ` · sfx : ${sh.sfx.join(", ")}`}
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}
      <div className="panel flat" style={{ marginTop: 10 }}>
        <b>Fin : {script.ending.type}</b>
        {script.ending.type === "vote" && (
          <div className="small">🗳️ {script.ending.vote_question} → {script.ending.vote_options.join(" / ")}</div>
        )}
        {script.canon_proposals.length > 0 && (
          <div className="small" style={{ marginTop: 6 }}>
            Propositions de canon (non canon tant que non validées) :
            <ul>{script.canon_proposals.map((p: any, i: number) => <li key={i}>[{p.category}] {p.text}</li>)}</ul>
          </div>
        )}
        {script.new_characters.length > 0 && (
          <div className="small">Nouveaux personnages proposés : {script.new_characters.map((c: any) => c.name).join(", ")}</div>
        )}
      </div>
    </div>
  );
}

function Critique({ c }: { c: any }) {
  const s = c.content;
  return (
    <div>
      <p className="small">{s.summary}</p>
      <p className="tiny muted">Source : {s.source}</p>
      {Object.entries(s.scores || {}).map(([k, v]: any) => (
        <div key={k} className="score">
          <span className="muted">{k}</span>
          <div className="progress"><span style={{ width: `${v}%` }} /></div>
          <span>{v}</span>
        </div>
      ))}
      <hr />
      {(s.issues || []).length === 0 && <p className="small muted">Aucun problème relevé.</p>}
      {(s.issues || []).map((i: any, k: number) => (
        <div key={k} className={`issue ${i.severity}`}>
          <div className="row between tiny">
            <span className="pill gray">{i.type}</span>
            <span className="muted">{i.scene} {i.shot} · {i.severity}</span>
          </div>
          <div>{i.message}</div>
          <div className="small muted">→ {i.suggestion}</div>
        </div>
      ))}
    </div>
  );
}

export default function Scripts() {
  const [sel, setSel] = useSelectedEpisode();
  const { data: d, reload } = usePoll<any>(sel ? `/api/episodes/${sel}` : null, 2500);
  const [ver, setVer] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [json, setJson] = useState("");
  const { run } = useAction();
  useEffect(() => { setVer(null); setEditing(false); }, [sel]);

  const script = d?.scripts.find((s: any) => s.id === ver) || d?.scripts[0];
  const crit = d?.critiques.find((c: any) => c.script_version_id === script?.id);
  const pendingScript = d?.gates.some((g: any) => g.status === "pending" && g.stage === "script");
  const busy = d?.jobs.some((j: any) => ["queued", "running"].includes(j.status));
  const regen = (i: number) => {
    const note = prompt(`Note pour réécrire la scène ${i + 1} (les autres scènes ne changent pas) :`, "Plus de tension");
    if (note !== null) run(() => api.post(`/api/episodes/${sel}/scenes/${i}/regenerate`, { note }), "Réécriture de la scène lancée").then(reload);
  };

  return (
    <div className="stack">
      <PageHead title="Scénarios" sub="Propositions, scripts, critiques, versions et validations." />
      <div className="grid" style={{ gridTemplateColumns: "minmax(240px, 300px) 1fr" }}>
        <EpisodeList selected={sel} onSelect={setSel} />
        <div className="stack" style={{ minWidth: 0 }}>
          {!d ? (
            <Empty>Sélectionnez un épisode.</Empty>
          ) : (
            <>
              <div className="panel" style={{ ["--accent" as any]: SERIES_COLORS[d.episode.series_id] }}>
                <div className="row between">
                  <h3>Ép. {d.episode.number} — {d.episode.title || "écriture en cours"}</h3>
                  <Status s={d.episode.status} />
                </div>
                <p className="small muted">Intention : {d.episode.intent} · {d.episode.duration_s}s · étape : {d.episode.stage_label}</p>
                <JobsPanel detail={d} reload={reload} />
              </div>
              {d.gates.some((g: any) => g.status === "pending" && g.stage === "episode") && (
                <div className="panel" style={{ ["--accent" as any]: "var(--amber)" }}>
                  <div className="row between"><b style={{ color: "var(--amber)" }}>Épisode prêt : validation unique en attente.</b>
                    <Link to="/validations"><button className="primary">Voir et valider →</button></Link></div>
                </div>
              )}
              <GateBar detail={d} stage="script" reload={reload}
                extra={<button className="ghost" onClick={() => { setJson(JSON.stringify(script.content, null, 2)); setEditing(true); }}>✎ Éditer à la main</button>} />
              {script ? (
                <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 1fr)" }}>
                  <div className="panel">
                    <div className="row between">
                      <h2>Script v{script.version}</h2>
                      <select style={{ width: "auto" }} value={script.id} onChange={(e) => setVer(+e.target.value)}>
                        {d.scripts.map((s: any) => (
                          <option key={s.id} value={s.id}>v{s.version} · {s.origin} · {fmtDate(s.created_at)}</option>
                        ))}
                      </select>
                    </div>
                    {script.note && <p className="tiny muted">{script.note}</p>}
                    {editing ? (
                      <div>
                        <p className="small muted">Modifiez le JSON du script. Une nouvelle version sera créée et repassera par la critique et votre validation.</p>
                        <textarea className="mono" rows={24} value={json} onChange={(e) => setJson(e.target.value)} />
                        <div className="row" style={{ marginTop: 8 }}>
                          <button className="primary" onClick={() => {
                            let content;
                            try { content = JSON.parse(json); } catch (e: any) { alert("JSON invalide : " + e.message); return; }
                            run(() => api.put(`/api/episodes/${sel}/script`, { content, note: "édition manuelle" }), "Nouvelle version enregistrée")
                              .then((r) => { if (r) setEditing(false); reload(); });
                          }}>Enregistrer la version</button>
                          <button className="ghost" onClick={() => setEditing(false)}>Annuler</button>
                        </div>
                      </div>
                    ) : (
                      <ScriptView script={script.content} accent={SERIES_COLORS[d.episode.series_id]}
                        canEdit={(!!pendingScript || d.gates.some((g: any) => g.status === "pending" && g.stage === "episode")) && !busy && script.id === d.scripts[0].id} onRegen={regen} />
                    )}
                  </div>
                  <div className="panel">
                    <h2>Critique du directeur</h2>
                    {crit ? <Critique c={crit} /> : <p className="small muted">Critique en attente…</p>}
                  </div>
                </div>
              ) : (
                <Empty>L'agent écrit le scénario…</Empty>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
