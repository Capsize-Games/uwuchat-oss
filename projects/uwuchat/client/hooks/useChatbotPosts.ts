import { useState, useEffect } from "react";
import { getChatbotPosts, type Post } from "../api/posts";

export function useChatbotPosts(chatbotId: number | null): {
  posts: Post[];
  loading: boolean;
  error: string | null;
} {
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (chatbotId === null) {
      setPosts([]);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    getChatbotPosts(chatbotId)
      .then((data) => {
        if (!cancelled) setPosts(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load posts");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [chatbotId]);

  return { posts, loading, error };
}
