/**
 * Edgar HTTP client — handles submission and share-text generation.
 */

export class EdgarClient {
  readonly baseUrl: string;
  readonly submitUrl: string;
  readonly verifyUrl: string;

  constructor(baseUrl: string, verifyUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.submitUrl = `${this.baseUrl}/dao/submit_contribution`;
    this.verifyUrl = verifyUrl;
  }

  /**
   * Build the share text wrapper around a signed payload.
   */
  buildShareText(
    payload: string,
    txId: string,
    publicKey: string,
    generationSource: string
  ): string {
    return [
      payload,
      '',
      `My Digital Signature: ${publicKey}`,
      '',
      `Request Transaction ID: ${txId}`,
      '',
      `This submission was generated using ${generationSource}`,
      '',
      `Verify submission here: ${this.verifyUrl}`,
    ].join('\n');
  }
}
