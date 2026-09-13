import { request } from "./client-base";

export interface Item {
  id: number;
  name: string;
  item_type: string;
  description: string | null;
  rarity: "common" | "uncommon" | "rare" | "legendary";
  attributes: Record<string, unknown> | null;
  location_found: string | null;
  created_at: string | null;
}

export interface CardStats {
  hp: number;
  attack: number;
  defense: number;
  speed: number;
  special: string;
}

export interface Card {
  id: number;
  chatbot_id: number;
  ability_text: string | null;
  stats: CardStats | null;
  art_url: string | null;
  owned_by_chatbot_id: number | null;
  created_at: string | null;
}

export async function getChatbotItems(chatbotId: number): Promise<Item[]> {
  return request<Item[]>("GET", `/api/v1/chatbots/${chatbotId}/items`);
}

export async function getChatbotCards(chatbotId: number): Promise<Card[]> {
  return request<Card[]>("GET", `/api/v1/chatbots/${chatbotId}/cards`);
}

export async function getCard(cardId: number): Promise<Card> {
  return request<Card>("GET", `/api/v1/cards/${cardId}`);
}

