import { useEffect, useState } from "react";
import { getChatbotItems, getChatbotCards, Item, Card } from "../api/economy";

interface InventoryState {
  items: Item[];
  cards: Card[];
  loading: boolean;
  error: string | null;
}

export function useChatbotInventory(chatbotId: number | null): InventoryState {
  const [items, setItems] = useState<Item[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chatbotId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([getChatbotItems(chatbotId), getChatbotCards(chatbotId)])
      .then(([fetchedItems, fetchedCards]) => {
        if (cancelled) return;
        setItems(fetchedItems);
        setCards(fetchedCards);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message ?? "Failed to load inventory");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [chatbotId]);

  return { items, cards, loading, error };
}
