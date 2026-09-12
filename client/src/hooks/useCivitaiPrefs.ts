import { useLocalStorage } from "./useLocalStorage";
import { useSessionStorage } from "./useSessionStorage";

/** Storage key for the CivitAI API bearer secret. */
export const CIVITAI_API_KEY = "airunner_civitai_api_key";

export function useCivitaiPrefs() {
  const [baseModel, setBaseModel] = useLocalStorage("airunner_civitai_base_model", "");
  const [modelType, setModelType] = useLocalStorage("airunner_civitai_model_type", "");
  const [selectedModelId, setSelectedModelId] = useLocalStorage<number | null>("airunner_civitai_selected_model", null);
  // API key is a bearer secret — sessionStorage limits exposure
  // to the current tab's lifetime, consistent with the existing
  // sessionStorage write in CivitaiModelDetailDownload.
  const [apiKey, setApiKey] = useSessionStorage(CIVITAI_API_KEY, "");

  return { baseModel, setBaseModel, modelType, setModelType, selectedModelId, setSelectedModelId, apiKey, setApiKey };
}
