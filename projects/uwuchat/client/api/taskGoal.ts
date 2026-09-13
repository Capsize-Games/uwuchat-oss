import { request } from "./client-base";

export interface Goal {
  id: number;
  title: string;
  description: string | null;
  target_date: string | null;
  status: "active" | "achieved" | "abandoned";
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  due_date: string | null;
  status: "open" | "in_progress" | "done" | "abandoned";
  goal_id: number | null;
  completed_at: string | null;
}

export interface ProductivityResponse {
  goals: Goal[];
  tasks: Task[];
}

export async function listProductivity(): Promise<ProductivityResponse> {
  return request<ProductivityResponse>(
    "GET",
    "/api/v1/uwuchat/productivity",
  );
}
