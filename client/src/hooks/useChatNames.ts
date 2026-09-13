import { useState, useEffect } from "react";
import { getSingleton, queryFirstResource } from "../api/client";

/**
 * Load the bot display name (from Chatbot.botname), user display name
 * (from User.display_name falling back to User.username), and user
 * avatar image (from User.avatar_image) and expose them reactively.
 *
 * Pass an optional `chatbotId` to re-fetch the bot name whenever the
 * selected chatbot changes (e.g. when switching UwUs in UwUchat).
 *
 * Returns fallbacks ("Computer" / "You" / null) while loading or on error
 * so the chat UI never shows blank labels.
 */
export function useChatNames(chatbotId?: number | null) {
  const [botName, setBotName] = useState("Computer");
  const [botEmoji, setBotEmoji] = useState("🤖");
  const [userName, setUserName] = useState("You");
  const [avatarImage, setAvatarImage] = useState<string | null>(null);
  const [isSystemBot, setIsSystemBot] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        // Query by id when a specific chatbot is selected, otherwise fall
        // back to the globally-current chatbot.  Using the id avoids a race
        // where getUwuSession(chatbotId) has not yet marked the new chatbot
        // as current on the server.
        const chatbotFilter: Record<string, unknown> =
          chatbotId != null ? { id: chatbotId } : { current: true };
        const [user, chatbot] = await Promise.all([
          getSingleton("User").catch(() => null),
          queryFirstResource("Chatbot", chatbotFilter).catch(() => null),
        ]);

        if (cancelled) return;

        if (user?.display_name) {
          setUserName(String(user.display_name));
        } else if (user?.username) {
          setUserName(String(user.username));
        }
        if (user?.avatar_image) {
          setAvatarImage(String(user.avatar_image));
        }
        if (chatbot?.record?.botname) {
          setBotName(String(chatbot.record.botname));
        }
        if (chatbot?.record?.avatar_emoji) {
          setBotEmoji(String(chatbot.record.avatar_emoji));
        }
        setIsSystemBot(chatbot?.record?.is_system_bot === true);
      } catch {
        // keep defaults
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [chatbotId]);

  return { botName, botEmoji, userName, avatarImage, isSystemBot };
}
