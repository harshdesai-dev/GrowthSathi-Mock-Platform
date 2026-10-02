import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="foundation-shell">
      <section className="foundation-card">
        <p className="eyebrow">404</p>
        <h1>Page not found</h1>
        <Link className="text-link" to="/">
          Return to the foundation page
        </Link>
      </section>
    </main>
  );
}
