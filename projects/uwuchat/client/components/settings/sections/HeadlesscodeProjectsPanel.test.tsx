import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("../../../api/headlesscode", () => ({
  listHeadlesscodeProjects: mocks.list,
  createHeadlesscodeProject: mocks.create,
  updateHeadlesscodeProject: mocks.update,
  deleteHeadlesscodeProject: mocks.remove,
}));

import HeadlesscodeProjectsPanel from "./HeadlesscodeProjectsPanel";

const PROJECT = {
  id: 1,
  name: "acme-web",
  repo_path: "/srv/acme",
  workspace_root: "/srv/acme",
  created_at: "2026-08-05T10:00:00Z",
};

describe("HeadlesscodeProjectsPanel", () => {
  beforeEach(() => {
    mocks.list.mockReset();
    mocks.create.mockReset();
    mocks.update.mockReset();
    mocks.remove.mockReset();
    mocks.list.mockResolvedValue({ projects: [PROJECT] });
    mocks.create.mockResolvedValue({ ...PROJECT });
    mocks.remove.mockResolvedValue(undefined);
  });

  it("lists the user's registered projects", async () => {
    render(<HeadlesscodeProjectsPanel />);
    expect(await screen.findByText("acme-web")).toBeTruthy();
    // repo_path and workspace_root both render for each project row.
    expect(screen.getAllByText("/srv/acme").length).toBeGreaterThanOrEqual(2);
  });

  it("registers a new project through the form", async () => {
    const user = userEvent.setup();
    render(<HeadlesscodeProjectsPanel />);
    await screen.findByText("acme-web");

    await user.type(screen.getByLabelText("Project name"), "acme-api");
    await user.type(screen.getByLabelText("Repo path"), "/srv/acme-api");
    await user.type(screen.getByLabelText("Workspace root"), "/srv/acme-api");
    await user.click(screen.getByRole("button", { name: "Add project" }));

    await waitFor(() => {
      expect(mocks.create).toHaveBeenCalledWith({
        name: "acme-api",
        repo_path: "/srv/acme-api",
        workspace_root: "/srv/acme-api",
      });
    });
  });

  it("soft-deletes a project after the confirm dialog", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi
      .spyOn(window, "confirm")
      .mockReturnValue(true);
    render(<HeadlesscodeProjectsPanel />);
    await screen.findByText("acme-web");

    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(mocks.remove).toHaveBeenCalledWith(1);
    });
    confirmSpy.mockRestore();
  });
});
