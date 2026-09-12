/** Clean, well-aligned per-stage controls. */

import { useState } from "react";
import styles from "./PipelineStageControls.module.css";
import type {
  PipelineStage,
  OpenRouterModelInfo,
  ConversationCostBreakdownItem,
} from "../../types/pipeline";

const CLR = ["#6c63ff","#4ade80","#f87171","#facc15","#38bdf8","#a78bfa","#fb923c","#2dd4bf","#f472b6","#94a3b8"];

interface Props {
  stages: PipelineStage[];
  models: OpenRouterModelInfo[];
  costBreakdown: ConversationCostBreakdownItem[];
  pending: Record<string, Record<string, unknown>>;
  setPending: (key: string, overrides: Record<string, unknown>) => void;
  onSaveStage: (key: string, overrides: Record<string, unknown>) => void;
  onSavePrompt: (key: string, prompt: string) => void;
  onResetStage: (key: string) => void;
}

export function PipelineStageControls({ stages, models, costBreakdown, pending, setPending, onSaveStage, onSavePrompt, onResetStage }: Props) {
  const grp1 = ["TOOL_CLASSIFICATION","DIALOGUE","NODE_VALIDATOR"];
  return (
    <div>
      <div className={styles.stageHeader}>PER-MESSAGE</div>
      {stages.filter(s => grp1.includes(s.key)).map((s,i) =>
        <Card key={s.key} s={s} models={models} cost={costBreakdown.find(c=>c.pipeline_key===s.key)} color={CLR[i%CLR.length]} pending={pending[s.key]||{}} setPending={(o)=>setPending(s.key,o)} onSave={(o)=>onSaveStage(s.key,o)} onSavePrompt={(p)=>onSavePrompt(s.key,p)} onReset={()=>onResetStage(s.key)} />)}
      <div className={styles.stageHeaderMt}>BACKGROUND</div>
      {stages.filter(s => !grp1.includes(s.key)).map((s,i) =>
        <Card key={s.key} s={s} models={models} cost={costBreakdown.find(c=>c.pipeline_key===s.key)} color={CLR[(i+3)%CLR.length]} pending={pending[s.key]||{}} setPending={(o)=>setPending(s.key,o)} onSave={(o)=>onSaveStage(s.key,o)} onSavePrompt={(p)=>onSavePrompt(s.key,p)} onReset={()=>onResetStage(s.key)} />)}
    </div>
  );
}

function Card({ s, models, cost, color, pending, setPending, onSave, onSavePrompt, onReset }: {
  s: PipelineStage; models: OpenRouterModelInfo[]; cost?: ConversationCostBreakdownItem; color: string;
  pending: Record<string,unknown>; setPending:(o:Record<string,unknown>)=>void; onSave:(o:Record<string,unknown>)=>void; onSavePrompt:(p:string)=>void; onReset:()=>void;
}) {
  const [open, setOpen] = useState(false);
  const [editPrompt, setEditPrompt] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dirty = Object.keys(pending).length > 0;

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(pm);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };
  const cfg = s.config as Record<string,number>;
  const pm = pending as Record<string,unknown>;
  const opac = s.enabled ? 1 : 0.45;

  const saveBtnClass = dirty && !saving
    ? styles.saveBtn
    : styles.saveBtnDisabled;

  return (
    // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
    <div className={styles.card} style={{ opacity: opac }}>
      {/* collapsed row */}
      <div onClick={()=>setOpen(!open)} className={styles.collapsedRow}>
        <div
          className={styles.dot}
          // eslint-disable-next-line no-restricted-syntax -- CSS custom property for pipeline color
          style={{ "--stage-color": color } as React.CSSProperties}
        />
        <span className={styles.stageLabel}>{s.label}</span>
        <span className={styles.modelName}>{s.model||"none"}</span>
        {cost && <span className={styles.costValue}>${(cost.cost_usd*30).toFixed(4)}/mo</span>}
      </div>
      {/* expanded */}
      {open && (
        <div className={styles.expanded}>
          <div className={styles.triggerText}>{s.trigger}</div>
          <Row label="Model">
            <select className={styles.input} value={String(pm.model??s.model??"")} onChange={e=>setPending({...pm,model:e.target.value})}>
              <option value="">(unchanged)</option>
              {models.slice(0,80).map(m=><option key={m.model_id} value={m.model_id}>{m.display_name}</option>)}
            </select>
          </Row>
          {cfg.interval_turns!==undefined&&<Row label="Every N turns"><input type="number" className={styles.input} min={1} max={50} value={pm.interval_turns??cfg.interval_turns} onChange={e=>setPending({...pm,interval_turns:Number(e.target.value)})}/></Row>}
          {cfg.min_complexity!==undefined&&<Row label="Min complexity"><input type="number" className={styles.input} min={0} max={1} step={0.01} value={pm.min_complexity??cfg.min_complexity} onChange={e=>setPending({...pm,min_complexity:Number(e.target.value)})}/></Row>}
          {cfg.max_tokens!==undefined&&<Row label="Max tokens"><input type="number" className={styles.input} min={1} max={8000} value={pm.max_tokens??cfg.max_tokens} onChange={e=>setPending({...pm,max_tokens:Number(e.target.value)})}/></Row>}
          {cfg.temperature!==undefined&&<Row label="Temp"><input type="number" className={styles.input} min={0} max={2} step={0.1} value={pm.temperature??cfg.temperature} onChange={e=>setPending({...pm,temperature:Number(e.target.value)})}/></Row>}
          {cfg.keep_recent!==undefined&&<Row label="Keep recent"><input type="number" className={styles.input} min={1} max={50} value={pm.keep_recent??cfg.keep_recent} onChange={e=>setPending({...pm,keep_recent:Number(e.target.value)})}/></Row>}
          {cost&&<Row label="This chatbot"><span className={styles.costRow}>${cost.cost_usd.toFixed(6)} ({cost.pct_of_total}% · {cost.call_count} calls)</span></Row>}
          {s.prompt_template&&<div className={styles.promptSection}>
            <div className={styles.promptHeader}>
              <span className={styles.promptLabel}>Prompt</span>
              <button className={styles.smBtn} onClick={()=>{if(editPrompt){onSavePrompt(String(pm.prompt_template||s.prompt_template));setEditPrompt(false)}else setEditPrompt(true)}}>{editPrompt?"Save":"Edit"}</button>
            </div>
            <textarea
              className={editPrompt ? styles.promptTextarea : styles.promptTextareaReadOnly}
              value={String(pm.prompt_template??s.prompt_template??"")}
              onChange={e=>setPending({...pm,prompt_template:e.target.value})}
              readOnly={!editPrompt}
            />
          </div>}
          {saveError && <div className={styles.errorText}>{saveError}</div>}
          <div className={styles.btnRow}>
            <button className={saveBtnClass} onClick={handleSave} disabled={!dirty || saving}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button className={styles.resetBtn} onClick={() => { onReset(); setPending({}); }}>
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.configRow}>
      <span className={styles.configLabel}>{label}</span>
      <span>{children}</span>
    </div>
  );
}
