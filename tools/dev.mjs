import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'
import { resolvePython, projectRoot } from './python.mjs'

// A stdin shutdown channel lets uvicorn exit gracefully on Windows as well as
// Unix. EOF also stops it if this parent goes away; no private API is exposed.
const backendBootstrap = `
import os, sys, threading, uvicorn
config = uvicorn.Config("backend.herlens.api:app", host="127.0.0.1", port=8000,
                        env_file=".env" if os.path.isfile(".env") else None,
                        timeout_graceful_shutdown=5)
server = uvicorn.Server(config)
def parent_watch():
    try:
        for line in sys.stdin:
            if line.strip() == "HERLENS_SHUTDOWN":
                break
    finally:
        server.should_exit = True
threading.Thread(target=parent_watch, daemon=True).start()
server.run()
`

let backend
let vite
let stopping
const exited = child => child.exitCode !== null || child.signalCode !== null

async function waitForExit(child, timeout) {
  if (exited(child)) return true
  return new Promise(resolve => {
    const onExit = () => { clearTimeout(timer); resolve(true) }
    const timer = setTimeout(() => { child.off('exit', onExit); resolve(false) }, timeout)
    child.once('exit', onExit)
  })
}

async function forceStop(child) {
  if (!child?.pid || exited(child)) return
  if (process.platform === 'win32') {
    // Only the exact process tree started by this runner is targeted.
    await new Promise(resolve => {
      const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore', shell: false })
      killer.once('error', resolve)
      killer.once('exit', resolve)
    })
  } else {
    child.kill('SIGTERM')
    if (!await waitForExit(child, 1000)) child.kill('SIGKILL')
  }
}

function stop(code = 0) {
  if (stopping) return stopping
  stopping = (async () => {
    process.exitCode = code
    await vite?.close()
    if (backend && !exited(backend)) {
      backend.stdin?.end('HERLENS_SHUTDOWN\n')
      if (!await waitForExit(backend, 6500)) await forceStop(backend)
    }
  })()
  return stopping
}

async function main() {
  backend = spawn(resolvePython(), ['-u', '-c', backendBootstrap], { cwd: projectRoot, stdio: ['pipe', 'inherit', 'inherit'], windowsHide: true, shell: false })
  backend.stdin.on('error', () => {})
  backend.once('error', () => { console.error('Backend could not start. Install backend/requirements.txt in .venv.'); void stop(1) })
  backend.once('exit', code => { if (!stopping) { console.error(`Backend stopped (${code ?? 'signal'}).`); void stop(code || 1) } })
  process.once('SIGINT', () => void stop(0))
  process.once('SIGTERM', () => void stop(0))
  let ready = false
  for (let attempt = 0; attempt < 100 && !stopping; attempt++) {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/strategy/health', { signal: AbortSignal.timeout(700) })
      if (response.ok) { ready = true; break }
    } catch { /* Wait for the server we just started, with a bounded timeout. */ }
    await delay(120)
  }
  if (stopping) return
  if (!ready) throw new Error('Backend did not become ready on 127.0.0.1:8000. Check dependencies and whether the port is already occupied.')
  // A brief exit check prevents accidentally pairing with an existing service
  // when our own uvicorn process reports an address-in-use error.
  await delay(150)
  if (stopping || exited(backend)) return
  process.env.VITE_API_MODE = 'local'
  const { createServer } = await import('vite')
  vite = await createServer({ root: projectRoot, server: { host: '127.0.0.1', port: 5173, strictPort: true } })
  await vite.listen()
  console.log('HerLens local workspace is ready. Ctrl+C closes both services.')
  vite.printUrls()
}

main().catch(async error => { console.error(error.message); await stop(1) })
