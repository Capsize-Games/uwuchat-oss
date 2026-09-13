import React, { useCallback, useState } from "react";
import type { BlueskyPost, BlueskyStatus } from "../../../api/bluesky";
import { connectBluesky } from "../../../api/bluesky";
import styles from "./PanelBlueskyTab.module.css";

interface PanelBlueskyTabProps {
  posts: BlueskyPost[];
  postsLoading: boolean;
  status: BlueskyStatus | null;
  loading: boolean;
  userId: number | null;
  onRefresh: () => void;
}

export default function PanelBlueskyTab({
  posts,
  postsLoading,
  status,
  loading,
  userId,
  onRefresh,
}: PanelBlueskyTabProps) {
  const [connecting, setConnecting] = useState(false);
  const [showingForm, setShowingForm] = useState(false);
  const [handle, setHandle] = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [connectError, setConnectError] = useState<string | null>(null);

  const handleConnect = useCallback(async () => {
    if (!userId || !handle.trim() || !appPassword.trim()) return;
    setConnecting(true);
    setConnectError(null);
    try {
      await connectBluesky(userId, handle.trim(), appPassword.trim());
      setShowingForm(false);
      setHandle("");
      setAppPassword("");
      setTimeout(() => onRefresh(), 100);
    } catch (err) {
      setConnectError(
        err instanceof Error ? err.message : "Connection failed",
      );
    } finally {
      setConnecting(false);
    }
  }, [userId, handle, appPassword, onRefresh]);

  if (loading) {
    return <div className={styles.loadingBox}>Loading…</div>;
  }

  if (!status?.connected) {
    if (showingForm) {
      return (
        <div className={styles.connectCard}>
          <div className={styles.connectTitle}>
            Connect Bluesky
          </div>
          <div className={styles.connectDesc}>
            Create an app password at{" "}
            <a
              href="https://bsky.social/settings/app-passwords"
              target="_blank"
              rel="noopener noreferrer"
              className={styles.connectLink}
            >
              bsky.social/settings/app-passwords
            </a>
          </div>
          <input
            type="text"
            placeholder="handle (e.g. user.bsky.social)"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            className={styles.connectInput}
          />
          <input
            type="password"
            placeholder="app password (xxxx-xxxx-xxxx-xxxx)"
            value={appPassword}
            onChange={(e) => setAppPassword(e.target.value)}
            className={styles.connectInput}
          />
          {connectError && (
            <div className={styles.connectError}>
              {connectError}
            </div>
          )}
          <div className={styles.connectActions}>
            <button
              onClick={handleConnect}
              disabled={connecting || !handle.trim() || !appPassword.trim()}
              className={styles.connectBtn}
              // eslint-disable-next-line no-restricted-syntax -- state-driven conditional style
              style={{ opacity: connecting ? 0.7 : 1 }}
            >
              {connecting ? "Connecting…" : "Connect"}
            </button>
            <button
              onClick={() => { setShowingForm(false); setConnectError(null); }}
              className={styles.cancelBtn}
            >
              Cancel
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className={styles.welcomeCard}>
        <div className={styles.welcomeIcon}>{"🦋"}</div>
        <div className={styles.welcomeText}>
          Connect your Bluesky account to show your recent posts.
        </div>
        <button
          onClick={() => setShowingForm(true)}
          className={styles.primaryBtn}
        >
          Connect Bluesky
        </button>
      </div>
    );
  }

  if (postsLoading) {
    return <div className={styles.loadingBox}>Loading posts…</div>;
  }

  if (posts.length === 0) {
    return (
      <div className={styles.welcomeCard}>
        <div className={styles.welcomeIcon}>{"🦋"}</div>
        <div className={styles.welcomeText}>
          No posts found.
        </div>
      </div>
    );
  }

  return (
    <div className={styles.postList}>
      {posts.map((post) => (
        <div key={post.cid} className={styles.postCard}>
          <div className={styles.postText}>
            {post.text}
          </div>
          {post.embed?.images?.map((img, i) => (
            <img
              key={i}
              src={img.thumb}
              alt={img.alt}
              className={styles.postImg}
              loading="lazy"
            />
          ))}
          <div className={styles.postMeta}>
            <span>♥ {post.likeCount}</span>
            <span>♺ {post.repostCount}</span>
            <span>💬 {post.replyCount}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
