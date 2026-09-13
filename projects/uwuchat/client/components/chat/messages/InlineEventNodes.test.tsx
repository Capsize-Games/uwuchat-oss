/**
 * Test for InlineEventNodes ceiling-fallback fix (Plan 2, Cause 1).
 *
 * When beforeTimestamp is undefined (last message, no following
 * assistant message), the filter must cap at "now" instead of leaving
 * the upper edge unbounded — otherwise events from hours/days later
 * get misattributed to the wrong message.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { InlineEventNodes } from "./InlineEventNodes";
import type { ConversationEvent } from "../../../api/admin";

function makeEvent(
  eventId: string,
  createdAt: string,
  eventType = "message_append",
): ConversationEvent {
  return {
    event_id: eventId,
    event_type: eventType,
    actor: "bot",
    payload: {},
    created_at: createdAt,
    sequence_num: null,
    conversation_id: null,
    session_id: null,
  };
}

const MS_PER_MINUTE = 60_000;

describe("InlineEventNodes ceiling fallback", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("includes events within the afterTimestamp → now window", () => {
    const now = new Date("2026-07-27T08:00:00Z");
    vi.setSystemTime(now);

    const after = new Date(now.getTime() - 10 * MS_PER_MINUTE).toISOString();
    const events = [
      makeEvent("e1", new Date(now.getTime() - 5 * MS_PER_MINUTE).toISOString()),
    ];

    render(<InlineEventNodes events={events} afterTimestamp={after} />);
    expect(screen.getByText("Events · 1")).toBeDefined();
  });

  it("excludes events beyond the current time when beforeTimestamp is undefined", () => {
    const now = new Date("2026-07-27T08:00:00Z");
    vi.setSystemTime(now);

    const after = new Date(now.getTime() - 120 * MS_PER_MINUTE).toISOString();
    const events = [
      makeEvent("e1", new Date(now.getTime() - 60 * MS_PER_MINUTE).toISOString()),
      // This event is 10 minutes in the future — should be excluded
      makeEvent("e2", new Date(now.getTime() + 10 * MS_PER_MINUTE).toISOString()),
      // This event is 2 hours in the future — should be excluded
      makeEvent("e3", new Date(now.getTime() + 120 * MS_PER_MINUTE).toISOString()),
    ];

    const { container } = render(
      <InlineEventNodes events={events} afterTimestamp={after} />,
    );

    // Only the past event should be rendered — events in the future
    // must be excluded by the ceiling-fallback.
    const rows = container.querySelectorAll('[class*="eventRow"]');
    expect(rows.length).toBe(1);
  });

  it("honors beforeTimestamp when provided (normal two-message case)", () => {
    const after = new Date("2026-07-27T07:30:00Z").toISOString();
    const before = new Date("2026-07-27T07:35:00Z").toISOString();
    const events = [
      makeEvent("e1", new Date("2026-07-27T07:32:00Z").toISOString()),
      makeEvent("e2", new Date("2026-07-27T07:38:00Z").toISOString()),
    ];

    const { container } = render(
      <InlineEventNodes
        events={events}
        afterTimestamp={after}
        beforeTimestamp={before}
      />,
    );

    const rows = container.querySelectorAll('[class*="eventRow"]');
    expect(rows.length).toBe(1);
  });
});
