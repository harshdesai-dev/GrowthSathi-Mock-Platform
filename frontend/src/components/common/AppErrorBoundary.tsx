import { Component, type ErrorInfo, type PropsWithChildren } from "react";

interface State {
  hasError: boolean;
}

export class AppErrorBoundary extends Component<PropsWithChildren, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled application error", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="foundation-shell">
          <section className="foundation-card" role="alert">
            <p className="eyebrow">GrowthSathi</p>
            <h1>Something went wrong</h1>
            <p>
              Please refresh the page. If the problem continues, try again
              later.
            </p>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}
