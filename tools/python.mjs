import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/** Select an executable, never a shell command or a string of command flags. */
export function resolvePython() {
  const override = process.env.HERLENS_PYTHON?.trim()
  const venv = join(projectRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const candidates = override ? [override] : [...(existsSync(venv) ? [venv] : []), ...(process.platform === 'win32' ? ['python', 'python3'] : ['python3', 'python'])]
  for (const executable of candidates) {
    const probe = spawnSync(executable, ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])'], { cwd: projectRoot, encoding: 'utf8', windowsHide: true, timeout: 8000, shell: false })
    const [major, minor] = (probe.stdout?.trim() ?? '').split('.').map(Number)
    if (!probe.error && probe.status === 0 && (major > 3 || major === 3 && minor >= 11)) return executable
  }
  throw new Error(override ? 'HERLENS_PYTHON must name one working Python 3.11+ executable (without command flags).' : 'Python 3.11+ was not found. Create .venv and install backend/requirements.txt, or set HERLENS_PYTHON to an executable path.')
}

async function main() {
  const args = process.argv.slice(2)
  if (!args.length) throw new Error('Usage: node tools/python.mjs <Python arguments>')
  const child = spawn(resolvePython(), args, { cwd: projectRoot, stdio: 'inherit', windowsHide: true, shell: false })
  let forwarded = false
  const forward = signal => {
    if (forwarded) return
    forwarded = true
    // Windows console Ctrl+C is delivered to Python too; let its handler finish.
    if (process.platform !== 'win32') child.kill(signal)
    const timeout = setTimeout(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM') }, 5000)
    timeout.unref()
  }
  process.on('SIGINT', forward)
  process.on('SIGTERM', forward)
  child.on('error', () => { console.error('Could not start the selected Python executable.'); process.exitCode = 1 })
  child.on('exit', (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0) })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1 })
}
