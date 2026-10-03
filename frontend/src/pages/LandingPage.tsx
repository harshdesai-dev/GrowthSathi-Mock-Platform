import { Link } from "react-router-dom";

import growthSathiLogo from "../assets/brand/growthsathi-logo.png";

export function LandingPage() {
  return (
    <main className="landing-shell">
      <nav className="landing-nav" aria-label="Main navigation">
        <Link className="brand-lockup brand-lockup--small" to="/">
          <img src={growthSathiLogo} alt="GrowthSathi" width="52" height="52" />
          <span>GrowthSathi</span>
        </Link>
        <div className="landing-nav__actions">
          <Link className="landing-nav__link" to="/mocks">
            Upcoming mocks
          </Link>
          <Link className="secondary-button" to="/auth">
            Continue with Google
          </Link>
        </div>
      </nav>

      <section className="landing-hero" aria-labelledby="landing-title">
        <div>
          <p className="eyebrow">JEE Main + MHT-CET PCM</p>
          <h1 id="landing-title">
            Exam ke din nahi. <span>Aaj pata karo</span> tum kaha stand karte
            ho.
          </h1>
          <p>
            Competitive mocks built around one shared exam window — with your
            score, rank and Mock Percentile published after verification.
          </p>
          <div className="landing-actions">
            <Link className="primary-button" to="/mocks">
              Explore mock tests
            </Link>
            <Link className="text-link" to="/auth">
              Already registered? Sign in
            </Link>
          </div>
        </div>
        <aside
          className="landing-scorecard"
          aria-label="What each mock gives you"
        >
          <p className="eyebrow">Every verified mock</p>
          <dl>
            <div>
              <dt>Score</dt>
              <dd>Know your performance.</dd>
            </div>
            <div>
              <dt>Rank</dt>
              <dd>See where you stand.</dd>
            </div>
            <div>
              <dt>Mock Percentile</dt>
              <dd>Compare this mock only.</dd>
            </div>
          </dl>
        </aside>
      </section>

      <section className="landing-section" aria-labelledby="landing-offers">
        <div className="landing-section__heading">
          <div>
            <p className="eyebrow">Simple pricing</p>
            <h2 id="landing-offers">Choose the mock that fits your prep.</h2>
          </div>
          <Link to="/mocks">View all offers</Link>
        </div>
        <div className="landing-offers">
          <article>
            <p>JEE Main</p>
            <strong>₹29</strong>
            <span>per mock</span>
          </article>
          <article>
            <p>MHT-CET PCM</p>
            <strong>₹29</strong>
            <span>per mock</span>
          </article>
          <article className="landing-offers__combo">
            <p>JEE + CET combo</p>
            <strong>₹50</strong>
            <span>Save ₹8 across two mocks</span>
          </article>
        </div>
      </section>

      <section
        className="landing-section landing-process"
        aria-labelledby="landing-process"
      >
        <div className="landing-section__heading">
          <div>
            <p className="eyebrow">Focused, not noisy</p>
            <h2 id="landing-process">
              Test. Know your rank. Beat your previous score.
            </h2>
          </div>
        </div>
        <ol>
          <li>
            <span>01</span> Choose a scheduled mock.
          </li>
          <li>
            <span>02</span> Attempt in the shared exam window.
          </li>
          <li>
            <span>03</span> Review verified results when published.
          </li>
        </ol>
      </section>
    </main>
  );
}
