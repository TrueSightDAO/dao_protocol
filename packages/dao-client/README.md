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

## Publishing

Push a tag: `dao-client-v1.0.1` — the CI workflow publishes to npm automatically.

## License

MIT
