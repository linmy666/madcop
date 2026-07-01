import React from 'react'
import { t } from '../i18n'
import { reportReactError } from '../lib/diagnosticsCapture'
import { Button } from './shared/Button'
import { DoctorPanel } from './doctor/DoctorPanel'

type Props = {
  children: React.ReactNode
}

type State = {
  hasError: boolean
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: unknown, errorInfo: React.ErrorInfo) {
    // PATCHED for debugging: stash error in window for ErrorBoundary fallback to show
    try {
      const msg = error instanceof Error ? `${error.message}\n${error.stack ?? ''}` : String(error)
      const stack = (errorInfo?.componentStack ?? '').slice(0, 2000)
      ;(window as any).__lastReactError = `${msg}\n\nComponent stack:\n${stack}`
    } catch {}
    void reportReactError(error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return <ErrorBoundaryFallback />
    }

    return this.props.children
  }
}

function ErrorBoundaryFallback() {
  // PATCHED for debugging: show the actual error message
  const [errMsg, setErrMsg] = React.useState<string>('Click "重试" to retry')
  React.useEffect(() => {
    try {
      const last = (window as any).__lastReactError
      if (last) {
        setErrMsg(String(last))
      }
    } catch {}
  }, [])
  return (
    <div className="h-screen w-screen bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        <div className="text-base font-semibold">{t('errorBoundary.title')}</div>
        <div className="mt-2 text-xs text-[var(--color-text-tertiary)] whitespace-pre-wrap font-mono bg-[var(--color-surface)] p-2 rounded">
          {errMsg}
        </div>
        <div className="mt-2 text-sm text-[var(--color-text-tertiary)]">
          {t('errorBoundary.description')}
        </div>
        <div className="mt-4 flex justify-center">
          <Button type="button" variant="secondary" size="sm" onClick={() => window.location.reload()}>
            {t('common.retry')}
          </Button>
        </div>
        <div className="mt-4 text-left">
          <DoctorPanel compact />
        </div>
      </div>
    </div>
  )
}
