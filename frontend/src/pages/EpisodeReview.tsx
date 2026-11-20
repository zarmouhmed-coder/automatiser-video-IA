import { useEffect, useState } from "react";
import { api, fileUrl, fmtBytes, SERIES_COLORS } from "../api";
import { SeriesPill, useAction } from "../ui";

/** Validation unique d'un épisode : vidéo FR/EN + explication complète + décision. */
export default function EpisodeReview({ gate, episode, onDone }: { gate: any; episode: any; onDone: () => void }) {
  const r = gate.report || {};
  const [lang, setLang] = useState<"fr" | "en">("fr");
  const [canon, setCanon] = useState<number[]>([]);
  const [chars, setChars] = useState<number[]>([]);
  const [note, setNote] = useState("");
  const [target, setTarget] = useState("script");
  const [scene, setScene] = useState(0);
  const [open, setOpen] = useState<number | null>(0);
  const { run, busy } = useAction();
  useEffect(() => {
    setCanon((r.canon_proposals || []).map((_: any, i: number) => i));
    setChars((r.new_characters || []).map((_: any, i: number) => i));
  }, [gate.id]);
  const render = (r.renders || []).find((x: any) => x.lang === lang) || (r.renders || [])[0];
  const accent = SERIES_COLORS[episode.series_id];
  const toggle = (list: number[], set: (v: number[]) => void, i: number) =>
    set(list.includes(i) ? list.filter((x) => x !== i) : [...list, i]);
  const decide = (action: string) =>
    run(() => api.post(`/api/gates/${gate.id}/decide`, {
      action, note, target, scene_index: target === "scene" ? scene : null, accept_canon: canon, accept_characters: chars,
    }), { approve: "Épisode validé : packs FR + EN en préparation", changes: "Modification lancée — l'épisode reviendra ici, prêt à revoir", reject: "Épisode rejeté" }[action]).then(onDone);
  const scores = r.critique?.scores || {};
  const avg = Object.values(scores).length ? Math.round((Object.values(scores) as number[]).reduce((a, b) => a + b, 0) / Object.values(scores).length) : null;

  return (
    <div className="panel" style={{ ["--accent" as any]: accent }}>
      <div className="row between">
        <span className="row"><SeriesPill id={episode.series_id} /> <b>Épisode {episode.number}</b></span>
        <span className="small muted">{r.duration_s}s · {r.shots} plans · {r.scenes?.length} scènes{r.costs_usd ? ` · IA ${r.costs_usd} $` : " · 0 $"}</span>
      </div>
      <h2 style={{ marginTop: 10, fontSize: "1.2rem", textTransform: "none", letterSpacing: 0, color: "var(--text)" }}>
        {r.title?.fr}{r.title?.en && <span className="muted"> / {r.title.en}</span>}
      </h2>
      <p className="small">{r.logline?.fr}</p>

      <div className="grid" style={{ gridTemplateColumns: "minmax(220px, 300px) minmax(0, 1fr)", marginTop: 12 }}>
        <div className="stack">
          <div className="tabs" style={{ marginBottom: 6 }}>
            {(r.renders || []).map((x: any) => (
              <button key={x.lang} className={lang === x.lang ? "on" : ""} onClick={() => setLang(x.lang)}>
                {x.lang === "fr" ? "🇫🇷 Français" : "🇬🇧 English"}
              </button>
            ))}
          </div>
          {render && <video key={render.path} src={fileUrl(render.path) + "#t=1.5"} controls playsInline preload="metadata" />}
          {render && <p className="tiny muted">{render.width}×{render.height} · {render.duration_s}s · {fmtBytes(render.size_bytes)}</p>}
          <div className="list-item">
            <b className="small">🎙 Voix</b>
            <div className="small">{Object.entries(r.voices?.langs || {}).map(([k, v]: any) => <div key={k}>{k.toUpperCase()} : {v.status}</div>)}</div>
            {(r.voices?.warnings || []).map((w: string, i: number) => <div key={i} className="lock tiny" style={{ marginTop: 4 }}>⚠ {w}</div>)}
            {(r.voices?.cast || []).length > 0 && (
              <table style={{ marginTop: 6 }}><tbody>
                {r.voices.cast.map((c: any) => <tr key={c.id}><td className="tiny">{c.name}</td><td className="tiny muted">{c.fr} / {c.en}</td></tr>)}
              </tbody></table>
            )}
          </div>
          {r.inspiration && (
            <div className="list-item">
              <b className="small">✦ Inspiration</b>
              <div className="small">{r.inspiration.title || r.inspiration.url}</div>
              <div className="tiny muted">{r.inspiration.description}</div>
              <ul className="tiny" style={{ paddingLeft: 16, margin: "4px 0" }}>{r.inspiration.applied.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}
          {r.originality && (
            <div className="list-item">
              <b className="small">🛡 Originalité</b>
              <div className={`tiny ${r.originality.ok ? "" : "lock"}`}>{r.originality.verdict || r.originality.reason}</div>
              {r.originality.checked && <div className="tiny muted">{r.originality.frames} images comparées à la référence.</div>}
            </div>
          )}
          <div className="list-item">
            <b className="small">🌐 Traduction anglaise</b>
            <div className="tiny">{r.translation?.source || "—"}</div>
            {r.translation?.missing?.length > 0 && <div className="lock tiny">⚠ {r.translation.missing.length} texte(s) restés en français : {(r.translation.errors || []).join(" ; ")}</div>}
          </div>
        </div>

        <div className="stack" style={{ minWidth: 0 }}>
          <div>
            <h2>Ce qui se passe, scène par scène — et pourquoi</h2>
            {(r.scenes || []).map((s: any) => (
              <div key={s.id} className="list-item clickable" onClick={() => setOpen(open === s.index ? null : s.index)}>
                <div className="row between">
                  <b className="small">Scène {s.index + 1} · {s.duration_s}s · {s.characters.join(", ") || "sans personnage"}</b>
                  <span className="tiny muted">{open === s.index ? "▲" : "▼"}</span>
                </div>
                <div className="small">{s.summary}</div>
                {open === s.index && (
                  <div className="row" style={{ alignItems: "flex-start", marginTop: 8, flexWrap: "nowrap" }}>
                    {s.thumb && <img src={fileUrl(s.thumb)} alt="" style={{ width: 90, borderRadius: 6, flexShrink: 0 }} />}
                    <div style={{ minWidth: 0 }}>
                      <ul className="tiny" style={{ paddingLeft: 16, margin: 0 }}>{s.why.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul>
                      {s.lines.map((l: any) => (
                        <div key={l.shot} className="small" style={{ marginTop: 4 }}>
                          <span className="speaker" style={{ color: "var(--amber)" }}>{l.speaker}</span> — {l.fr}
                          {l.en && <div className="tiny muted">EN : {l.en}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="grid g2">
            <div className="list-item">
              <b className="small">🎬 Avis du directeur {avg != null && <span className="pill" style={{ marginLeft: 6 }}>{avg}/100</span>}</b>
              {r.critique?.hook && (
                <div className="tiny" style={{ marginTop: 4 }}>
                  <span className="meter">Accroche <i><span style={{ width: `${r.critique.hook.score * 10}%` }} /></i> {r.critique.hook.score}/10</span>
                  {r.critique.hook.missing?.length > 0 && <span className="muted"> — manque : {r.critique.hook.missing.join(", ")}</span>}
                </div>
              )}
              <div className="tiny muted">{r.critique?.summary}</div>
              {(r.critique?.issues || []).slice(0, 6).map((i: any, k: number) => (
                <div key={k} className={`issue ${i.severity}`} style={{ marginTop: 4 }}><div className="tiny">{i.message}</div><div className="tiny muted">→ {i.suggestion}</div></div>
              ))}
              {!(r.critique?.issues || []).length && <div className="tiny">Aucun problème relevé.</div>}
            </div>
            <div className="list-item">
              <b className="small">🏁 Fin de l'épisode : {r.ending?.type}</b>
              {r.ending?.type === "vote" && (
                <div className="small" style={{ marginTop: 4 }}>
                  🗳️ {r.ending.question.fr}<div className="tiny muted">{r.ending.options.fr.join(" / ")}</div>
                  <div className="tiny muted">EN : {r.ending.question.en} — {r.ending.options.en.join(" / ")}</div>
                </div>
              )}
              <div className="tiny" style={{ marginTop: 6 }}>{r.ending?.why}</div>
            </div>
          </div>

          {((r.canon_proposals || []).length > 0 || (r.new_characters || []).length > 0) && (
            <div className="list-item">
              <b className="small">📖 Ce qui entrera dans la bible si vous validez (décochez pour refuser)</b>
              {(r.canon_proposals || []).map((p: any, i: number) => (
                <label key={i} className="row small" style={{ margin: "4px 0", color: "var(--text)" }}>
                  <input type="checkbox" checked={canon.includes(i)} onChange={() => toggle(canon, setCanon, i)} /> [{p.category}] {p.text}
                </label>
              ))}
              {(r.new_characters || []).map((c: any, i: number) => (
                <label key={`c${i}`} className="row small" style={{ margin: "4px 0", color: "var(--text)" }}>
                  <input type="checkbox" checked={chars.includes(i)} onChange={() => toggle(chars, setChars, i)} /> Nouveau personnage : {c.name} ({c.role})
                </label>
              ))}
            </div>
          )}

          <div className="list-item" style={{ borderColor: "rgba(255,176,0,.5)" }}>
            <b className="small" style={{ color: "var(--amber)" }}>Votre décision</b>
            <ul className="tiny" style={{ paddingLeft: 16, margin: "4px 0" }}>{(r.on_approve || []).map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>
            <div className="row" style={{ marginTop: 8 }}>
              <button className="primary" disabled={busy} onClick={() => decide("approve")}>✓ Valider l'épisode (FR + EN)</button>
              <button className="danger" disabled={busy} onClick={() => confirm("Rejeter cet épisode ?") && decide("reject")}>✕ Rejeter</button>
            </div>
            <hr />
            <div className="small" style={{ marginBottom: 6 }}>Ou demander une modification :</div>
            <div className="row" style={{ alignItems: "flex-start" }}>
              <select value={target} onChange={(e) => setTarget(e.target.value)} style={{ width: "auto" }}>
                <option value="script">Réécrire tout l'épisode</option>
                <option value="scene">Réécrire une seule scène</option>
                <option value="render">Refaire voix + vidéo seulement</option>
              </select>
              {target === "scene" && (
                <select value={scene} onChange={(e) => setScene(+e.target.value)} style={{ width: "auto" }}>
                  {(r.scenes || []).map((s: any) => <option key={s.index} value={s.index}>Scène {s.index + 1}</option>)}
                </select>
              )}
            </div>
            <textarea rows={2} style={{ marginTop: 8 }} placeholder="Ce que vous voulez changer (l'agent s'en souviendra pour la suite)" value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="amber" style={{ marginTop: 8 }} disabled={busy || (target !== "render" && !note.trim())} onClick={() => decide("changes")}>
              ✎ Lancer la modification
            </button>
            <p className="tiny muted" style={{ marginTop: 6 }}>Tout se refait automatiquement (texte, traduction, voix, vidéo) puis l'épisode revient ici pour une nouvelle validation unique.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
