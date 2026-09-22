/**
 * Use the installed canonical report builder and its browser verifier.
 * A scoped compatibility correction addresses its 100vw toolbar overflowing
 * Windows classic scrollbars. No plugin files, data, themes, or charts change.
 */
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

export function fixClassicScrollbarWidth(html) {
  let corrections = 0
  const result = html.replace(/\.analytics-top-bar\s*\{[^}]*\}/g, rule => {
    if (!rule.includes('width: 100vw;') || !rule.includes('calc(50% - 50vw)')) return rule
    corrections++
    return rule.replace('width: 100vw;', 'width: calc(100% + 2 * var(--ds-gutter));')
      .replaceAll('calc(50% - 50vw)', 'calc(-1 * var(--ds-gutter))')
  })
  if (corrections > 1) throw new Error('Ambiguous toolbar CSS; review the installed renderer before packaging.')
  return { html: result, corrections }
}

async function main() {
  const args = process.argv.slice(2)
  const get = name => { const i = args.indexOf(name); return i < 0 ? null : args[i + 1] }
  const renderer = get('--renderer')
  if (!renderer || !get('--input') || !get('--output')) throw new Error('Required: --renderer, --input, --output')
  const directory = dirname(resolve(renderer))
  const builder = await import(pathToFileURL(join(directory, 'build_portable_artifact.mjs')).href)
  const delivery = await import(pathToFileURL(resolve(renderer)).href)
  const patched = fixClassicScrollbarWidth(builder.readPackagedReaderRuntime().html)
  const receipt = await delivery.deliverPortableArtifact({
    inputPath: get('--input'), outputPath: get('--output'),
  }, {
    build: (input, options = {}) => builder.buildPortableArtifact(input, { ...options, runtimeHtml: patched.html }),
  })
  console.log(JSON.stringify({ ...receipt, compatibility: { classicScrollbarToolbarCorrections: patched.corrections } }))
  if (!receipt.ok) process.exitCode = 1
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1 })
}
