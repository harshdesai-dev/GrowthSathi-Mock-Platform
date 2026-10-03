import growthSathiLogo from "../assets/brand/growthsathi-logo.webp";

export function FoundationPage() {
  return (
    <main className="foundation-shell">
      <section className="foundation-card" aria-labelledby="foundation-title">
        <img
          className="brand-logo"
          src={growthSathiLogo}
          alt="GrowthSathi"
          width="220"
          height="220"
        />
        <p className="eyebrow">GrowthSathi</p>
        <h1 id="foundation-title">Mock platform foundation</h1>
        <p>
          Phase 0 infrastructure is ready. Product features begin in later
          phases.
        </p>
      </section>
    </main>
  );
}
