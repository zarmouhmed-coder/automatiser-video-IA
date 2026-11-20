import { useEffect, useState } from "react";
import { api } from "../api";
import { PageHead, useAction, usePoll } from "../ui";

function SecretField({ k, set, reload }: { k: string; set: boolean; reload: () => void }) {
  const [v, setV] = useState("");
  const { run } = useAction();
  return (
    <div className="field">
      <label>{k} {set ? <span className="pill green">configurée</span> : <span className="pill amber">configuration requise</span>}</label>
      <div className="row">
        <input type="password" autoComplete="off" placeholder={set ? "•••••••• (laisser vide pour conserver)" : "Coller la clé"} value={v} onChange={(e) => setV(e.target.value)} style={{ flex: 1 }} />
        <button disabled={!v} onClick={() => run(() => api.put("/api/secrets", { key: k, value: v }), "Clé enregistrée dans .env (local, hors Git)").then(() => { setV(""); reload(); })}>Enregistrer</button>
        {set && <button className="danger" onClick={() => confirm("Supprimer cette clé ?") && run(() => api.put("/api/secrets", { key: k, value: "" }), "Clé supprimée").then(reload)}>Supprimer</button>}
      </div>
    </div>
  );
}

export default function Settings() {
  const { data, reload } = usePoll<any>("/api/settings", 0);
  const { data: status } = usePoll<any>("/api/status", 0);
  const [s, setS] = useState<any>(null);
  const { run, busy } = useAction();
  useEffect(() => { if (data) setS(data.settings); }, [data]);
  if (!s || !status) return <p className="muted">Chargement…</p>;
  const set = (k: string, v: any) => setS({ ...s, [k]: v });
  const num = (k: string, label: string, step = 1) => (
    <div className="field"><label>{label}</label><input type="number" step={step} value={s[k]} onChange={(e) => set(k, +e.target.value)} /></div>
  );
  return (
    <div className="stack">
      <PageHead title="Paramètres" sub="Modèles, clés API, budgets, fichiers, qualité et performances.">
        <button className="primary" disabled={busy} onClick={() => run(() => api.put("/api/settings", s), "Paramètres enregistrés").then(reload)}>Enregistrer</button>
      </PageHead>
      <div className="grid g2">
        <div className="panel">
          <h2>Modèles d'écriture (agents)</h2>
          <div className="field"><label>Fournisseur</label>
            <select value={s.llm_provider} onChange={(e) => set("llm_provider", e.target.value)}>
              <option value="demo">Mode démo local — gratuit, sans IA</option>
              <option value="anthropic">API Claude (Anthropic) — clé requise, facturée à l'usage</option>
              <option value="ollama">Ollama — modèle local installé par vous</option>
            </select></div>
          <p className="tiny muted">Un abonnement claude.ai ne donne pas accès à l'API : une clé de la console Anthropic (facturation séparée) est nécessaire.</p>
          {s.llm_provider === "anthropic" && (
            <div className="grid g2">
              <div className="field"><label>Modèle</label><input value={s.anthropic_model} onChange={(e) => set("anthropic_model", e.target.value)} /></div>
              <div className="field"><label>Effort</label><select value={s.anthropic_effort} onChange={(e) => set("anthropic_effort", e.target.value)}>{["low", "medium", "high", "xhigh", "max"].map((x) => <option key={x}>{x}</option>)}</select></div>
              <label className="row"><input type="checkbox" checked={s.anthropic_fallbacks} onChange={(e) => set("anthropic_fallbacks", e.target.checked)} /> Repli automatique côté serveur si le modèle refuse une demande</label>
            </div>
          )}
          {s.llm_provider === "ollama" && (
            <div className="grid g2">
              <div className="field"><label>URL Ollama</label><input value={s.ollama_url} onChange={(e) => set("ollama_url", e.target.value)} /></div>
              <div className="field"><label>Modèle</label><input value={s.ollama_model} onChange={(e) => set("ollama_model", e.target.value)} /></div>
            </div>
          )}
          <SecretField k="ANTHROPIC_API_KEY" set={data.secrets.ANTHROPIC_API_KEY} reload={reload} />
          <hr />
          <h2>Voix</h2>
          <div className="field"><label>Synthèse vocale</label>
            <select value={s.tts_provider} onChange={(e) => set("tts_provider", e.target.value)}>
              {Object.entries(status.tts).filter(([k]) => k !== "active").map(([k, v]: any) => (
                <option key={k} value={k}>{v.label}{v.ready ? "" : " — configuration requise"}</option>
              ))}
            </select></div>
          {s.tts_provider === "piper" && (
            <div className="list-item small">
              {status.tts.piper_models.ready ? "✓ Voix Piper installées (FR : 3 voix, EN : 4 voix)." :
                `Voix à télécharger : ${status.tts.piper_models.missing.length} modèle(s) (~500 Mo, une seule fois).`}
              {!status.tts.piper_models.ready && <div style={{ marginTop: 6 }}><button className="sm" onClick={() => run(() => api.post("/api/voices/download"), "Téléchargement lancé (voir la file d'attente du Dashboard)")}>⤓ Télécharger les voix maintenant</button></div>}
            </div>
          )}
          {s.tts_provider === "elevenlabs" && <SecretField k="ELEVENLABS_API_KEY" set={data.secrets.ELEVENLABS_API_KEY} reload={reload} />}
          {status.tts[s.tts_provider]?.note && <p className="tiny muted">{status.tts[s.tts_provider].note}</p>}
        </div>
        <div className="panel">
          <h2>Production</h2>
          <div className="field"><label>Validations</label>
            <select value={s.validation_mode} onChange={(e) => set("validation_mode", e.target.value)}>
              <option value="episode">Une seule validation par épisode, tout expliqué (recommandé)</option>
              <option value="detailed">Détaillé : 4 validations (scénario, storyboard, prévisu, rendu)</option>
            </select></div>
          <div className="field"><label>Versions produites</label>
            <select value={s.languages} onChange={(e) => set("languages", e.target.value)}>
              <option value="fr,en">Français + Anglais</option>
              <option value="fr">Français seulement</option>
            </select></div>
          <div className="field"><label>Traduction anglaise</label>
            <select value={s.translation_provider} onChange={(e) => set("translation_provider", e.target.value)}>
              <option value="auto">Automatique (IA configurée, sinon modèle local hors ligne)</option>
              <option value="argos">Modèle local hors ligne uniquement (gratuit)</option>
              <option value="llm">IA configurée uniquement</option>
            </select></div>
          <p className="tiny muted">Le réglage de validation s'applique aux nouveaux épisodes.</p>
          <hr />
          <h2>Budgets, quotas et limites</h2>
          <div className="grid g2">
            {num("budget_monthly_usd", "Budget IA mensuel ($)", 0.5)}
            {num("budget_episode_usd", "Budget IA par épisode ($)", 0.1)}
            {num("max_llm_calls_per_episode", "Appels IA max par épisode")}
            {num("llm_timeout_s", "Délai max d'un appel IA (s)")}
            {num("render_timeout_s", "Délai max d'un rendu (s)")}
            {num("max_parallel_workflows", "Workflows en parallèle (1 à 3)")}
          </div>
          <p className="small">Dépenses du mois : <b>{data.costs.month_usd.toFixed(4)} $</b></p>
          {data.costs.by_provider.map((c: any) => <div key={c.provider + c.model} className="tiny muted">{c.provider} · {c.model} : {c.calls} appels · {c.usd} $</div>)}
          <hr />
          <h2>Qualité vidéo</h2>
          <div className="grid g3">
            {num("video_width", "Largeur")}
            {num("video_height", "Hauteur")}
            {num("video_fps", "Images/s")}
            {num("video_crf", "CRF (qualité H.264)")}
            <div className="field"><label>Préréglage x264</label><select value={s.video_preset} onChange={(e) => set("video_preset", e.target.value)}>{["ultrafast", "veryfast", "fast", "medium", "slow"].map((x) => <option key={x}>{x}</option>)}</select></div>
            <div className="field"><label>Débit audio AAC</label><select value={s.audio_bitrate} onChange={(e) => set("audio_bitrate", e.target.value)}>{["128k", "160k", "192k", "256k"].map((x) => <option key={x}>{x}</option>)}</select></div>
          </div>
          <div className="grid g3">
            {num("preview_scale", "Échelle prévisu", 0.05)}
            {num("preview_fps", "Images/s prévisu")}
            {num("preview_max_seconds", "Extrait test max (s, 0 = tout)")}
          </div>
        </div>
      </div>
      <div className="grid g2">
        <div className="panel">
          <h2>Fichiers et sauvegardes</h2>
          <p className="small">Données : <code>{status.data_dir}</code></p>
          <p className="small">FFmpeg : <code>{status.ffmpeg || "configuration requise"}</code></p>
          <div className="field" style={{ maxWidth: 220 }}><label>Sauvegardes conservées</label><input type="number" value={s.backups_keep} onChange={(e) => set("backups_keep", +e.target.value)} /></div>
          <button onClick={() => run(() => api.post("/api/backups"), "Sauvegarde créée (base + bibles)")}>Sauvegarder maintenant</button>
        </div>
        <div className="panel">
          <h2>Système</h2>
          <p className="small">{status.system.os} · Python {status.system.python} · {status.system.cpu_count} cœurs · {status.system.disk_free_gb} Go libres</p>
          <p className="tiny muted">Rendu 2D/2.5D sur processeur (aucun GPU requis). Un seul rendu lourd à la fois.</p>
        </div>
      </div>
    </div>
  );
}
