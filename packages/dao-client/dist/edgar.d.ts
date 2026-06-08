/**
 * Edgar HTTP client — handles submission and share-text generation.
 */
export declare class EdgarClient {
    readonly baseUrl: string;
    readonly submitUrl: string;
    readonly verifyUrl: string;
    constructor(baseUrl: string, verifyUrl: string);
    /**
     * Build the share text wrapper around a signed payload.
     */
    buildShareText(payload: string, txId: string, publicKey: string, generationSource: string): string;
}
//# sourceMappingURL=edgar.d.ts.map