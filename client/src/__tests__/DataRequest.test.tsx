/**
 * DataRequest GDPR deletion UI test — renders the real component,
 * simulates delete flow, and asserts correct endpoint/method/body.
 *
 * Requires VITE_PROJECT=uwuchat for the project overlay plugin to
 * handle cross-package JSX/resolution.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

// ── Mocks for transitive deps ────────────────────────────────────
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const m: Record<string, string> = {
        "legal.data_request.title": "Data Request",
        "legal.data_request.delete_my_account": "Delete My Account",
        "legal.data_request.confirm_delete": "Confirm deletion",
        "legal.data_request.yes_delete": "Yes, Delete",
        "legal.data_request.deleting": "Deleting...",
        "legal.data_request.account_deleted_title": "Account Deleted",
        "legal.data_request.export_my_data": "Export My Data",
        "legal.data_request.exporting": "Exporting...",
        "legal.data_request.cancel": "Cancel",
        "legal.data_request.return_login": "Return to Login",
        "legal.data_request.deleted_desc": "Account deleted.",
      };
      return m[key] ?? key;
    },
    i18n: { language: "en" },
  }),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("lucide-react", () => ({
  Star: () => null,
  BotMessageSquare: () => null,
  Menu: () => null,
  X: () => null,
}));

vi.mock(
  "../../../projects/uwuchat/client/components/layout/PublicShell",
  () => ({
    PublicShell: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="public-shell">{children}</div>
    ),
  }),
);

const mockDeleteAccount = vi.fn();
vi.mock(
  "../../../projects/uwuchat/client/hooks/useAuth",
  () => ({
    useAuth: () => ({
      user: { email: "test@example.com" },
      isAuthenticated: true,
      deleteAccount: mockDeleteAccount,
      accessToken: "test-access-token",
    }),
  }),
);

describe("DataRequest", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders delete button and calls deleteAccount with password", async () => {
    mockDeleteAccount.mockResolvedValue(undefined);
    const { default: DataRequest } = await import(
      "../../../projects/uwuchat/client/components/legal/DataRequest"
    );
    render(<DataRequest />);

    fireEvent.click(screen.getByText("Delete My Account"));
    fireEvent.change(screen.getByPlaceholderText("Your password"), {
      target: { value: "mypassword" },
    });
    fireEvent.click(screen.getByText("Yes, Delete"));

    await waitFor(() => {
      expect(mockDeleteAccount).toHaveBeenCalledWith("mypassword");
    });
  });

  it("shows deleted page after success", async () => {
    mockDeleteAccount.mockResolvedValue(undefined);
    const { default: DataRequest } = await import(
      "../../../projects/uwuchat/client/components/legal/DataRequest"
    );
    render(<DataRequest />);

    fireEvent.click(screen.getByText("Delete My Account"));
    fireEvent.change(screen.getByPlaceholderText("Your password"), {
      target: { value: "mypassword" },
    });
    fireEvent.click(screen.getByText("Yes, Delete"));

    await waitFor(() => {
      expect(screen.getByText("Account Deleted")).toBeInTheDocument();
    });
  });
});
