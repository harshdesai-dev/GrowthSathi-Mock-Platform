import { render, screen } from "@testing-library/react";

import { AppRouter } from "./AppRouter";

describe("AppRouter", () => {
  it("renders the Phase 0 foundation without product features", () => {
    window.history.pushState({}, "", "/");
    render(<AppRouter />);
    expect(
      screen.getByRole("heading", { name: "Mock platform foundation" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "GrowthSathi" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Product features begin in later phases/i),
    ).toBeInTheDocument();
  });
});
