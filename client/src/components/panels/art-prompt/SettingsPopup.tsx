import { CompactSlider, type ArtSettingsData } from "./ArtShared";
import styles from "./SettingsPopup.module.css";
import shared from "./ArtShared.module.css";

export function SettingsPopup({
  steps, cfgScale, nSamples, imagesPerBatch,
  onStepsChange, onCfgScaleChange, onNSamplesChange, onImagesPerBatchChange,
  hideHeader = false,
}: ArtSettingsData & { hideHeader?: boolean }) {
  return (
    <div className={`d-flex flex-column ${styles.wrap}`}>
      {!hideHeader && (
        <div className={shared.sectionLabelTight}>
          Art Generator Settings
        </div>
      )}
      <CompactSlider label="Steps"   value={steps}          min={1}   max={150}  step={1}   onChange={onStepsChange} />
      <CompactSlider label="CFG"     value={cfgScale}       min={1}   max={30}   step={0.1} float onChange={onCfgScaleChange} />
      <CompactSlider label="Samples" value={nSamples}       min={1}   max={1000} step={1}   onChange={onNSamplesChange} />
      <CompactSlider label="Batch"   value={imagesPerBatch} min={1}   max={6}    step={1}   onChange={onImagesPerBatchChange} />
    </div>
  );
}
