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

export class EdgarClient {
  readonly baseUrl: string;
  readonly submitUrl: string;
  readonly verifyUrl: string;
  readonly checkSignatureUrl: string;

  constructor(baseUrl: string, verifyUrl: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.submitUrl = `${this.baseUrl}/dao/submit_contribution`;
    this.verifyUrl = verifyUrl;
    this.checkSignatureUrl = `${this.baseUrl}/dao/check_digital_signature`;
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

  /**
   * Parse Edgar's submit_contribution response into a structured outcome.
   *
   * Edgar response shapes:
   *   200: { status: 'success', signature_verification: 'success', email_registration?: {...} }
   *   409: { status: 'error', error: 'Duplicate submission...' }
   *   422: { status: 'error', error: 'Email onboarding failed', email_registration: {ok: false, ...} }
   *   500: { status: 'error', error: '...' }
   */
  async parseSubmitResponse(
    response: Response,
    txId: string,
    slug: string
  ): Promise<SubmitEventResponse> {
    const httpStatus = response.status;
    let body: Record<string, unknown> = {};
    try {
      body = await response.json();
    } catch {
      // Non-JSON response
    }

    const base: Omit<SubmitEventResponse, 'status'> = {
      ok: false,
      txId,
      slug,
      httpStatus,
    };

    // 409 — Duplicate submission
    if (httpStatus === 409) {
      return {
        ...base,
        status: 'duplicate',
        error: (body.error as string) || 'Duplicate submission',
      };
    }

    // 422 — Validation failed (e.g. email onboarding failed)
    if (httpStatus === 422) {
      const emailReg = this.parseEmailRegistration(body);
      return {
        ...base,
        status: 'validation_failed',
        error: (body.error as string) || 'Validation failed',
        emailRegistration: emailReg,
      };
    }

    // 5xx — Server error
    if (httpStatus >= 500) {
      return {
        ...base,
        status: 'server_error',
        error: (body.error as string) || `Server error (${httpStatus})`,
      };
    }

    // 200 — Success (or signature verification failed)
    if (httpStatus === 200) {
      const sigVerification = body.signature_verification as string;

      if (sigVerification === 'failed' || sigVerification === 'error') {
        return {
          ...base,
          status: 'signature_verification_failed',
          error: 'Signature verification failed on Edgar',
        };
      }

      const emailReg = this.parseEmailRegistration(body);
      return {
        ...base,
        ok: true,
        status: 'submitted',
        emailRegistration: emailReg,
      };
    }

    // Unexpected status code
    return {
      ...base,
      status: 'server_error',
      error: `Unexpected HTTP ${httpStatus}`,
    };
  }

  /**
   * Parse the email_registration field from Edgar's response body.
   */
  private parseEmailRegistration(
    body: Record<string, unknown>
  ): EmailRegistrationStatus | undefined {
    const er = body.email_registration as Record<string, unknown> | undefined;
    if (!er || !er.applicable) {
      return undefined;
    }

    let status: EmailRegistrationStatus['status'] = 'not_applicable';

    if (er.ok === true) {
      if (er.activated === true) {
        status = 'activated';
      } else if (er.already_consumed === true) {
        status = 'already_consumed';
      } else if (er.pending_verification === true) {
        status = 'pending_verification';
      }
    } else if (er.ok === false) {
      if (er.pubkey_mismatch === true) {
        status = 'pubkey_mismatch';
      } else if (er.not_found === true) {
        status = 'not_found';
      }
    }

    return {
      status,
      contributorEmail: er.contributor_email as string | undefined,
    };
  }

  /**
   * Call Edgar's check_digital_signature endpoint.
   * Returns the authoritative registration status for a public key.
   */
  async checkRegistration(publicKey: string): Promise<CheckRegistrationResponse> {
    const url = `${this.checkSignatureUrl}?signature=${encodeURIComponent(publicKey)}`;

    try {
      const response = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
      });

      if (!response.ok) {
        if (response.status === 404) {
          return { registered: false, error: 'No matching contributor digital signature' };
        }
        const text = await response.text().catch(() => '');
        return { registered: false, error: `HTTP ${response.status}: ${text.slice(0, 200)}` };
      }

      const body = await response.json();

      if (body.registered === true) {
        return {
          registered: true,
          contributor_name: body.contributor_name as string | undefined,
          contributor_email: body.contributor_email as string | undefined,
        };
      }

      if (body.pending_verification === true) {
        return {
          registered: false,
          pending_verification: true,
          contributor_email: body.contributor_email as string | undefined,
        };
      }

      return {
        registered: false,
        error: (body.error as string) || 'Unknown response',
      };
    } catch (err) {
      return {
        registered: false,
        error: `Network error: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
  }
}
