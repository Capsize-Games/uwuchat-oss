import { Sparkles, BrainCircuit, Globe, Shield, Heart, Infinity, Drama, Languages, Fingerprint, Mic } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { TFunction } from "i18next";

export interface Tier {
  name: string;
  price: string;
  period: string;
  cap: string;
  features: string[];
  highlight?: boolean;
  badge?: string;
}

export interface Feature {
  icon: LucideIcon;
  hue: "purple" | "blue" | "green" | "orange" | "pink" | "teal";
  title: string;
  desc: string;
}

export interface CreatorDimension {
  icon: LucideIcon;
  hue: "purple" | "blue" | "green" | "orange" | "pink" | "teal";
  title: string;
  desc: string;
}

export function getTiers(t: TFunction): Tier[] {
  return [
    {
      name: t("landing.tiers.try_it.name"),
      price: "$5",
      period: t("landing.tiers.try_it.period"),
      cap: t("landing.tiers.try_it.cap"),
      features: t("landing.tiers.try_it.features", {
        returnObjects: true,
      }) as string[],
    },
    {
      name: t("landing.tiers.starter.name"),
      price: "$9.99",
      period: t("landing.tiers.starter.period"),
      cap: t("landing.tiers.starter.cap"),
      features: t("landing.tiers.starter.features", {
        returnObjects: true,
      }) as string[],
      highlight: true,
      badge: t("landing.tiers.most_popular_badge"),
    },
    {
      name: t("landing.tiers.companion.name"),
      price: "$25",
      period: t("landing.tiers.companion.period"),
      cap: t("landing.tiers.companion.cap"),
      features: t("landing.tiers.companion.features", {
        returnObjects: true,
      }) as string[],
    },
  ];
}

export function getFeatures(t: TFunction): Feature[] {
  return [
    {
      icon: Sparkles,
      hue: "purple",
      title: t("landing.features.deep_character.title"),
      desc: t("landing.features.deep_character.desc"),
    },
    {
      icon: BrainCircuit,
      hue: "blue",
      title: t("landing.features.memory.title"),
      desc: t("landing.features.memory.desc"),
    },
    {
      icon: Globe,
      hue: "green",
      title: t("landing.features.web_browse.title"),
      desc: t("landing.features.web_browse.desc"),
    },
    {
      icon: Shield,
      hue: "pink",
      title: t("landing.features.privacy.title"),
      desc: t("landing.features.privacy.desc"),
    },
    {
      icon: Heart,
      hue: "orange",
      title: t("landing.features.moods.title"),
      desc: t("landing.features.moods.desc"),
    },
    {
      icon: Infinity,
      hue: "teal",
      title: t("landing.features.continuity.title"),
      desc: t("landing.features.continuity.desc"),
    },
  ];
}

export function getCreatorDimensions(t: TFunction): CreatorDimension[] {
  return [
    {
      icon: Drama,
      hue: "purple",
      title: t("landing.vibes.personality.title"),
      desc: t("landing.vibes.personality.desc"),
    },
    {
      icon: Languages,
      hue: "teal",
      title: t("landing.vibes.language.title"),
      desc: t("landing.vibes.language.desc"),
    },
    {
      icon: Fingerprint,
      hue: "blue",
      title: t("landing.vibes.identity.title"),
      desc: t("landing.vibes.identity.desc"),
    },
    {
      icon: Mic,
      hue: "pink",
      title: t("landing.vibes.voice.title"),
      desc: t("landing.vibes.voice.desc"),
    },
  ];
}
