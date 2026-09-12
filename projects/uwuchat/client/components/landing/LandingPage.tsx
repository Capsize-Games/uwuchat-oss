import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { UserStar } from "lucide-react";
import { PublicShell } from "../layout/PublicShell";
import { getTiers, getFeatures, getCreatorDimensions } from "./landingData";

export default function LandingPage() {
  const navigate = useNavigate(); const { t } = useTranslation(); const goRegister = () => navigate("/register");
  const TIERS = getTiers(t); const FEATURES = getFeatures(t); const CREATOR_DIMENSIONS = getCreatorDimensions(t);

  return (
    <PublicShell stickyFooter={false}>
      <style>{`
        .landing-page { display: block; position: relative; }
        .landing-page::before { content: ""; position: absolute; inset: 0; background: radial-gradient(ellipse 55% 30% at 75% 45%, rgba(124,58,237,0.09) 0%, transparent 60%), radial-gradient(ellipse 50% 25% at 25% 55%, rgba(0,132,185,0.05) 0%, transparent 55%), radial-gradient(ellipse 70% 35% at 50% 100%, rgba(168,85,247,0.1) 0%, transparent 65%), linear-gradient(180deg,rgba(0,132,185,0.02) 0%,rgba(124,58,237,0.03) 40%,rgba(168,85,247,0.05) 100%); pointer-events: none; z-index: 0; }
        .landing-page > * { position: relative; z-index: 1; }
        .landing-hero-glow { -webkit-mask-image: linear-gradient(to bottom,black 0%,black 90%,transparent 100%); mask-image: linear-gradient(to bottom,black 0%,black 90%,transparent 100%); z-index: 1 !important; }
        .landing-feature-card:hover { transform: none !important; }
        .landing-tier-card { text-align: center; align-items: center; }
        .landing-tier-price { justify-content: center; }
        .landing-tiers-grid:has(> .landing-tier-card:only-child) { grid-template-columns: minmax(280px, 400px); justify-content: center; }
        @media (max-width: 640px) { .landing-hero-title { font-size: 2.5rem !important; } .landing-hero-sub { font-size: 1.05rem !important; max-width: 520px !important; } }
        @media (max-width: 1024px) and (min-width: 641px) { .landing-features-grid { grid-template-columns: repeat(2, 1fr); gap: 16px; } }
      `}</style>
      <div className="landing-page">
        <section className="landing-hero">
          <div className="landing-hero-glow" aria-hidden="true" />
          <h1 className="landing-hero-title">{t("landing.hero.title_line1")}<span className="landing-hero-gradient">{t("landing.hero.title_line2")}</span></h1>
          <p className="landing-hero-sub">{t("landing.hero.subtitle")}</p>
          <section className="landing-showcase"><div className="landing-showcase-frame"><img src="/chat-screenshot.png" alt={t("landing.showcase.alt")} /></div></section>
          <div className="landing-hero-actions"><button className="btn landing-btn-primary" onClick={goRegister}><UserStar size={18} strokeWidth={2.2} />{t("landing.hero.cta_primary")}</button><button className="btn landing-btn-outline" onClick={() => navigate("/login")}>{t("landing.hero.cta_signin")}</button></div>
        </section>
        <section className="landing-features"><h2 className="landing-section-title">{t("landing.features.heading")}</h2><p className="landing-section-sub">{t("landing.features.subheading")}</p><div className="landing-features-grid">{FEATURES.map(({ icon: Icon, hue, title, desc }) => <div key={title} className="landing-feature-card"><div className="landing-feature-icon" data-hue={hue}><Icon size={24} strokeWidth={1.8} /></div><h3 className="landing-feature-title">{title}</h3><p className="landing-feature-desc">{desc}</p></div>)}</div></section>
        <section className="landing-vibes"><h2 className="landing-section-title">{t("landing.vibes.heading")}</h2><p className="landing-section-sub">{t("landing.vibes.subheading")}</p><div className="landing-vibes-grid">{CREATOR_DIMENSIONS.map(({ icon: Icon, hue, title, desc }) => <div key={title} className="landing-feature-card"><div className="landing-feature-icon" data-hue={hue}><Icon size={24} strokeWidth={1.8} /></div><h3 className="landing-feature-title">{title}</h3><p className="landing-feature-desc">{desc}</p></div>)}</div></section>
        <section className="landing-tiers"><h2 className="landing-section-title">{t("landing.tiers.heading")}</h2><p className="landing-section-sub">{t("landing.tiers.subheading")}</p><div className="landing-tiers-grid">{TIERS.map((tier) => <div key={tier.name} className={"landing-tier-card" + (tier.highlight ? " landing-tier-highlight" : "")}>{tier.badge && <span className="landing-tier-badge">{tier.badge}</span>}<h3 className="landing-tier-name">{tier.name}</h3><div className="landing-tier-price"><span className="landing-tier-amount">{tier.price}</span><span className="landing-tier-interval">/{tier.period}</span></div><p className="landing-tier-cap">{tier.cap}</p><ul className="landing-tier-features">{tier.features.map((f) => <li key={f}>{f}</li>)}</ul><button className="landing-tier-cta-btn" onClick={goRegister}>{t("landing.tiers.cta")}</button></div>)}</div></section>
        <section className="landing-cta"><h2 className="landing-cta-title">{t("landing.cta.heading")}</h2><p className="landing-cta-sub">{t("landing.cta.subheading")}</p><button className="btn landing-btn-primary landing-btn-lg" onClick={goRegister}><UserStar size={20} strokeWidth={2.2} />{t("landing.cta.button")}</button></section>
      </div>
    </PublicShell>
  );
}
