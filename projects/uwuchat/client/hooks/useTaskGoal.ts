import { useState, useEffect, useCallback } from "react";
import {
  listProductivity,
  type Goal,
  type Task,
} from "../api/taskGoal";

interface UseTaskGoalResult {
  goals: Goal[];
  tasks: Task[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useTaskGoal(): UseTaskGoalResult {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listProductivity();
      setGoals(data.goals);
      setTasks(data.tasks);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load tasks & goals",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { goals, tasks, loading, error, refresh: fetch };
}
