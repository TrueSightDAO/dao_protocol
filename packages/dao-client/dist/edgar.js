/**
 * Edgar HTTP client — handles submission and share-text generation.
 */
export class EdgarClient {
    constructor(baseUrl, verifyUrl) {
        this.baseUrl = baseUrl.replace(/\/+$/, '');
        this.submitUrl = `${this.baseUrl}/dao/submit_contribution`;
        this.verifyUrl = verifyUrl;
        this.checkSignatureUrl = `${this.baseUrl}/dao/check_digital_signature`;
    }
    /**
     * Build the share text wrapper around a signed payload.
     */
    buildShareText(payload, txId, publicKey, generationSource) {
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
    async parseSubmitResponse(response, txId, slug) {
        const httpStatus = response.status;
        let body = {};
        try {
            body = await response.json();
        }
        catch {
            // Non-JSON response
        }
        const base = {
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
                error: body.error || 'Duplicate submission',
            };
        }
        // 422 — Validation failed (e.g. email onboarding failed)
        if (httpStatus === 422) {
            const emailReg = this.parseEmailRegistration(body);
            return {
                ...base,
                status: 'validation_failed',
                error: body.error || 'Validation failed',
                emailRegistration: emailReg,
            };
        }
        // 5xx — Server error
        if (httpStatus >= 500) {
            return {
                ...base,
                status: 'server_error',
                error: body.error || `Server error (${httpStatus})`,
            };
        }
        // 200 — Success (or signature verification failed)
        if (httpStatus === 200) {
            const sigVerification = body.signature_verification;
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
    parseEmailRegistration(body) {
        const er = body.email_registration;
        if (!er || !er.applicable) {
            return undefined;
        }
        let status = 'not_applicable';
        if (er.ok === true) {
            if (er.activated === true) {
                status = 'activated';
            }
            else if (er.already_consumed === true) {
                status = 'already_consumed';
            }
            else if (er.pending_verification === true) {
                status = 'pending_verification';
            }
        }
        else if (er.ok === false) {
            if (er.pubkey_mismatch === true) {
                status = 'pubkey_mismatch';
            }
            else if (er.not_found === true) {
                status = 'not_found';
            }
        }
        return {
            status,
            contributorEmail: er.contributor_email,
        };
    }
    /**
     * Call Edgar's check_digital_signature endpoint.
     * Returns the authoritative registration status for a public key.
     */
    async checkRegistration(publicKey) {
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
                    contributor_name: body.contributor_name,
                    contributor_email: body.contributor_email,
                };
            }
            if (body.pending_verification === true) {
                return {
                    registered: false,
                    pending_verification: true,
                    contributor_email: body.contributor_email,
                };
            }
            return {
                registered: false,
                error: body.error || 'Unknown response',
            };
        }
        catch (err) {
            return {
                registered: false,
                error: `Network error: ${err instanceof Error ? err.message : String(err)}`,
            };
        }
    }
    async uploadDesign(shareText, imageFile, filename) {
        const formData = new FormData();
        formData.append('text', shareText);
        formData.append('attachment', imageFile, filename);
        try {
            const response = await fetch(`${this.baseUrl}/design/upload`, {
                method: 'POST',
                body: formData,
            });
            const body = await response.json().catch(() => ({}));
            if (response.status === 200 && body.status === 'ok') {
                return {
                    ok: true,
                    status: 'uploaded',
                    design_id: body.design_id,
                    image_url: body.image_url,
                };
            }
            if (response.status === 401) {
                return { ok: false, status: 'auth_error', error: body.error || 'Authentication failed' };
            }
            if (response.status === 422) {
                return { ok: false, status: 'validation_error', error: body.error || 'Invalid design file' };
            }
            return { ok: false, status: 'server_error', error: body.error || `HTTP ${response.status}` };
        }
        catch (err) {
            return { ok: false, status: 'server_error', error: `Network error: ${err instanceof Error ? err.message : String(err)}` };
        }
    }
    async listDesigns(email, publicKey, shareText) {
        const params = new URLSearchParams({
            email,
            signature: publicKey,
            signed_payload: shareText,
        });
        try {
            const response = await fetch(`${this.baseUrl}/design/list?${params}`);
            const body = await response.json().catch(() => ({}));
            if (response.status === 200 && body.status === 'ok') {
                return { ok: true, status: 'loaded', designs: body.designs };
            }
            if (response.status === 401 || response.status === 403) {
                return { ok: false, status: 'auth_error', error: body.error || 'Authentication failed' };
            }
            return { ok: false, status: 'server_error', error: body.error || `HTTP ${response.status}` };
        }
        catch (err) {
            return { ok: false, status: 'server_error', error: `Network error: ${err instanceof Error ? err.message : String(err)}` };
        }
    }
    async orderDesign(shareText) {
        const formData = new FormData();
        formData.append('text', shareText);
        try {
            const response = await fetch(`${this.baseUrl}/design/order`, {
                method: 'POST',
                body: formData,
            });
            const body = await response.json().catch(() => ({}));
            if (response.status === 200 && body.status === 'ok') {
                return {
                    ok: true,
                    status: 'ordered',
                    order_id: body.order_id,
                    design_id: body.design_id,
                    quantity: body.quantity,
                    unit_price: body.unit_price,
                    sku: body.sku,
                    image_url: body.image_url,
                };
            }
            if (response.status === 401) {
                return { ok: false, status: 'auth_error', error: body.error || 'Authentication failed' };
            }
            if (response.status === 422 || response.status === 400) {
                return { ok: false, status: 'validation_error', error: body.error || 'Invalid order' };
            }
            return { ok: false, status: 'server_error', error: body.error || `HTTP ${response.status}` };
        }
        catch (err) {
            return { ok: false, status: 'server_error', error: `Network error: ${err instanceof Error ? err.message : String(err)}` };
        }
    }
}
//# sourceMappingURL=edgar.js.map