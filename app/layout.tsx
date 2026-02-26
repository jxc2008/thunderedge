import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'ThunderEdge | Valorant Esports Betting Analytics',
  description:
    'Production-ready React component library for ThunderEdge — a dark-themed Valorant esports betting analytics platform. Kill line analytics, EV calculators, team analysis, and moneyline strategy tools.',
  keywords: ['Valorant', 'esports', 'betting', 'analytics', 'PrizePicks', 'kill line'],
}

export const viewport: Viewport = {
  themeColor: '#000000',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans antialiased">{children}</body>
    </html>
  )
}
