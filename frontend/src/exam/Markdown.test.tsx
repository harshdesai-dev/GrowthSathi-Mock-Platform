import { render, screen } from "@testing-library/react";
import { Markdown } from "./Markdown";

test("renders mathematics but never raw HTML, javascript links or unsafe images", () => {
  const { container } = render(
    <Markdown
      text={
        "Solve $x^2=4$. <script>alert(1)</script> [bad](javascript:alert(1)) ![diagram](data:image/svg+xml,bad)"
      }
    />,
  );
  expect(container.querySelector(".katex")).toBeTruthy();
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("a")).toBeNull();
  expect(screen.getByAltText("diagram")).not.toHaveAttribute("src");
});
