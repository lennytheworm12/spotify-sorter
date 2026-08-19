import { useState } from 'react'
import { spotifyLoginUrl } from '../api/client'
import { cleanupOAuthUrlParams } from '../utils/oauthCleanup'
import heroImg from '../assets/listening-room-hero.png'

export function ConnectScreen({
  connectionError = null,
  onRetry,
}: {
  connectionError?: string | null
  onRetry?: () => void
}) {
  const [dismissed, setDismissed] = useState(false)
  const query = new URLSearchParams(window.location.search)
  const authFailed = query.get('auth') === 'error'
  const reason = query.get('reason')
  const authMessage =
    reason === 'access_denied'
      ? 'Spotify access was not granted. You can try connecting again when you’re ready.'
      : reason === 'state_mismatch' || reason === 'missing_state'
        ? 'The login request expired or could not be verified. Please start again.'
        : 'Spotify login could not be completed. Please try again.'

  function dismissAuthError() {
    setDismissed(true)
    cleanupOAuthUrlParams()
  }

  return (
    <main className="connect">
      <div className="connect__bg" aria-hidden="true">
        <img src={heroImg} alt="" />
        <div className="connect__shade" />
      </div>

      <div className="connect__content">
        <p className="connect__eyebrow">
          <span className="connect__dot" aria-hidden="true" />
          Spotify Sorter
        </p>
        <h1>Spotify Playlist Organizer</h1>
        <p className="connect__lede">
          Automatically organize your liked songs or an existing playlist into
          genre-based Spotify playlists.
        </p>
        {connectionError ? (
          <div className="connect__error" role="alert">
            <p>
              {connectionError ||
                'We couldn’t reach the organizer service. Check that the backend is running.'}
            </p>
            {onRetry ? (
              <button className="connect__retry" type="button" onClick={onRetry}>
                Retry connection
              </button>
            ) : null}
          </div>
        ) : authFailed && !dismissed ? (
          <div className="connect__error" role="alert">
            <p>{authMessage}</p>
            <button className="connect__retry" type="button" onClick={dismissAuthError}>
              Dismiss
            </button>
          </div>
        ) : null}
        <a className="button button--primary connect__cta" href={spotifyLoginUrl()}>
          <span className="connect__spotify" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z" />
            </svg>
          </span>
          Connect Spotify
        </a>
      </div>
    </main>
  )
}
