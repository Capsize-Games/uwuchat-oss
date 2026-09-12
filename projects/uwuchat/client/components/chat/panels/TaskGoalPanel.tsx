import { useState } from "react";
import { useTaskGoal } from "../../../hooks/useTaskGoal";
import type { Goal, Task } from "../../../api/taskGoal";
import styles from "./TaskGoalPanel.module.css";

const STATUS_COLORS: Record<string, string> = {
  active: "#4c9aff",
  achieved: "#4caf50",
  abandoned: "#9e9e9e",
};

const TASK_STATUS_COLORS: Record<string, string> = {
  open: "#ff9800",
  in_progress: "#4c9aff",
  done: "#4caf50",
  abandoned: "#9e9e9e",
};

function StatusBadge({ label, color }: { label: string; color: string }) {
  return (
    // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
    <span className={styles.statusBadge} style={{ color }}>
      {label}
    </span>
  );
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr + "T12:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return dateStr;
  }
}

function GoalSection({
  goal,
  tasks,
  children,
}: {
  goal: Goal;
  tasks: Task[];
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div>
      <div
        onClick={() => setOpen(!open)}
        className={styles.goalHeader}
      >
        <span className={styles.goalArrow}>{open ? "▾" : "▸"}</span>
        {goal.title}
        <StatusBadge label={goal.status} color={STATUS_COLORS[goal.status] || "#888"} />
        {goal.target_date && (
          <span className={styles.goalDate}>by {formatDate(goal.target_date)}</span>
        )}
      </div>
      {open && <div>{children}</div>}
    </div>
  );
}

function TaskRow({ task }: { task: Task }) {
  const statusLabel =
    task.status === "done" ? "✓ done"
    : task.status === "in_progress" ? "↻ in progress"
    : task.status === "open" ? "○ open"
    : "✕ abandoned";

  return (
    <div className={styles.taskRow}>
      <span className={styles.taskTitle}>{task.title}</span>
      <StatusBadge label={statusLabel} color={TASK_STATUS_COLORS[task.status] || "#888"} />
      {task.due_date && (
        <span className={styles.taskDate}>{formatDate(task.due_date)}</span>
      )}
    </div>
  );
}

export function TaskGoalPanel() {
  const { goals, tasks, loading, error } = useTaskGoal();

  if (loading) return <div className={styles.loadingState}>Loading tasks & goals...</div>;
  if (error) return <div className={styles.errorState}>{error}</div>;
  if (goals.length === 0 && tasks.length === 0) {
    return (
      <div className={styles.emptyState}>
        No tasks or goals yet. Tell your UwU what you're working on and they'll help you keep track!
      </div>
    );
  }

  const uncategorized = tasks.filter((t) => t.goal_id === null);
  const tasksByGoal = new Map<number, Task[]>();
  for (const task of tasks) {
    if (task.goal_id !== null) {
      const list = tasksByGoal.get(task.goal_id);
      if (list) list.push(task);
      else tasksByGoal.set(task.goal_id, [task]);
    }
  }

  return (
    <div className={styles.panel}>
      {goals.map((goal) => (
        <GoalSection key={goal.id} goal={goal} tasks={tasksByGoal.get(goal.id) || []}>
          {(tasksByGoal.get(goal.id) || []).map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
          {(!tasksByGoal.get(goal.id) || tasksByGoal.get(goal.id)!.length === 0) && (
            <div className={styles.emptyTasks}>No tasks yet</div>
          )}
        </GoalSection>
      ))}
      {uncategorized.length > 0 && (
        <div>
          <div className={styles.uncatHeader}>Uncategorized</div>
          {uncategorized.map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
        </div>
      )}
    </div>
  );
}
