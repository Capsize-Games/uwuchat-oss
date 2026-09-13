import { useState, useEffect, useCallback, useRef } from "react";
import {
  getBlueskyStatus,
  getBlueskyPosts,
  type BlueskyPost,
  type BlueskyStatus,
} from "../api/bluesky";

interface UseBlueskyProfileResult {
  status: BlueskyStatus | null;
  posts: BlueskyPost[];
  postsLoading: boolean;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * Hook to fetch a user's Bluesky connection status and posts.
 *
 * When connected (via OAuth), fetches posts through the server proxy.
 * Falls back to public API if a manual handle exists in social links.
 */
export function useBlueskyProfile(
  userId: number | null,
): UseBlueskyProfileResult {
  const [status, setStatus] = useState<BlueskyStatus | null>(null);
  const [posts, setPosts] = useState<BlueskyPost[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetchStatus = useCallback(async () => {
    if (userId === null) return;
    try {
      const s = await getBlueskyStatus(userId);
      if (!mountedRef.current) return;
      setStatus(s);
      setError(null);

      if (s.connected && s.handle) {
        setPostsLoading(true);
        try {
          const res = await getBlueskyPosts(userId);
          if (!mountedRef.current) return;
          setPosts(res.posts ?? []);
        } catch {
          setPosts([]);
        } finally {
          if (mountedRef.current) setPostsLoading(false);
        }
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(
        err instanceof Error ? err.message : "Failed to fetch status",
      );
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [userId]);

  // Listen for bluesky:disconnected events
  useEffect(() => {
    const handler = () => {
      if (userId !== null) {
        setLoading(true);
        setError(null);
        setPosts([]);
        setStatus(null);
        fetchStatus();
      }
    };
    window.addEventListener("bluesky:disconnected", handler);
    return () =>
      window.removeEventListener("bluesky:disconnected", handler);
  }, [userId, fetchStatus]);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    setPosts([]);
    setStatus(null);
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    mountedRef.current = true;
    if (userId === null) {
      setStatus(null);
      setPosts([]);
      setLoading(false);
      return;
    }
    refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [userId, refresh]);

  return { status, posts, postsLoading, loading, error, refresh };
}
