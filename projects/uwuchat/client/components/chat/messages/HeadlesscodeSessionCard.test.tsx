import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mocks = vi.hoisted(() => ({
  getDetail: vi.fn(),
  injectMessage: vi.fn(),
  eventCallback: null as ((event: string, data: unknown) => void) | null,
}));

vi.mock("../../../api/headlesscode", () => ({
  getHeadlesscodeSessionDetail: mocks.getDetail,
  injectHeadlesscodeMessage: mocks.injectMessage,
}));

vi.mock("@/features/events/useEventBus", () => ({
  useEventBus: (_events: string[], cb: (event: string, data: unknown) => void) => {
    mocks.eventCallback = cb;
  },
}));

import HeadlesscodeSessionCard from "./HeadlesscodeSessionCard";

const SESSION_ID = "hc-sess-42";

function renderCard() {
  return render(
    <HeadlesscodeSessionCard
      sessionId={SESSION_ID}
      projectName="acme-web"
      status="running"
      taskDescription="fix the login bug"
    />,
  );
}

describe("HeadlesscodeSessionCard", () => {
  beforeEach(() => {
    mocks.getDetail.mockReset();
    mocks.injectMessage.mockReset();
    mocks.eventCallback = null;
    mocks.getDetail.mockResolvedValue({
      session: {
        headlesscode_session_id: SESSION_ID,
        project_id: 1,
        project_name: "acme-web",
        status: "running",
        mode: "code",
        created_at: "2026-08-05T10:00:00Z",
        updated_at: "2026-08-05T10:00:00Z",
      },
      events: [],
    });
  });

  it("renders the header with project name, task and a running pill", async () => {
    renderCard();
    expect(screen.getByText("acme-web")).toBeTruthy();
    expect(screen.getByText("fix the login bug")).toBeTruthy();
    expect(screen.getByText("Running")).toBeTruthy();
  });

  it("shows the durable transcript once expanded", async () => {
    mocks.getDetail.mockResolvedValue({
      session: {
        headlesscode_session_id: SESSION_ID,
        project_id: 1,
        project_name: "acme-web",
        status: "running",
        mode: null,
      },
      events: [
        {
          id: 1,
          chat_block_kind: "turn",
          raw_event: { chat_block_kind: "turn", content: "Starting work" },
          created_at: "2026-08-05T10:00:00Z",
        },
      ],
    });
    const user = userEvent.setup();
    renderCard();
    const header = screen.getByRole("button", { name: /acme-web/ });
    await user.click(header);
    expect(await screen.findByText(/Starting work/)).toBeTruthy();
  });

  it("disables injection until the message_injected relay event confirms it", async () => {
    const user = userEvent.setup();
    mocks.injectMessage.mockResolvedValue({ ok: true, session_id: SESSION_ID });
    renderCard();

    const header = screen.getByRole("button", { name: /acme-web/ });
    await user.click(header);

    const input = screen.getByLabelText(
      "Send a message to the coding agent",
    ) as HTMLInputElement;
    await user.type(input, "keep going");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(mocks.injectMessage).toHaveBeenCalledWith(SESSION_ID, "keep going");
    // Sending -> pending: the affordance is disabled until confirmed.
    expect(input.disabled).toBe(true);

    // The relay pushes the message_injected event for this session id.
    mocks.eventCallback?.("headlesscode_session", {
      session_id: SESSION_ID,
      event_type: "message_injected",
      content: "keep going",
    });

    await vi.waitFor(() => {
      expect((screen.getByLabelText(
        "Send a message to the coding agent",
      ) as HTMLInputElement).disabled).toBe(false);
    });
  });
});
