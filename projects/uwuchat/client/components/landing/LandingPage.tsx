import { Github, Download, Search, Shield, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { PublicShell } from "../layout/PublicShell";

const REPO = "https://github.com/Capsize-Games/uwuchat-oss";

export default function LandingPage() {
  const { t } = useTranslation();
  const text = (key: string, fallback: string) => t(key, fallback);
  return (
    <PublicShell stickyFooter={false}>
      <style>{`
        .landing-page { min-height: 100%; background: radial-gradient(ellipse at 50% 0%, rgba(124,58,237,.16), transparent 55%); color: var(--theme-text); }
        .landing-hero { max-width: 860px; margin: 0 auto; padding: 96px 24px 72px; text-align: center; }
        .landing-eyebrow { color: #b58cff; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: .78rem; }
        .landing-hero-title { margin: 14px 0; font-size: clamp(2.8rem, 8vw, 5.5rem); font-weight: 850; letter-spacing: -.06em; background: linear-gradient(110deg, #fff, #c4a4ff 55%, #73d8ff); -webkit-background-clip: text; background-clip: text; color: transparent; }
        .landing-hero-sub { max-width: 650px; margin: 0 auto; color: var(--theme-text-secondary); font-size: 1.2rem; line-height: 1.65; }
        .landing-hero-actions { display: flex; justify-content: center; flex-wrap: wrap; gap: 12px; margin-top: 32px; }
        .landing-btn-primary, .landing-btn-outline { display: inline-flex; align-items: center; gap: 8px; text-decoration: none; }
        .landing-install { margin-top: 18px; color: var(--theme-text-secondary); font-size: .9rem; }
        .landing-features, .landing-steps { max-width: 1080px; margin: 0 auto; padding: 48px 24px; }
        .landing-oss-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
        .landing-feature-card { padding: 26px; border: 1px solid rgba(255,255,255,.08); border-radius: 16px; background: rgba(255,255,255,.025); }
        .landing-feature-icon { display: inline-flex; padding: 10px; border-radius: 12px; background: rgba(124,58,237,.18); color: #c4a4ff; }
        .landing-feature-title { margin: 18px 0 8px; font-size: 1.12rem; }
        .landing-feature-desc, .landing-steps p { color: var(--theme-text-secondary); line-height: 1.55; }
        .landing-section-title { text-align: center; margin-bottom: 28px; }
        .landing-steps-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 28px; text-align: center; }
        .landing-steps-grid strong { display: inline-grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: var(--theme-primary); color: #fff; }
        .landing-steps-grid h3 { margin: 14px 0 6px; font-size: 1.05rem; }
        .landing-cta { padding: 76px 24px 96px; text-align: center; }
        .landing-cta-sub { color: var(--theme-text-secondary); margin-bottom: 24px; }
        .landing-btn-lg { display: inline-flex; align-items: center; gap: 8px; }
        @media (max-width: 700px) { .landing-oss-grid, .landing-steps-grid { grid-template-columns: 1fr; } .landing-hero { padding-top: 56px; } }
      `}</style>
      <main className="landing-page">
        <section className="landing-hero">
          <p className="landing-eyebrow">{text("landing.oss.eyebrow", "Open source AI companions")}</p>
          <h1 className="landing-hero-title">{text("landing.oss.title", "AI that remembers you.")}</h1>
          <p className="landing-hero-sub">{text("landing.oss.subtitle", "Run UwUchat on your own machine, choose your model provider, and keep your conversations under your control.")}</p>
          <div className="landing-hero-actions">
            <a className="btn landing-btn-primary" href={REPO} target="_blank" rel="noreferrer"><Github size={18} />{text("landing.oss.github", "Get UwUchat on GitHub")}</a>
            <a className="btn landing-btn-outline" href={`${REPO}#readme`} target="_blank" rel="noreferrer"><Download size={18} />{text("landing.oss.setup", "Read the setup guide")}</a>
          </div>
          <div className="landing-install">{text("landing.oss.install_hint", "Clone the repo, add your provider keys, and start with Docker Compose.")}</div>
        </section>
        <section className="landing-features landing-oss-grid">
          <div className="landing-feature-card"><div className="landing-feature-icon" data-hue="purple"><Sparkles size={24} /></div><h2 className="landing-feature-title">{text("landing.oss.memory_title", "Persistent memory")}</h2><p className="landing-feature-desc">{text("landing.oss.memory_desc", "Build companions with continuity across sessions instead of starting over every time.")}</p></div>
          <div className="landing-feature-card"><div className="landing-feature-icon" data-hue="green"><Search size={24} /></div><h2 className="landing-feature-title">{text("landing.oss.search_title", "Optional web search")}</h2><p className="landing-feature-desc">{text("landing.oss.search_desc", "Run FastSearch yourself and configure its API key when you want current information.")}</p></div>
          <div className="landing-feature-card"><div className="landing-feature-icon" data-hue="pink"><Shield size={24} /></div><h2 className="landing-feature-title">{text("landing.oss.control_title", "Your deployment")}</h2><p className="landing-feature-desc">{text("landing.oss.control_desc", "Use local models or OpenRouter, host it yourself, and decide where your data lives.")}</p></div>
        </section>
        <section className="landing-steps">
          <h2 className="landing-section-title">{text("landing.oss.steps_title", "Start in three steps")}</h2>
          <div className="landing-steps-grid">
            <div><strong>1</strong><h3>{text("landing.oss.step_one", "Clone UwUchat")}</h3><p>{text("landing.oss.step_one_desc", "Download the source from GitHub.")}</p></div>
            <div><strong>2</strong><h3>{text("landing.oss.step_two", "Choose your providers")}</h3><p>{text("landing.oss.step_two_desc", "Add model and optional self-hosted FastSearch settings in your environment.")}</p></div>
            <div><strong>3</strong><h3>{text("landing.oss.step_three", "Create your companion")}</h3><p>{text("landing.oss.step_three_desc", "Run the stack and start chatting from your own instance.")}</p></div>
          </div>
        </section>
        <section className="landing-cta"><h2 className="landing-cta-title">{text("landing.oss.cta_title", "Make it yours.")}</h2><p className="landing-cta-sub">{text("landing.oss.cta_subtitle", "UwUchat is free to use and open to contributions.")}</p><a className="btn landing-btn-primary landing-btn-lg" href={REPO} target="_blank" rel="noreferrer"><Github size={20} />{text("landing.oss.cta", "View the project on GitHub")}</a></section>
      </main>
    </PublicShell>
  );
}
