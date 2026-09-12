import { request } from "./client-base";

export interface CalendarEvent {
  id: number;
  title: string;
  description: string | null;
  starts_at: string;
  ends_at: string | null;
  all_day: boolean;
  reminder_minutes: number | null;
  chatbot_id: number | null;
}

export interface CalendarListResponse {
  events: CalendarEvent[];
}

export async function listCalendarEvents(
  fromDate: string,
  toDate: string,
  chatbotId?: number | null,
): Promise<CalendarListResponse> {
  let url = (
    "/api/v1/uwuchat/calendar"
    + "?from_date=" + encodeURIComponent(fromDate)
    + "&to_date=" + encodeURIComponent(toDate)
  );
  if (chatbotId != null) {
    url += "&chatbot_id=" + chatbotId;
  }
  return request<CalendarListResponse>("GET", url);
}
