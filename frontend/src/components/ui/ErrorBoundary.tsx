import React from "react";
import { UltronLogo } from "../UltronLogo";

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode; resetKey?: string }, State> {
  constructor(props: { children: React.ReactNode; resetKey?: string }) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message || "Unexpected interface error." };
  }

  componentDidUpdate(prevProps: { resetKey?: string }) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, message: "" });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="state-box" role="alert">
          <UltronLogo variant="empty" size={40} />
          <h3>Workspace Recovered from Error</h3>
          <p className="muted">{this.state.message}</p>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => this.setState({ hasError: false, message: "" })}
          >
            Reload Workspace
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
