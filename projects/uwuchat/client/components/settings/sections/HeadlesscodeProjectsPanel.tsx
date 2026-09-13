import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  createHeadlesscodeProject,
  deleteHeadlesscodeProject,
  listHeadlesscodeProjects,
  updateHeadlesscodeProject,
  type HeadlesscodeProject,
} from "../../../api/headlesscode";
import styles from "./HeadlesscodeProjectsPanel.module.css";

const EMPTY_FORM = { name: "", repo_path: "", workspace_root: "" };

interface ProjectForm {
  name: string;
  repo_path: string;
  workspace_root: string;
}

function ProjectFormFields({
  value,
  onChange,
}: {
  value: ProjectForm;
  onChange: (next: ProjectForm) => void;
}) {
  return (
    <>
      <input
        className={styles.input}
        value={value.name}
        onChange={(e) => onChange({ ...value, name: e.target.value })}
        placeholder="Project name"
        aria-label="Project name"
        required
      />
      <input
        className={styles.input}
        value={value.repo_path}
        onChange={(e) => onChange({ ...value, repo_path: e.target.value })}
        placeholder="Repo path (e.g. /srv/acme)"
        aria-label="Repo path"
        required
      />
      <input
        className={styles.input}
        value={value.workspace_root}
        onChange={(e) => onChange({ ...value, workspace_root: e.target.value })}
        placeholder="Workspace root"
        aria-label="Workspace root"
        required
      />
    </>
  );
}

export default function HeadlesscodeProjectsPanel() {
  const [projects, setProjects] = useState<HeadlesscodeProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<ProjectForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<ProjectForm>(EMPTY_FORM);

  // State is only ever set from async callbacks here — never
  // synchronously — so the initial effect-driven refresh() stays
  // lint-clean under react-hooks/set-state-in-effect. `loading`
  // starts true and flips false on the first completion.
  const refresh = useCallback(() => {
    listHeadlesscodeProjects()
      .then((resp) => {
        setProjects(resp.projects);
        setError(null);
      })
      .catch(() => setError("Failed to load projects."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCreate = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (saving) return;
      setSaving(true);
      setError(null);
      try {
        await createHeadlesscodeProject(form);
        setForm(EMPTY_FORM);
        refresh();
      } catch {
        setError("Could not create the project.");
      } finally {
        setSaving(false);
      }
    },
    [form, saving, refresh],
  );

  const handleUpdate = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (editingId == null || saving) return;
      setSaving(true);
      setError(null);
      try {
        await updateHeadlesscodeProject(editingId, editForm);
        setEditingId(null);
        refresh();
      } catch {
        setError("Could not update the project.");
      } finally {
        setSaving(false);
      }
    },
    [editingId, editForm, saving, refresh],
  );

  const handleDelete = useCallback(
    async (project: HeadlesscodeProject) => {
      if (!window.confirm(`Remove "${project.name}" from the registry?`)) {
        return;
      }
      setError(null);
      try {
        await deleteHeadlesscodeProject(project.id);
        refresh();
      } catch {
        setError("Could not delete the project.");
      }
    },
    [refresh],
  );

  const startEdit = useCallback(
    (project: HeadlesscodeProject) => {
      setEditingId(project.id);
      setEditForm({
        name: project.name,
        repo_path: project.repo_path,
        workspace_root: project.workspace_root,
      });
    },
    [],
  );

  return (
    <div className={styles.wrap}>
      <h6 className="text-theme-secondary">Headlesscode projects</h6>
      <p className={styles.hint}>
        Registered repos the UwU can launch headlesscode sessions on. The
        UwU can only work on projects listed here.
      </p>

      {error && <div className={styles.error}>{error}</div>}
      {loading ? (
        <div className={styles.state}>Loading projects…</div>
      ) : projects.length === 0 ? (
        <div className={styles.state}>
          No projects registered yet. Add one below.
        </div>
      ) : (
        <div className={styles.list}>
          {projects.map((project) =>
            editingId === project.id ? (
              <form key={project.id} className={styles.row} onSubmit={handleUpdate}>
                <ProjectFormFields value={editForm} onChange={setEditForm} />
                <div className={styles.actions}>
                  <button type="submit" className={styles.primaryBtn} disabled={saving}>
                    Save
                  </button>
                  <button
                    type="button"
                    className={styles.ghostBtn}
                    onClick={() => setEditingId(null)}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div key={project.id} className={styles.row}>
                <div className={styles.rowText}>
                  <span className={styles.rowName}>{project.name}</span>
                  <span className={styles.rowPath}>{project.repo_path}</span>
                  <span className={styles.rowPath}>{project.workspace_root}</span>
                </div>
                <div className={styles.actions}>
                  <button type="button" className={styles.ghostBtn} onClick={() => startEdit(project)}>
                    Edit
                  </button>
                  <button type="button" className={styles.dangerBtn} onClick={() => handleDelete(project)}>
                    Delete
                  </button>
                </div>
              </div>
            ),
          )}
        </div>
      )}

      <form className={styles.addForm} onSubmit={handleCreate}>
        <ProjectFormFields value={form} onChange={setForm} />
        <button type="submit" className={styles.primaryBtn} disabled={saving}>
          {saving ? "Saving…" : "Add project"}
        </button>
      </form>
    </div>
  );
}
