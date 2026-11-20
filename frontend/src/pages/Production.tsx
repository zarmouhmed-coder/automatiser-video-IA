import { useEffect, useState } from "react";
import { api, fileUrl, fmtBytes, fmtDate, SERIES_COLORS } from "../api";
import { Empty, PageHead, Status, useAction, usePoll } from "../ui";
import { EpisodeList, GateBar, JobsPanel, useSelectedEpisode } from "./common";

const CAMERAS = ["static", "push_in", "pull_out", "pan_left", "pan_right", "shake", "tilt_up"];
const EXPRESSIONS = ["neutral", "happy", "sad", "angry", "scared", "surprised", "determined", "smirk"];

function ShotEditor({ ep, shot, editable, onDone }: { ep: number; shot: any; editable: boolean; onDone: () => void }) {
  const [camera, setCamera] = useState(shot.camera);
  const [duration, setDuration] = useState(shot.duration);
  const [caption, setCaption] = useState(shot.caption);
  const [chars, setChars] = useState<any[]>(shot.characters);
  const { run, busy } = useAction();
  useEffect(() => { setCamera(shot.camera); setDuration(shot.duration); setCaption(shot.caption); setChars(shot.characters); }, [shot]);
  return (
    <div className="panel">
      <h2>Plan {shot.shot_id}</h2>
      {shot.thumb && <img src={fileUrl(shot.thumb)} alt="" style={{ width: 160, borderRadius: 8, float: "right", marginLeft: 12 }} />}
      <p className="small">{shot.kind} · {shot.location} · début {shot.start}s</p>
      {shot.text && <p className="small"><b>{shot.speaker_name}</b> : {shot.text}</p>}
      <div className="field"><label>Caméra</label>
        <select disabled={!editable} value={camera} onChange={(e) => setCamera(e.target.value)}>{CAMERAS.map((c) => <option key={c}>{c}</option>)}</select></div>
      <div className="field"><label>Durée (s)</label>
        <input disabled={!editable} type="number" step={0.1} min={1} max={12} value={duration} onChange={(e) => setDuration(+e.target.value)} /></div>
      <div className="field"><label>Texte à l'écran</label>
        <input disabled={!editable} value={caption} onChange={(e) => setCaption(e.target.value)} /></div>
      {chars.map((c, i) => (
        <div key={i} className="field"><label>{c.id} — expression</label>
          <select disabled={!editable} value={c.expression} onChange={(e) => setChars(chars.map((x, k) => k === i ? { ...x, expression: e.target.value } : x))}>
            {EXPRESSIONS.map((x) => <option key={x}>{x}</option>)}
          </select></div>
      ))}
      <button className="primary" disabled={!editable || busy} onClick={() =>
        run(() => api.patch(`/api/episodes/${ep}/storyboard/shots/${shot.shot_id}`, { camera, duration, caption, characters: chars }),
          "Plan modifié : nouvelle version du storyboard (seul ce plan change)").then(onDone)}>
        Appliquer à ce plan uniquement
      </button>
      {!editable && <p className="tiny muted">Modifiable pendant la validation du storyboard ou après le rendu (aucune tâche en cours).</p>}
    </div>
  );
}

export default function Production() {
  const [sel, setSel] = useSelectedEpisode();
  const { data: d, reload } = usePoll<any>(sel ? `/api/episodes/${sel}` : null, 2500);
  const [tab, setTab] = useState("storyboard");
  const [shotId, setShotId] = useState<string | null>(null);
  useEffect(() => setShotId(null), [sel]);
  const sb = d?.storyboards[0];
  const shot = sb?.content.shots.find((s: any) => s.shot_id === shotId);
  const busy = d?.jobs.some((j: any) => ["queued", "running"].includes(j.status));
  const scriptApproved = d?.gates.some((g: any) => g.stage === "script" && g.status === "approved");
  const preview = d?.renders.find((r: any) => r.kind === "preview");
  const final = d?.renders.find((r: any) => r.kind === "final");

  return (
    <div className="stack">
      <PageHead title="Production" sub="Storyboard, plans, voix, rendu, journaux et lecteur de prévisualisation." />
      <div className="grid" style={{ gridTemplateColumns: "minmax(240px, 300px) 1fr" }}>
        <EpisodeList selected={sel} onSelect={setSel} />
        <div className="stack" style={{ minWidth: 0 }}>
          {!d ? <Empty>Sélectionnez un épisode.</Empty> : (
            <>
              <div className="panel" style={{ ["--accent" as any]: SERIES_COLORS[d.episode.series_id] }}>
                <div className="row between">
                  <h3>Ép. {d.episode.number} — {d.episode.title}</h3>
                  <Status s={d.episode.status} />
                </div>
                <p className="small muted">Étape : {d.episode.stage_label}</p>
                <JobsPanel detail={d} reload={reload} />
              </div>
              <GateBar detail={d} stage="storyboard" reload={reload} />
              <GateBar detail={d} stage="preview" reload={reload} />
              <GateBar detail={d} stage="final" reload={reload} />
              <div className="tabs">
                {[["storyboard", "Storyboard"], ["video", "Lecteur"], ["assets", "Voix & assets"], ["logs", "Journal"]].map(([k, l]) => (
                  <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
                ))}
              </div>
              {tab === "storyboard" && (!sb ? <Empty>{scriptApproved ? "Storyboard en préparation…" : "Le storyboard démarre après la validation du scénario."}</Empty> : (
                <div className="grid" style={{ gridTemplateColumns: shot ? "minmax(0,1.5fr) minmax(260px,1fr)" : "1fr" }}>
                  <div className="panel">
                    <div className="row between"><h2>Storyboard v{sb.version}</h2><span className="small muted">{sb.content.shots.length} plans · {sb.content.total}s</span></div>
                    <div className="board">
                      {sb.content.shots.map((s: any) => (
                        <div key={s.shot_id} className={`frame clickable ${s.shot_id === shotId ? "selected" : ""}`} onClick={() => setShotId(s.shot_id)}>
                          {s.thumb ? <img src={fileUrl(s.thumb)} alt={s.shot_id} loading="lazy" /> : <div style={{ aspectRatio: "9/16" }} />}
                          <div className="cap"><b>{s.shot_id}</b> · {s.duration}s · {s.camera}<br /><span className="muted">{(s.text || s.caption || s.narration || s.kind).slice(0, 48)}</span></div>
                        </div>
                      ))}
                    </div>
                  </div>
                  {shot && <ShotEditor ep={d.episode.id} shot={shot} editable={!busy && scriptApproved && d.episode.status !== "published"} onDone={reload} />}
                </div>
              ))}
              {tab === "video" && (
                <div className="grid g2">
                  {[["Prévisualisation (basse définition)", preview], ["Rendu final", final]].map(([label, r]: any) => (
                    <div key={label} className="panel">
                      <h2>{label}</h2>
                      {r ? (
                        <>
                          <div className="phone"><video src={fileUrl(r.path) + "#t=1.5"} controls playsInline preload="metadata" /></div>
                          <p className="tiny muted" style={{ marginTop: 8 }}>
                            {r.width}×{r.height} · {r.fps} i/s · {r.duration_s}s · {fmtBytes(r.size_bytes)} · rendu en {r.meta.render_seconds}s · {fmtDate(r.created_at)}
                            <br />Voix : {r.meta.voice_status}
                          </p>
                          <a href={fileUrl(r.path)} download>Télécharger le MP4</a>
                        </>
                      ) : <Empty>Pas encore rendu.</Empty>}
                    </div>
                  ))}
                </div>
              )}
              {tab === "assets" && (
                <div className="panel">
                  <h2>Voix et ressources de l'épisode</h2>
                  <p className="small">Fournisseur de voix : <b>{d.assets_manifest.tts_provider || "—"}</b> — {d.assets_manifest.voice_status || "pas encore préparé"}</p>
                  {(d.assets_manifest.warnings || []).map((w: string, i: number) => <div key={i} className="lock small">⚠ {w}</div>)}
                  <table><thead><tr><th>Plan</th><th>Voix</th><th>Durée</th><th>Ajustement</th></tr></thead><tbody>
                    {Object.entries(d.assets_manifest.voices || {}).map(([k, v]: any) => (
                      <tr key={k}><td>{k}</td><td><audio controls src={fileUrl(v.rel)} /></td>
                        <td>{v.duration}s</td><td>{d.assets_manifest.adjusted_durations?.[k] ? `${d.assets_manifest.adjusted_durations[k]}s` : "—"}</td></tr>
                    ))}
                  </tbody></table>
                  {!Object.keys(d.assets_manifest.voices || {}).length && <p className="small muted">Aucune voix générée : les dialogues sont portés par les sous-titres, l'animation des bouches et le sound design.</p>}
                  <p className="tiny muted">Personnages, décors, musiques et effets sont produits par le moteur 2D/2.5D local ou pris dans la Bibliothèque (éléments importés prioritaires).</p>
                </div>
              )}
              {tab === "logs" && (
                <div className="grid g2">
                  <div className="panel"><h2>Journal de l'épisode</h2>
                    <div className="log">{d.events.map((e: any) => <div key={e.id} className={e.level}>{fmtDate(e.ts)} · {e.message}</div>)}</div></div>
                  <div className="panel"><h2>Tâches</h2>
                    <table><thead><tr><th>#</th><th>Tâche</th><th>Statut</th><th>Message</th></tr></thead><tbody>
                      {d.jobs.map((j: any) => <tr key={j.id}><td>{j.id}</td><td>{j.kind}</td><td><Status s={j.status} /></td><td className="small">{j.error || j.message}</td></tr>)}
                    </tbody></table></div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
