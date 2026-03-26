import { Component } from 'react';
import type { ReactNode, ErrorInfo } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="flex flex-col items-center justify-center py-16 gap-4">
          <p className="text-site-red text-sm">
            Произошла ошибка при загрузке компонента.
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="text-sm text-site-blue hover:text-white transition-colors"
          >
            Попробовать снова
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
