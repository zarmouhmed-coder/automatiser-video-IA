import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { PageHead, SeriesPill, useAction, usePoll } from "../ui";

const EXAMPLES: Record<string, string> = {
  horror: "Léa retourne seule dans l'aile B et découvre que la voix imite maintenant Samir.",
  football: "Match retour contre les Corbeaux : Noa doit trouver un contre à l'Éclipse Totale de Kaito.",
  isekai: "Elio approche du niveau 10 et doit comprendre ce que cache l'indice du Système.",
};

export default function Create() {
  const { data: dash } = usePoll<any>("/api/dashboard", 5000);
  const [series, setSeries] = useState("horror");
  const [intent, setIntent] = useState("");
  const [duration, setDuration] = useState(45);
  const [style, setStyle] = useState("");
  const [vote, setVote] = useState(1);
  const { run, busy } = useAction();
  const nav = useNavigate();
  const lock = dash?.series.find((s: any) => s.id === series)?.lock;

  const submit = async () => {
    const ep = await run(
      () => api.post("/api/episodes", { series_id: series, intent, duration_s: duration, style, allow_vote: vote }),
      "Épisode créé : l'agent scénariste démarre",
    );
    if (ep) nav(`/scenarios?ep=${(ep as any).id}`);
  };

  return (
    <div className="stack">
      <PageHead title="Création · Mode Directeur" sub="Donnez une intention en langage naturel ; l'agent de la série écrit dans les règles de sa bible." />
      <div className="grid g2">
        <div className="panel">
          <div className="field">
            <label>Série</label>
            <div className="row">
              {(dash?.series || []).map((s: any) => (
                <button key={s.id} className={series === s.id ? "primary" : ""} onClick={() => setSeries(s.id)}
                  style={series === s.id ? { background: s.accent, borderColor: s.accent } : {}}>
                  {s.code} · {s.name}
                </button>
              ))}
            </div>
          </div>
          {lock?.locked && <div className="lock field">🔒 {lock.reason}</div>}
          <div className="field">
            <label htmlFor="intent">Intention du réalisateur</label>
            <textarea id="intent" rows={5} value={intent} onChange={(e) => setIntent(e.target.value)}
              placeholder={EXAMPLES[series]} />
            <button className="sm ghost" onClick={() => setIntent(EXAMPLES[series])}>Utiliser l'exemple</button>
          </div>
          <div className="grid g3">
            <div className="field">
              <label>Durée cible</label>
              <select value={duration} onChange={(e) => setDuration(+e.target.value)}>
                {[20, 30, 45, 60, 90, 120].map((d) => <option key={d} value={d}>{d} secondes</option>)}
              </select>
            </div>
            <div className="field">
              <label>Fin sur un vote</label>
              <select value={vote} onChange={(e) => setVote(+e.target.value)}>
                <option value={1}>Si un vrai dilemme existe</option>
                <option value={2}>Oui, obligatoire</option>
                <option value={0}>Non (révélation / émotion)</option>
              </select>
            </div>
            <div className="field">
              <label>Style</label>
              <input value={style} onChange={(e) => setStyle(e.target.value)} placeholder="ex. lent, oppressant" />
            </div>
          </div>
          <button className="primary" disabled={busy || intent.trim().length < 5 || lock?.locked} onClick={submit}>
            ▶ Lancer l'écriture
          </button>
        </div>
        <div className="panel flat">
          <h2>Ce qui va se passer</h2>
          <ol className="small" style={{ paddingLeft: 18 }}>
            <li>L'agent scénariste <SeriesPill id={series} /> écrit le script (scènes, plans, dialogues).</li>
            <li>Le directeur/critique relève dialogues plats, incohérences, rythme, répétitions, tension.</li>
            <li><b>Vous validez</b> le scénario (ou demandez une modification, scène par scène).</li>
            <li>Storyboard avec vignettes réelles → <b>votre validation</b>.</li>
            <li>Personnages, décors, voix, effets → prévisualisation basse définition → <b>votre validation</b>.</li>
            <li>Rendu final 1080×1920 H.264/AAC → <b>votre validation</b>.</li>
            <li>Pack de publication manuelle (rien n'est publié automatiquement).</li>
          </ol>
          <p className="small muted">
            Si l'épisode précédent de cette série se termine sur un vote, la création reste bloquée tant que vous n'avez
            pas saisi et validé le résultat officiel. Les autres séries continuent normalement.
          </p>
        </div>
      </div>
    </div>
  );
}
