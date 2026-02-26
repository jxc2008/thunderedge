import { execSync } from 'child_process'
import { fileURLToPath } from 'url'
import { join, dirname } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const projectRoot = join(__dirname, '..')

console.log('[v0] Running npm install to regenerate package-lock.json...')
try {
  execSync('npm install --package-lock-only', {
    cwd: projectRoot,
    stdio: 'inherit',
  })
  console.log('[v0] package-lock.json regenerated successfully.')
} catch (err) {
  console.error('[v0] npm install failed:', err.message)
  process.exit(1)
}
