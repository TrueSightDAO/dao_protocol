/**
 * @truesight_dao/dao-client
 *
 * Zero-dependency browser library for TrueSight DAO identity management,
 * cryptographic signing, and Edgar submission.
 *
 * Usage:
 *   import { DaoClient } from '@truesight_dao/dao-client';
 *   const client = new DaoClient();
 *   await client.submit('CONTRIBUTION EVENT', { ... });
 */
import { SubmitEventResponse, CheckRegistrationResponse } from './edgar';
export interface DaoClientOptions {
    edgarBase?: string;
    verifyUrl?: string;
    /** Prefix used to derive storage keys (default: 'truesight_dao_'). Ignored when publicKeyKey/privateKeyKey are set. */
    storagePrefix?: string;
    /** Explicit localStorage key for the public key. Takes precedence over storagePrefix. */
    publicKeyKey?: string;
    /** Explicit localStorage key for the private key. Takes precedence over storagePrefix. */
    privateKeyKey?: string;
    generationSource?: string;
}
export interface SubmitResult {
    json: Record<string, unknown>;
    txId: string;
}
export interface SignResult {
    payload: string;
    txId: string;
    shareText: string;
}
export interface SubmitEventOptions {
    /** The event type, e.g. 'CONTRIBUTION EVENT' */
    eventType: string;
    /** Key-value fields to include in the signed body */
    fields: Record<string, unknown>;
    /**
     * Override the generation source URL.
     * Defaults to window.location.origin + pathname in browser environments.
     * Required when window is undefined (Node.js).
     */
    generationSource?: string;
}
export { SubmitEventResponse, CheckRegistrationResponse };
export type { EmailRegistrationStatus } from './edgar';
export declare class DaoClient {
    publicKey: string;
    privateKey: string;
    private crypto;
    private payloadBuilder;
    private edgar;
    private storage;
    private generationSource;
    constructor(options?: DaoClientOptions);
    /**
     * Static async factory. Creates a DaoClient and ensures a keypair exists
     * (loading from storage or generating a new one).
     *
     * Usage:
     *   const client = await DaoClient.create();
     */
    static create(options?: DaoClientOptions): Promise<DaoClient>;
    /**
     * Ensure a keypair exists — loads from storage or generates a new one.
     * Safe to call multiple times; no-op if keys already loaded.
     */
    ensureKeys(): Promise<void>;
    /**
     * Build a canonical payload, sign it, and submit to Edgar.
     * (v1.0.x compatible — no Timestamp injection, no field guard)
     */
    submit(eventName: string, attributes: Record<string, unknown>): Promise<SubmitResult>;
    /**
     * Build and sign a payload without submitting.
     */
    sign(eventName: string, attributes: Record<string, unknown>): Promise<SignResult>;
    /**
     * Submit an event with v1.1.0 safety features:
     *   - Auto-injects Timestamp (prevents 409 duplicates from persistent keys)
     *   - Guards field values against [... EVENT] substrings (prevents misdispatch)
     *   - Parses Edgar's response into structured outcomes
     *
     * Returns a structured result with status, txId, slug, and optional
     * email registration details.
     */
    submitEvent(options: SubmitEventOptions): Promise<SubmitEventResponse>;
    /**
     * Submit a [CREDENTIALING ATTESTATION EVENT] — used by credentialing
     * programs (Butterfly Effect Club, capoeira Tribo Mirim Bahia, etc.)
     * to attest that a participant has completed a program milestone.
     *
     * The attestor (admin/teacher) signs this event with their own key.
     * The tokenomics GAS handler picks it up, verifies the attestor is
     * authorized (sheet editor), and commits identity.json +
     * attestations/<ts>.json to lineage-credentials.
     *
     * @see CREDENTIALING_PLATFORM.md §4c for the event spec
     * @see butterfly-effect-club/PROPOSAL.md §6.1 for payload format
     */
    submitAttestation(options: {
        /** Program slug, e.g. 'butterfly-effect' or 'tribomirim' */
        program: string;
        /** Type of attestation, e.g. 'program-completion', 'program-admission' */
        attestationType: string;
        /** The participant's public key (base64 SPKI) */
        attesteePublicKey: string;
        /** The participant's display name */
        attesteeName: string;
        /** ISO 8601 timestamp of when the attestation was captured */
        capturedAt?: string;
        /** Program year, e.g. '2025-2026' */
        programYear?: string;
        /** URL of the source program/roster */
        sourceUrl?: string;
        /** Optional JSON payload with additional metadata */
        payload?: Record<string, unknown>;
        /** Override the generation source URL */
        generationSource?: string;
    }): Promise<SubmitEventResponse>;
    /**
     * Submit a [CREDENTIALING QUALIFICATION EVENT] — used for live-cohort
     * admission (the first of a two-event path: qualification then attestation).
     *
     * For alumni (graduation_date in the past), use submitAttestation() directly.
     * For live cohorts, call submitQualification() on admission and
     * submitAttestation() on completion.
     *
     * @see CREDENTIALING_PLATFORM.md §4b for the event spec
     */
    submitQualification(options: {
        /** Program slug, e.g. 'butterfly-effect' or 'tribomirim' */
        program: string;
        /** The participant's public key (base64 SPKI) */
        participantPublicKey: string;
        /** The participant's display name */
        participantName: string;
        /** ISO 8601 timestamp */
        capturedAt?: string;
        /** Program year, e.g. '2025-2026' */
        programYear?: string;
        /** URL of the source program/roster */
        sourceUrl?: string;
        /** Optional JSON payload with additional metadata */
        payload?: Record<string, unknown>;
        /** Override the generation source URL */
        generationSource?: string;
    }): Promise<SubmitEventResponse>;
    /**
     * Register an email address with the DAO identity system.
     * Submits an [EMAIL REGISTERED EVENT] and returns the registration status.
     *
     * After calling this, the user must click the verification link sent to
     * their email to complete registration.
     */
    registerEmail(email: string): Promise<SubmitEventResponse>;
    /**
     * Verify an email registration using the verification key from the
     * email link. Submits an [EMAIL VERIFICATION EVENT].
     *
     * Call this when the user lands on your page with ?em=...&vk=... params.
     */
    verifyEmail(email: string, verificationKey: string): Promise<SubmitEventResponse>;
    /**
     * Check the registration status of the current public key against Edgar.
     * This is a read-only GET call (not a submission).
     *
     * Returns the authoritative registration status including whether the
     * key is registered, pending verification, or not found.
     */
    checkRegistration(): Promise<CheckRegistrationResponse>;
    /**
     * Get the credential slug: pk-<sha256-hash-prefix>
     */
    getSlug(): Promise<string>;
    /**
     * Verify a signed payload against a transaction ID.
     */
    verifyPayload(payload: string, txId: string): Promise<boolean>;
    /**
     * Generate a new keypair and store it.
     */
    generateKeyPair(): Promise<{
        publicKey: string;
        privateKey: string;
    }>;
    /**
     * Build the share text wrapper around a signed payload.
     */
    private buildShareText;
    static generateKeyPair(): Promise<{
        publicKey: string;
        privateKey: string;
    }>;
    static arrayBufferToBase64(buffer: ArrayBuffer): string;
    static base64ToArrayBuffer(base64: string): ArrayBuffer;
    static base64ToBase64Url(base64: string): string;
}
//# sourceMappingURL=index.d.ts.map