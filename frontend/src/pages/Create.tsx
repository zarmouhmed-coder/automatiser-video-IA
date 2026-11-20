import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, fileUrl } from "../api";
import { PageHead, useAction, usePoll } from "../ui";
import { Palette } from "./Inspirations";

const EXAMPLES: Record<string, string> = {
  horror: "Léa retourne seule dans l'aile B et découvre que la voix imite maintenant Samir.",
  football: "Match retour contre les Corbeaux : Noa doit trouver un contre à l'Éclipse Totale de Kaito.",
  isekai: "Elio approche du niveau 10 et doit comprendre ce que cache l'indice du Système.",
};

export default function Create() {
  const [params] = useSearchParams();
  const { data: dash } = usePoll<any>("/api/dashboard", 6000);
  const [step, setStep] = useState(params.get("series") ? 2 : 1);
  const [series, setSeries] = useState(params.get("series") || "horror");
  const [intent, setIntent] = useState("");
  const [duration, setDuration] = useState(45);
  const [vote, setVote] = useState(1);
  const [inspId, setInspId] = useState<number | null>(null);
  const [link, setLink] = useState("");
  const { data: ideas } = usePoll<any>(step === 2 ? `/api/ideas/${series}` : null, 0);
  const { data: insps } = usePoll<any[]>(step === 3 ? `/api/inspirations?series_id=${series}` : null, 4000);
  const { run, busy } = useAction();
  const nav = useNavigate();
  const s = dash?.series.find((x: any) => x.id === series);
  useEffect(() => { if (s?.lock?.locked && step > 1) setStep(1); }, [s?.lock?.locked]);
  const presets = (insps || []).filter((i) => i.kind === "recette");
  const mine = (insps || []).filter((i) => i.kind !== "recette" && i.status !== "error");
  const chosen = (insps || []).find((i) => i.id === inspId);

  const launch = async () => {
    const ep = await run(() => api.post("/api/episodes", {
      series_id: series, intent, duration_s: duration, allow_vote: vote, inspiration_id: inspId, inspiration_url: inspId ? "" : link,
    }), "C'est parti : écriture, traduction, voix et vidéos FR/EN en cours");
    if (ep) nav(`/production?ep=${(ep as any).id}`);
  };

  return (
    <div className="stack">
      <PageHead title="Créer un épisode" sub="Trois étapes. Ensuite le studio produit tout, et vous ne validez qu'une fois." />
      <div className="steps">
        {["Série", "Idée", "Style"].map((l, i) => (
          <div key={l} className={`step ${step === i + 1 ? "on" : step > i + 1 ? "done" : ""}`}><b>{step > i + 1 ? "✓" : i + 1}</b>{l}</div>
        ))}
      </div>

      {step === 1 && (
        <div className="grid g3">
          {(dash?.series || []).map((x: any) => (
            <div key={x.id} className={`panel scard pick ${series === x.id ? "sel" : ""}`} style={{ ["--accent" as any]: x.accent }}
              onClick={() => !x.lock.locked && setSeries(x.id)}>
              <div className="cover" style={{ backgroundImage: x.cover ? `url(${fileUrl(x.cover)})` : undefined }}><span className="code">SÉRIE {x.code}</span></div>
              <div className="body">
                <h3>{x.name}</h3>
                <p className="small muted">{x.genre}</p>
                {x.lock.locked ? <div className="lock small">🔒 {x.lock.reason}</div> : <p className="tiny muted">{x.episodes_total} épisode(s) · prochain : n°{x.episodes_total + 1}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      {step === 2 && (
        <div className="grid g2">
          <div className="panel" style={{ ["--accent" as any]: s?.accent }}>
            <h2>Votre idée pour {s?.name}</h2>
            <textarea rows={6} value={intent} onChange={(e) => setIntent(e.target.value)} placeholder={EXAMPLES[series]} autoFocus />
            <div className="row" style={{ marginTop: 6 }}>
              <button className="sm ghost" onClick={() => setIntent(EXAMPLES[series])}>Utiliser l'exemple</button>
            </div>
            <div className="grid g2" style={{ marginTop: 10 }}>
              <div className="field"><label>Durée</label>
                <select value={duration} onChange={(e) => setDuration(+e.target.value)}>{[20, 30, 45, 60, 75, 90].map((d) => <option key={d} value={d}>{d} secondes</option>)}</select></div>
              <div className="field"><label>Fin sur un vote du public</label>
                <select value={vote} onChange={(e) => setVote(+e.target.value)}>
                  <option value={1}>Si un vrai dilemme existe</option><option value={2}>Oui</option><option value={0}>Non</option>
                </select></div>
            </div>
          </div>
          <div className="panel">
            <h2>💡 Idées du moment</h2>
            <p className="tiny muted">Actualité réelle filtrée (rien de sensible), transformée en fiction avec vos personnages. Cliquez pour l'utiliser.</p>
            {!ideas ? <span className="small muted"><span className="spinner" /> Lecture de l'actualité…</span> : (
              <div className="chips">
                {ideas.items.slice(0, 10).map((it: any, i: number) => (
                  <button key={i} className="chip" onClick={() => setIntent(it.intent)}>{it.title}<small>{it.source}</small></button>
                ))}
                {!ideas.items.length && <span className="small muted">Aucune idée disponible {ideas.errors?.length ? `(${ideas.errors[0]})` : ""}.</span>}
              </div>
            )}
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="stack">
          <div className="panel">
            <h2>Recettes prêtes à l'emploi</h2>
            <p className="tiny muted">Rythme, accroche, sous-titres et ambiance sonore issus de formats TikTok qui marchent (recettes TrendForge).</p>
            <div className="rgrid">
              <div className={`rcard pick ${inspId === null && !link ? "sel" : ""}`} onClick={() => { setInspId(null); setLink(""); }}>
                <h4>Style de la série</h4><div className="tiny muted">Direction artistique de la bible, sans recette.</div>
              </div>
              {presets.map((i) => (
                <div key={i.id} className={`rcard pick ${inspId === i.id ? "sel" : ""}`} onClick={() => setInspId(i.id)}>
                  <h4>{i.title}</h4><div className="tiny muted">{i.profile.description}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="grid g2">
            <div className="panel">
              <h2>Vos références</h2>
              {!mine.length && <p className="small muted">Aucune pour l'instant. Ajoutez un lien TikTok ci-contre ou dans <Link to="/inspirations">Recettes & inspirations</Link>.</p>}
              <div className="rgrid">
                {mine.map((i) => (
                  <div key={i.id} className={`rcard pick ${inspId === i.id ? "sel" : ""}`} onClick={() => i.status !== "analyzing" && setInspId(i.id)}>
                    <div className="row" style={{ flexWrap: "nowrap" }}>
                      {i.thumbnail_path && <img src={fileUrl(i.thumbnail_path)} alt="" style={{ width: 44, borderRadius: 6 }} />}
                      <div style={{ minWidth: 0 }}><h4>{i.title || (i.url ? "Lien TikTok" : "Référence")}</h4>
                        {i.status === "analyzing" ? <span className="tiny"><span className="spinner" /> analyse…</span> : <Palette colors={i.profile?.palette?.slice(0, 5)} />}</div>
                    </div>
                    <div className="tiny muted" style={{ marginTop: 4 }}>{i.profile?.description}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel">
              <h2>Ou collez un lien TikTok</h2>
              <input placeholder="https://www.tiktok.com/@compte/video/…" value={link} onChange={(e) => { setLink(e.target.value); setInspId(null); }} />
              <p className="tiny muted" style={{ marginTop: 6 }}>Le studio essaie de récupérer la vidéo pour en extraire la recette (rythme, accroche, sous-titres, couleurs). Si TikTok refuse, importez le fichier dans « Recettes & inspirations ».</p>
            </div>
          </div>
          <div className="panel flat">
            <h2>Récapitulatif</h2>
            <p className="small"><b>{s?.name}</b> · {duration} s · vote : {["non", "si dilemme", "oui"][vote]} · style : {chosen ? chosen.title : link ? "lien TikTok (analysé au lancement)" : "celui de la série"}</p>
            <p className="small muted">« {intent} »</p>
            <p className="tiny muted">Le studio écrit, critique, traduit, double les voix FR/EN, monte et rend les deux vidéos, puis vous présente un seul écran de validation.</p>
          </div>
        </div>
      )}

      <div className="wizard-foot">
        <button className="ghost" disabled={step === 1} onClick={() => setStep(step - 1)}>← Retour</button>
        {step < 3 ? (
          <button className="primary" disabled={(step === 1 && (!s || s.lock.locked)) || (step === 2 && intent.trim().length < 5)} onClick={() => setStep(step + 1)}>Continuer →</button>
        ) : (
          <button className="primary" disabled={busy || intent.trim().length < 5} onClick={launch}>▶ Lancer la production</button>
        )}
      </div>
    </div>
  );
}
