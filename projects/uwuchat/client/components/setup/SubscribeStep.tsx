import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { redeemPromoCode } from "../../../../extensions/auth/client/promotion-api";
import styles from "./SubscribeStep.module.css";

interface Plan { id: string; name: string; price: string; period: string; cap: string; badge?: string; intro?: boolean; }

const PLANS: Plan[] = [
  { id: "trial", name: "Try UwUchat", price: "$5", period: "3 days", cap: "30 messages · 15/day", intro: true, badge: "Best way to start" },
  { id: "companion", name: "Companion", price: "$15", period: "mo", cap: "400 msg/mo · 20/day", badge: "Most popular" },
  { id: "devoted", name: "Devoted", price: "$40", period: "mo", cap: "1,500 msg/mo · 65/day" },
];

interface SubscribeStepProps { onSubscribe: (tier: string) => Promise<void>; onSkip: () => void; }

export function SubscribeStep({ onSubscribe, onSkip }: SubscribeStepProps) {
  const { t } = useTranslation();
  const { accessToken } = useAuth();
  const [loading, setLoading] = useState<string | null>(null);
  const [promoCode, setPromoCode] = useState("");
  const [promoLoading, setPromoLoading] = useState(false);
  const [promoError, setPromoError] = useState<string | null>(null);
  const [promoSuccess, setPromoSuccess] = useState<string | null>(null);

  async function handlePick(tier: string) { setLoading(tier); await onSubscribe(tier); }

  async function handlePromoRedeem(e: React.FormEvent) {
    e.preventDefault();
    const clean = promoCode.trim().toUpperCase(); if (!clean || !accessToken) return;
    setPromoLoading(true); setPromoError(null); setPromoSuccess(null);
    try {
      const result = await redeemPromoCode(clean, accessToken);
      setPromoSuccess(result.tier ? t("settings.promo.redeemed_tier", { tier: result.tier }) : t("settings.promo.redeemed"));
      setPromoCode("");
      if (result.tier) await onSubscribe(result.tier);
    } catch (e) { setPromoError(e instanceof Error ? e.message : t("settings.promo.error")); }
    finally { setPromoLoading(false); }
  }

  return (
    <div className={styles.wrap}>
      {accessToken && (
        <form onSubmit={handlePromoRedeem} className={styles.promoForm}>
          <input type="text" value={promoCode} onChange={(e) => setPromoCode(e.target.value)}
            placeholder={t("settings.promo.placeholder")} disabled={promoLoading} autoComplete="off" className={styles.promoInput} />
          <button type="submit" disabled={promoLoading || !promoCode.trim()} className={styles.promoBtn}>
            {promoLoading ? "…" : t("settings.promo.redeem")}
          </button>
          {promoError && <div className={styles.promoError}>{promoError}</div>}
          {promoSuccess && <div className={styles.promoSuccess}>{promoSuccess}</div>}
        </form>
      )}
      <p className={styles.tagline}>{t("subscribe.tagline")}</p>
      {PLANS.map((plan) => {
        const isIntro = plan.intro;
        const isPopular = !!plan.badge && !isIntro;
        const planCls = loading && loading !== plan.id ? styles.planBtnDimmed
          : isIntro ? styles.planBtnHighlight : isPopular ? styles.planBtnPopular : styles.planBtnDefault;
        const badgeCls = isIntro ? styles.planBadgeIntro : styles.planBadgePopular;
        return (
          <button key={plan.id} disabled={loading !== null} onClick={() => handlePick(plan.id)} className={planCls}>
            <div>
              <div className={styles.planNameRow}>
                <span className={styles.planName}>{plan.name}</span>
                {plan.badge && <span className={badgeCls}>{plan.badge}</span>}
              </div>
              <div className={styles.planCap}>{plan.cap}</div>
            </div>
            <div className={styles.planPrice}>
              {loading === plan.id ? "…" : <>{plan.price}<span className={styles.planPeriod}>{"/" + plan.period}</span></>}
            </div>
          </button>
        );
      })}
      <button onClick={onSkip} className={styles.skipBtn}>{t("subscribe.maybe_later")}</button>
    </div>
  );
}
