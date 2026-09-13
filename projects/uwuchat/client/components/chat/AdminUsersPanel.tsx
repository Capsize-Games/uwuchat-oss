/**
 * Admin users panel — rendered in the right sidebar of ChatView.
 * Lists accounts with search, create, suspend, reactivate, delete,
 * and account controls.
 */
import { useEffect, useState, useCallback } from "react";
import {
  BadgeAlert,
  BadgeCheck,
  Ban,
  CheckCircle,
  ShieldAlert,
  ShieldCheck,
  ShieldUser,
  Trash2,
  User,
} from "lucide-react";
import {
  type AdminAccount,
  listAccounts,
  createAccount,
  deleteAccount,
  suspendAccount,
  reactivateAccount,
  type AdminCreateAccount,
} from "@extensions/auth/client/admin-api";
import styles from "./AdminUsersPanel.module.css";

const PAGE_SIZE = 30;

/** 14×14 icon indicator with tooltip — no background, just color. */
function IconBadge({
  icon,
  color,
  title,
}: {
  icon: React.ReactNode;
  color: string;
  title: string;
}) {
  return (
    <span
      title={title}
      className={styles.iconBadge}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{ color }}
    >
      {icon}
    </span>
  );
}

export default function AdminUsersPanel() {
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);


  const load = useCallback(async (off: number, q?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAccounts({ limit: PAGE_SIZE, offset: off, q });
      setAccounts(data.accounts);
      setTotal(data.total);
      setOffset(data.offset);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  // Defer the initial load to a microtask so setState is not called
  // synchronously in the effect body (react-hooks/set-state-in-effect).
  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) load(0);
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    load(0, search || undefined);
  };

  const [showCreate, setShowCreate] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createSuperuser, setCreateSuperuser] = useState(false);
  const [createVerified, setCreateVerified] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const doDelete = async (accountId: number) => {
    setBusyId(accountId);
    setConfirmDeleteId(null);
    try {
      await deleteAccount(accountId);
      setAccounts((prev) => prev.filter((a) => a.id !== accountId));
      setTotal((t) => Math.max(0, t - 1));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusyId(null);
    }
  };

  const doSuspend = async (accountId: number) => {
    setBusyId(accountId);
    try {
      const updated = await suspendAccount(accountId);
      setAccounts((prev) =>
        prev.map((a) => (a.id === accountId ? { ...a, ...updated } : a)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Suspend failed");
    } finally {
      setBusyId(null);
    }
  };

  const doReactivate = async (accountId: number) => {
    setBusyId(accountId);
    try {
      const updated = await reactivateAccount(accountId);
      setAccounts((prev) =>
        prev.map((a) => (a.id === accountId ? { ...a, ...updated } : a)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reactivate failed");
    } finally {
      setBusyId(null);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateBusy(true);
    setCreateError(null);
    try {
      const body: AdminCreateAccount = {
        email: createEmail,
        password: createPassword,
        is_superuser: createSuperuser || undefined,
        is_verified: createVerified || undefined,
      };
      await createAccount(body);
      setShowCreate(false);
      setCreateEmail("");
      setCreatePassword("");
      setCreateSuperuser(false);
      setCreateVerified(false);
      load(offset, search || undefined);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create account");
    } finally {
      setCreateBusy(false);
    }
  };

  return (
    <div className={styles.wrapper}>
      {/* Search & Create */}
      <form onSubmit={handleSearch} className={styles.searchForm}>
        <div className={styles.searchRow}>
          <input
            type="text"
            placeholder="Search email or username..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={styles.searchInput}
          />
          <button
            type="submit"
            className={`${styles.btn} ${styles.btnSearch}`}
          >
            Search
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className={`${styles.btn} ${styles.btnCreate}`}
          >
            + Create
          </button>
        </div>
      </form>

      <div className={styles.resultLabel}>
        {search ? `Results for "${search}"` : `${total} accounts`}
      </div>

      {error && (
        <div className={styles.errorMsg}>{error}</div>
      )}

      {loading ? (
        <div className={styles.loadingText}>Loading...</div>
      ) : accounts.length === 0 ? (
        <div className={styles.emptyText}>No accounts found.</div>
      ) : (
        <>
          <div className={styles.accountList}>
            {accounts.map((a) => {
              const btnDisabled = busyId === a.id;
              const confirming = confirmDeleteId === a.id;
              const iconStyle = (color: string): React.CSSProperties => ({
                color,
                cursor: btnDisabled ? "default" : "pointer",
                opacity: btnDisabled ? 0.4 : 1,
              });
              return (
              <div
                key={a.id}
                className={styles.accountCard}
              >
                <div className={styles.accountHeader}>
                  <span className={styles.accountName}>
                    {a.username}
                  </span>
                  <div className={styles.accountActions}>
                    {/* Role */}
                    <IconBadge
                      icon={
                        a.is_superuser
                          ? <ShieldUser size={12} />
                          : <User size={12} />
                      }
                      color={a.is_superuser ? "#a78bfa" : "rgba(255,255,255,0.35)"}
                      title={a.is_superuser ? "Superuser" : "User"}
                    />
                    {/* Status */}
                    <IconBadge
                      icon={
                        a.is_suspended
                          ? <ShieldAlert size={12} />
                          : <ShieldCheck size={12} />
                      }
                      color={
                        a.is_suspended
                          ? "#fbbf24"
                          : a.is_active
                            ? "var(--theme-success)"
                            : "rgba(255,255,255,0.2)"
                      }
                      title={
                        a.is_suspended
                          ? "Suspended"
                          : a.is_active
                            ? "Active"
                            : "Disabled"
                      }
                    />
                    {/* Verified */}
                    <IconBadge
                      icon={
                        a.is_verified
                          ? <BadgeCheck size={12} />
                          : <BadgeAlert size={12} />
                      }
                      color={a.is_verified ? "var(--theme-success)" : "var(--bs-danger)"}
                      title={a.is_verified ? "Verified" : "Unverified"}
                    />
                    <span className={styles.actSep} />
                    {a.is_suspended ? (
                      <button
                        disabled={btnDisabled}
                        onClick={() => doReactivate(a.id)}
                        title="Reactivate account"
                        className={`${styles.actBtn} ${styles.actBtnOk}`}
                        style={iconStyle("var(--theme-success)")}
                      >
                        <CheckCircle size={12} />
                      </button>
                    ) : (
                      <button
                        disabled={btnDisabled}
                        onClick={() => doSuspend(a.id)}
                        title="Suspend account"
                        className={`${styles.actBtn} ${styles.actBtnWarn}`}
                        style={iconStyle("#fbbf24")}
                      >
                        <Ban size={12} />
                      </button>
                    )}
                    <button
                      disabled={btnDisabled}
                      onClick={() =>
                        setConfirmDeleteId(confirming ? null : a.id)
                      }
                      title={confirming ? "Cancel delete" : "Delete account"}
                      className={`${styles.actBtn} ${confirming ? "" : styles.actBtnDanger}`}
                      style={iconStyle(confirming ? "#fff" : "var(--bs-danger)")}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
                {confirming && (
                  <div className={styles.confirmDelete}>
                    <span className={styles.confirmDeleteText}>
                      Delete {a.email}?
                    </span>
                    <span className={styles.confirmDeleteActions}>
                      <button
                        onClick={() => doDelete(a.id)}
                        className={styles.confirmDeleteBtn}
                      >
                        Delete
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(null)}
                        className={styles.confirmCancelBtn}
                      >
                        Cancel
                      </button>
                    </span>
                  </div>
                )}
                <div className={styles.accountMeta}>
                  {a.email} · {a.auth_provider}
                </div>
              </div>
            )})}
          </div>

          {total > PAGE_SIZE && (
            <div className={styles.pagerRow}>
              <button
                onClick={() => load(offset - PAGE_SIZE, search || undefined)}
                disabled={offset === 0}
                className={styles.btnPager}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  color: offset === 0 ? "rgba(255,255,255,0.2)" : "var(--theme-text, #e0e0e0)",
                }}
              >
                ← Prev
              </button>
              <span className={styles.pagerLabel}>
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)}
              </span>
              <button
                onClick={() => load(offset + PAGE_SIZE, search || undefined)}
                disabled={offset + PAGE_SIZE >= total}
                className={styles.btnPager}
                // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                style={{
                  color: offset + PAGE_SIZE >= total ? "rgba(255,255,255,0.2)" : "var(--theme-text, #e0e0e0)",
                }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}

      {/* Create Account Modal */}
      {showCreate && (
        <>
          <div
            onClick={() => setShowCreate(false)}
            className={styles.modalOverlay}
          />
          <div className={`${styles.modalPanel} ${styles.modalPanelWide}`}>
            <h3 className={styles.modalTitle}>
              Create Account
            </h3>
            <form onSubmit={handleCreate}>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Email</label>
                <input
                  type="email"
                  value={createEmail}
                  onChange={(e) => setCreateEmail(e.target.value)}
                  required
                  className={styles.formInput}
                />
              </div>
              <div className={styles.formGroup}>
                <label className={styles.formLabel}>Password (min 8 chars)</label>
                <input
                  type="password"
                  value={createPassword}
                  onChange={(e) => setCreatePassword(e.target.value)}
                  required
                  minLength={8}
                  className={styles.formInput}
                />
              </div>
              <div className={styles.checkboxRow}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={createSuperuser}
                    onChange={(e) => setCreateSuperuser(e.target.checked)}
                  />
                  Superuser
                </label>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={createVerified}
                    onChange={(e) => setCreateVerified(e.target.checked)}
                  />
                  Verified
                </label>
              </div>
              {createError && (
                <div className={styles.errorMsg}>{createError}</div>
              )}
              <div className={styles.modalActions}>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className={styles.modalCancelBtn}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createBusy}
                  className={styles.modalSubmitBtn}
                >
                  {createBusy ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </div>
        </>
      )}

    </div>
  );
}
