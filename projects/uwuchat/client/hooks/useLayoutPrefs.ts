import { useLocalStorage } from "./useLocalStorage";

export type PanelId = "civitai_browser";

export function useLayoutPrefs() {
  const [showChat, setShowChat] = useLocalStorage("airunner_show_chat", true);
  const [showCanvas, setShowCanvas] = useLocalStorage("airunner_show_canvas", false);
  const [ttsOn, setTtsOn] = useLocalStorage("airunner_tts_on", false);
  const [sttOn, setSttOn] = useLocalStorage("airunner_stt_on", false);
  const [rawPanel, setRightPanel] = useLocalStorage<PanelId | null>("airunner_right_panel", null);
  const rightPanel: PanelId | null = rawPanel === "civitai_browser" ? "civitai_browser" : null;
  const [chatbotId, setChatbotId] = useLocalStorage<number | null>("airunner_chatbot_id", null);
  const [showPipelineCost, setShowPipelineCost] = useLocalStorage("airunner_show_pipeline_cost", false);
  const [inspectingCallChainId, setInspectingCallChainId] = useLocalStorage<string | null>("airunner_inspecting_call_chain", null);

  return {
    showChat, setShowChat,
    showCanvas, setShowCanvas,
    ttsOn, setTtsOn,
    sttOn, setSttOn,
    rightPanel, setRightPanel,
    chatbotId, setChatbotId,
    showPipelineCost, setShowPipelineCost,
    inspectingCallChainId, setInspectingCallChainId,
  };
}
