/**
 * Edgar HTTP client — handles submission and share-text generation.
 */
export interface SubmitEventResponse {
    ok: boolean;
    status: 'submitted' | 'duplicate' | 'signature_verification_failed' | 'validation_failed' | 'server_error';
    txId: string;
    slug: string;
    httpStatus: number;
    emailRegistration?: EmailRegistrationStatus;
    error?: string;
}
export interface EmailRegistrationStatus {
    status: 'activated' | 'already_consumed' | 'pending_verification' | 'pubkey_mismatch' | 'not_found' | 'not_applicable';
    contributorEmail?: string;
}
export interface CheckRegistrationResponse {
    registered: boolean;
    pending_verification?: boolean;
    contributor_name?: string;
    contributor_email?: string;
    error?: string;
}
export declare class EdgarClient {
    readonly baseUrl: string;
    readonly submitUrl: string;
    readonly verifyUrl: string;
    readonly checkSignatureUrl: string;
    constructor(baseUrl: string, verifyUrl: string);
    /**
     * Build the share text wrapper around a signed payload.
     */
    buildShareText(payload: string, txId: string, publicKey: string, generationSource: string): string;
    /**
     * Parse Edgar's submit_contribution response into a structured outcome.
     *
     * Edgar response shapes:
     *   200: { status: 'success', signature_verification: 'success', email_registration?: {...} }
     *   409: { status: 'error', error: 'Duplicate submission...' }
     *   422: { status: 'error', error: 'Email onboarding failed', email_registration: {ok: false, ...} }
     *   500: { status: 'error', error: '...' }
     */
    parseSubmitResponse(response: Response, txId: string, slug: string): Promise<SubmitEventResponse>;
    /**
     * Parse the email_registration field from Edgar's response body.
     */
    private parseEmailRegistration;
    /**
     * Call Edgar's check_digital_signature endpoint.
     * Returns the authoritative registration status for a public key.
     */
    checkRegistration(publicKey: string): Promise<CheckRegistrationResponse>;
}
//# sourceMappingURL=edgar.d.ts.map