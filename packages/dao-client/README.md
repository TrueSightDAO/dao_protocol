# @truesight_dao/dao-client

Zero-dependency browser library for TrueSight DAO identity management, cryptographic signing, and Edgar submission.

## Usage

### Browser (CDN)

```html
<script src="https://unpkg.com/@truesight_dao/dao-client@1.0.1/dist/dao-client.min.js"></script>
<script>
  // window.DaoClient is the class itself
  const client = new DaoClient();
  
  // Static helpers available directly
  const buf = DaoClient.base64ToArrayBuffer('SGVsbG8=');
  
  // Sign and submit
  client.submit('CONTRIBUTION EVENT', { key: 'value' })
    .then(result => console.log('Submitted:', result.txId));
</script>
```

### Module (ESM / CJS)

```ts
import { DaoClient } from '@truesight_dao/dao-client';
const client = new DaoClient();
```

## Build

```bash
npm run build      # CJS + IIFE (browser)
npm run build:esm  # ESM
npm test           # Runtime smoke test on the built bundle
```

## Publishing (automatic)

**Releasing is just: bump the version → merge.** On any push to `main` that
changes `packages/dao-client/package.json`, the `npm-publish-dao-client.yml`
workflow builds, runs the smoke test (`npm test`), and publishes **only if that
version is new** on npm. No manual step, no token handling.

```
# release flow
1. bump "version" in packages/dao-client/package.json (in a PR)
2. merge to main
3. CI publishes automatically (skips if the version already exists; a failing
   smoke test blocks the publish)
```

`workflow_dispatch` and `dao-client-v*` tags also trigger it, as escape hatches.

### npm token (it expires)

CI publishes with the **`NPM_TOKEN`** GitHub Actions secret on `dao_protocol`
(an npm Automation token for the `truesight_dao` org). **It expires (~2026-09-06)**
— when it does, publishes 401 and the **weekly `npm-token-health.yml` check**
fails loudly. Rotation is governor-only: regenerate an Automation token on
npmjs.com → update the `NPM_TOKEN` secret on `dao_protocol`. Tracked in
`agentic_ai_context/OPEN_FOLLOWUPS.md`. **Never put the token on a server or in
chat** — it only lives as the GH Actions secret.

## License

MIT
