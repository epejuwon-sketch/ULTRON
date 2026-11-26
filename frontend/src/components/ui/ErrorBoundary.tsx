import React from "react";
import { UltronLogo } from "../UltronLogo";
import { clearCachesAndReload, isModuleLoadError } from "../../lib/lazyWithRecovery";

interface Props {
  children: React.ReactNode;
  resetKey?: string;
}

interface State {
  hasError: boolean;
  message: string;
  isModuleError: boolean;
  retryNonce: number;
  reloading: boolean;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      message: "",
      isModuleError: false,
      retryNonce: 0,
      reloading: false,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    const isMod = isModuleLoadError(error);
    return {
      hasError: true,
      isModuleError: isMod,
      message: error?.message || "Unexpected interface error.",
    };
  }

  componentDidUpdate(prevProps: Props) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, message: "", isModuleError: false, reloading: false });
    }
  }

  handleRetry = () => {
    this.setState((prev) => ({
      hasError: false,
      message: "",
      isModuleError: false,
      retryNonce: prev.retryNonce + 1,
    }));
  };

  handleHardReload = async () => {
    this.setState({ reloading: true });
    await clearCachesAndReload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="state-box" role="alert" data-testid="workspace-error-boundary">
          <UltronLogo variant="empty" size={40} />
          <h3>
            {this.state.isModuleError
              ? "Workspace Module Update Required"
              : "Workspace Recovered from Error"}
          </h3>
          <p className="muted" style={{ maxWidth: 460 }}>
            {this.state.isModuleError
              ? "This module bundle could not be loaded—usually after a fresh deployment or brief connection drop. Refreshing loads the latest matching assets."
              : this.state.message}
          </p>
          {this.state.isModuleError && (
            <div className="muted mono" style={{ fontSize: 11.5 }}>
              {this.state.message}
            </div>
          )}
          <div className="row" style={{ marginTop: 8, justifyContent: "center", flexWrap: "wrap" }}>
            <button
              id="error-boundary-retry-btn"
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={this.state.reloading}
              onClick={this.handleRetry}
            >
              Retry Workspace
            </button>
            <button
              id="error-boundary-reload-btn"
              type="button"
              className="btn btn-sm"
              disabled={this.state.reloading}
              onClick={this.handleHardReload}
            >
              {this.state.reloading ? "Updating App..." : "Update & Reload App"}
            </button>
          </div>
        </div>
      );
    }
    return <React.Fragment key={this.state.retryNonce}>{this.props.children}</React.Fragment>;
  }
}
