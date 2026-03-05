/**
 * Backend API base URL for client-side fetches.
 * Used for long-running endpoints (player, edge) that exceed Next.js proxy's 30s timeout.
 * PrizePicks endpoints use the proxy (fast) via relative /api/... URLs.
 */
export const API_BASE =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:5000')
    : ''
