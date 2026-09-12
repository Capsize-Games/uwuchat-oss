import { request } from "./client-base";

export interface JournalEntry {
  id: number;
  entry_date: string;
  body: string;
  created_at: string;
}

export interface JournalListResponse {
  entries: JournalEntry[];
  total: number;
}

export async function listJournalEntries(
  limit = 30,
  offset = 0,
): Promise<JournalListResponse> {
  return request<JournalListResponse>(
    "GET",
    `/api/v1/uwuchat/journal?limit=${limit}&offset=${offset}`,
  );
}
