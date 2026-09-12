import { useState, useEffect } from "react";
import { fetchBlueskyPosts, type BlueskyPost } from "../api/bluesky";

/** Fetch the 5 most recent Bluesky posts for a handle. */
export function useBlueskyPosts(
  handle: string | null | undefined,
): {
  posts: BlueskyPost[];
  loading: boolean;
} {
  const [posts, setPosts] = useState<BlueskyPost[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!handle) {
      setPosts([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchBlueskyPosts(handle).then((result) => {
      if (!cancelled) {
        setPosts(result);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [handle]);

  return { posts, loading };
}
