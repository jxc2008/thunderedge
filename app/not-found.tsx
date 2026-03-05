import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-4">
      <h1 className="text-2xl font-semibold text-white">404 — Page not found</h1>
      <p className="text-zinc-400 text-sm">The page you&apos;re looking for doesn&apos;t exist.</p>
      <Link
        href="/"
        className="px-4 py-2 rounded-lg text-sm font-medium text-white"
        style={{ background: 'linear-gradient(135deg, #3b82f6, #0ea5e9)' }}
      >
        Back to home
      </Link>
    </div>
  );
}
