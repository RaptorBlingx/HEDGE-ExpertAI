import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import App from "./App";

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ schema_version: "2.0", total: 0, apps: [] }),
    }),
  );
});

test("renders the v2 validation console and loads the authoritative catalogue", async () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "HEDGE-ExpertAI Command Console" })).toBeInTheDocument();
  expect(screen.getByLabelText("Response language")).toHaveValue("en");
  expect(screen.getByText(/Welcome to the HEDGE-ExpertAI validation console/)).toBeInTheDocument();

  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v2/catalog/apps?page=1&page_size=100"));
  expect(screen.getByText("0 apps loaded")).toBeInTheDocument();
});
