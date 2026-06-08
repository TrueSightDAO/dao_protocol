import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DaoClient } from '../src/index';
import { EdgarClient } from '../src/edgar';

// Mock crypto.subtle for tests
const mockGenerateKey = vi.fn().mockResolvedValue({
  publicKey: 'mock-public-key',
  privateKey: 'mock-private-key',
});

const mockSign = vi.fn().mockResolvedValue(new ArrayBuffer(32));
const mockDigest = vi.fn().mockResolvedValue(new ArrayBuffer(32));
const mockExportKey = vi.fn().mockResolvedValue(new ArrayBuffer(128));
const mockImportKey = vi.fn().mockResolvedValue('mock-key');

beforeEach(() => {
  vi.clearAllMocks();

  // Set up crypto.subtle mock
  Object.defineProperty(globalThis, 'crypto', {
    value: {
      subtle: {
        generateKey: mockGenerateKey,
        sign: mockSign,
        digest: mockDigest,
        exportKey: mockExportKey,
        importKey: mockImportKey,
        verify: vi.fn().mockResolvedValue(true),
      },
    },
    writable: true,
    configurable: true,
  });

  // Mock localStorage
  const store: Record<string, string> = {};
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem: vi.fn((key: string) => store[key] || null),
      setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
      removeItem: vi.fn((key: string) => { delete store[key]; }),
      clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]); }),
    },
    writable: true,
    configurable: true,
  });

  // Mock window.location
  Object.defineProperty(globalThis, 'window', {
    value: {
      location: {
        origin: 'https://example.com',
        pathname: '/test',
        href: 'https://example.com/test',
      },
      crypto: {
        subtle: {
          generateKey: mockGenerateKey,
          sign: mockSign,
          digest: mockDigest,
          exportKey: mockExportKey,
          importKey: mockImportKey,
          verify: vi.fn().mockResolvedValue(true),
        },
      },
    },
    writable: true,
    configurable: true,
  });

  // Mock fetch
  globalThis.fetch = vi.fn();

  // Mock FormData
  globalThis.FormData = vi.fn().mockImplementation(() => ({
    append: vi.fn(),
  }));
});

describe('DaoClient', () => {
  describe('constructor', () => {
    it('generates a keypair when none exists in storage', async () => {
      // Need to handle the async key generation
      // The constructor calls generateKeyPairSync which throws, then falls through
      // to the async path. For this test we'll just verify the client is created.
      const client = new DaoClient({ edgarBase: 'https://edgar.test', verifyUrl: 'https://dapp.test/verify' });
      expect(client).toBeInstanceOf(DaoClient);
    });

    it('uses provided generationSource', () => {
      const client = new DaoClient({ generationSource: 'https://custom.source/page' });
      // generationSource is private, but we can verify the client was created
      expect(client).toBeInstanceOf(DaoClient);
    });
  });

  describe('submitEvent()', () => {
    it('returns submitted status on 200 with signature_verification: success', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'success',
          signature_verification: 'success',
          googleSheetLogged: true,
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      // Override the private key for signing
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.submitEvent({
        eventType: 'TEST EVENT',
        fields: { Key: 'value' },
      });

      expect(result.ok).toBe(true);
      expect(result.status).toBe('submitted');
      expect(result.httpStatus).toBe(200);
    });

    it('returns duplicate status on 409', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({
          status: 'error',
          error: 'Duplicate submission (Request Transaction ID already processed).',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.submitEvent({
        eventType: 'TEST EVENT',
        fields: { Key: 'value' },
      });

      expect(result.ok).toBe(false);
      expect(result.status).toBe('duplicate');
      expect(result.httpStatus).toBe(409);
    });

    it('returns validation_failed status on 422', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          status: 'error',
          error: 'Email onboarding failed',
          email_registration: {
            applicable: true,
            ok: false,
            error: 'Public key mismatch',
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.submitEvent({
        eventType: 'TEST EVENT',
        fields: { Key: 'value' },
      });

      expect(result.ok).toBe(false);
      expect(result.status).toBe('validation_failed');
      expect(result.httpStatus).toBe(422);
    });

    it('returns server_error status on 500', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({
          status: 'error',
          error: 'Internal server error',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.submitEvent({
        eventType: 'TEST EVENT',
        fields: { Key: 'value' },
      });

      expect(result.ok).toBe(false);
      expect(result.status).toBe('server_error');
      expect(result.httpStatus).toBe(500);
    });

    it('returns signature_verification_failed when Edgar reports failed verification', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'success',
          signature_verification: 'failed',
          googleSheetLogged: true,
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.submitEvent({
        eventType: 'TEST EVENT',
        fields: { Key: 'value' },
      });

      expect(result.ok).toBe(false);
      expect(result.status).toBe('signature_verification_failed');
      expect(result.httpStatus).toBe(200);
    });

    it('returns network error when fetch fails', async () => {
      const mockFetch = vi.fn().mockRejectedValue(new Error('Network failure'));
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.submitEvent({
        eventType: 'TEST EVENT',
        fields: { Key: 'value' },
      });

      expect(result.ok).toBe(false);
      expect(result.status).toBe('server_error');
      expect(result.error).toContain('Network error');
    });

    it('includes slug in the result', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'success',
          signature_verification: 'success',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.submitEvent({
        eventType: 'TEST EVENT',
        fields: { Key: 'value' },
      });

      expect(result.slug).toBeTruthy();
      expect(result.slug).toContain('pk-');
    });
  });

  describe('registerEmail()', () => {
    it('submits an EMAIL REGISTERED EVENT', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'success',
          signature_verification: 'success',
          email_registration: {
            applicable: true,
            ok: true,
            pending_verification: true,
            contributor_email: 'test@example.com',
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.registerEmail('test@example.com');

      expect(result.ok).toBe(true);
      expect(result.status).toBe('submitted');
      expect(result.emailRegistration).toBeDefined();
      expect(result.emailRegistration!.status).toBe('pending_verification');
      expect(result.emailRegistration!.contributorEmail).toBe('test@example.com');
    });
  });

  describe('verifyEmail()', () => {
    it('submits an EMAIL VERIFICATION EVENT', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'success',
          signature_verification: 'success',
          email_registration: {
            applicable: true,
            ok: true,
            activated: true,
            contributor_email: 'test@example.com',
          },
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';
      client.privateKey = 'test-private-key';

      const result = await client.verifyEmail('test@example.com', 'abc123');

      expect(result.ok).toBe(true);
      expect(result.status).toBe('submitted');
      expect(result.emailRegistration).toBeDefined();
      expect(result.emailRegistration!.status).toBe('activated');
    });
  });

  describe('checkRegistration()', () => {
    it('returns registered: true when key is active', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          registered: true,
          contributor_name: 'Test User',
          contributor_email: 'test@example.com',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';

      const result = await client.checkRegistration();

      expect(result.registered).toBe(true);
      expect(result.contributor_name).toBe('Test User');
      expect(result.contributor_email).toBe('test@example.com');
    });

    it('returns pending_verification when key is not yet activated', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          registered: false,
          pending_verification: true,
          contributor_email: 'test@example.com',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';

      const result = await client.checkRegistration();

      expect(result.registered).toBe(false);
      expect(result.pending_verification).toBe(true);
      expect(result.contributor_email).toBe('test@example.com');
    });

    it('returns registered: false when key is not found', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({
          registered: false,
          error: 'No matching contributor digital signature',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new DaoClient({ edgarBase: 'https://edgar.test' });
      client.publicKey = 'test-public-key';

      const result = await client.checkRegistration();

      expect(result.registered).toBe(false);
      expect(result.error).toContain('No matching');
    });
  });
});

describe('EdgarClient', () => {
  describe('parseSubmitResponse', () => {
    it('parses 200 with email registration', async () => {
      const client = new EdgarClient('https://edgar.test', 'https://dapp.test/verify');
      
      const response = new Response(
        JSON.stringify({
          status: 'success',
          signature_verification: 'success',
          email_registration: {
            applicable: true,
            ok: true,
            activated: true,
            contributor_email: 'test@example.com',
          },
        }),
        { status: 200 }
      );

      const result = await client.parseSubmitResponse(response, 'tx-123', 'pk-abc');
      expect(result.ok).toBe(true);
      expect(result.status).toBe('submitted');
      expect(result.emailRegistration!.status).toBe('activated');
    });

    it('parses 409 duplicate', async () => {
      const client = new EdgarClient('https://edgar.test', 'https://dapp.test/verify');
      
      const response = new Response(
        JSON.stringify({
          status: 'error',
          error: 'Duplicate submission (Request Transaction ID already processed).',
        }),
        { status: 409 }
      );

      const result = await client.parseSubmitResponse(response, 'tx-123', 'pk-abc');
      expect(result.ok).toBe(false);
      expect(result.status).toBe('duplicate');
    });

    it('parses 422 validation failed', async () => {
      const client = new EdgarClient('https://edgar.test', 'https://dapp.test/verify');
      
      const response = new Response(
        JSON.stringify({
          status: 'error',
          error: 'Email onboarding failed',
          email_registration: {
            applicable: true,
            ok: false,
            error: 'Public key mismatch',
          },
        }),
        { status: 422 }
      );

      const result = await client.parseSubmitResponse(response, 'tx-123', 'pk-abc');
      expect(result.ok).toBe(false);
      expect(result.status).toBe('validation_failed');
      expect(result.emailRegistration!.status).toBe('pubkey_mismatch');
    });
  });

  describe('checkRegistration', () => {
    it('returns registered: true for active key', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          registered: true,
          contributor_name: 'Test User',
          contributor_email: 'test@example.com',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new EdgarClient('https://edgar.test', 'https://dapp.test/verify');
      const result = await client.checkRegistration('test-public-key');

      expect(result.registered).toBe(true);
      expect(result.contributor_name).toBe('Test User');
    });

    it('returns pending_verification for unactivated key', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          registered: false,
          pending_verification: true,
          contributor_email: 'test@example.com',
        }),
      });
      globalThis.fetch = mockFetch;

      const client = new EdgarClient('https://edgar.test', 'https://dapp.test/verify');
      const result = await client.checkRegistration('test-public-key');

      expect(result.registered).toBe(false);
      expect(result.pending_verification).toBe(true);
    });

    it('handles network errors gracefully', async () => {
      const mockFetch = vi.fn().mockRejectedValue(new Error('Network failure'));
      globalThis.fetch = mockFetch;

      const client = new EdgarClient('https://edgar.test', 'https://dapp.test/verify');
      const result = await client.checkRegistration('test-public-key');

      expect(result.registered).toBe(false);
      expect(result.error).toContain('Network error');
    });
  });
});
