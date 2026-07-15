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
export interface DesignUploadResponse {
    ok: boolean;
    status: 'uploaded' | 'validation_error' | 'auth_error' | 'server_error';
    design_id?: string;
    image_url?: string;
    error?: string;
}
export interface DesignOrderResponse {
    ok: boolean;
    status: 'ordered' | 'validation_error' | 'auth_error' | 'server_error';
    order_id?: string;
    design_id?: string;
    quantity?: number;
    unit_price?: number;
    sku?: string;
    image_url?: string;
    error?: string;
}
export interface DesignListResponse {
    ok: boolean;
    status: 'loaded' | 'auth_error' | 'server_error';
    designs?: DesignEntry[];
    error?: string;
}
export interface DesignEntry {
    design_id: string;
    email_hash: string;
    filename: string;
    image_url: string;
    dimensions: string;
    created_at: string;
    orders: DesignOrderEntry[];
}
export interface DesignOrderEntry {
    order_id: string;
    quantity: number;
    unit_price: number;
    sku?: string;
    status: string;
    created_at: string;
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
    uploadDesign(shareText: string, imageFile: File | Blob, filename: string): Promise<DesignUploadResponse>;
    listDesigns(email: string, publicKey: string, shareText: string): Promise<DesignListResponse>;
    orderDesign(shareText: string): Promise<DesignOrderResponse>;
}
//# sourceMappingURL=edgar.d.ts.map