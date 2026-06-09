/**
 * Canonical payload formatting for Edgar submissions.
 *
 * Format:
 *   [EVENT NAME]
 *   - Label: value
 *   - Label2: value2
 *   --------
 *
 * The Ruby SignatureVerifier signs everything up to and including the first
 * --------, then .strip()s the result. The JS builder must match byte-for-byte.
 *
 * v1.1.0 adds:
 *   - buildSubmitEvent() — auto-injects Timestamp, guards field values
 *   - validateFieldValues() — rejects [... EVENT] substrings
 */
export declare class PayloadBuilder {
    /**
     * Build a canonical payload string from an event name and attributes.
     * (v1.0.x compatible — no Timestamp injection, no field guard)
     */
    build(eventName: string, attributes: Record<string, unknown>): string;
    /**
     * Build a canonical payload with v1.1.0 safety features:
     *   - Auto-injects Timestamp as the first field (ISO 8601 UTC)
     *   - Rejects field values containing [... EVENT] substrings
     *
     * The Timestamp is INSIDE the signed body (before --------), so it
     * varies the signature on each call — preventing HTTP 409 "Duplicate
     * submission" errors from persistent keys.
     */
    buildSubmitEvent(eventName: string, fields: Record<string, unknown>, timestamp?: string): string;
    /**
     * Validate that no field value contains a bracketed event tag like
     * [CONTRIBUTION EVENT] or [PRACTICE EVENT]. Edgar dispatches by
     * substring matching on the event name — a bracketed tag inside a
     * value causes a 422 misdispatch.
     *
     * Throws an error with the offending field name if found.
     */
    validateFieldValues(fields: Record<string, unknown>): void;
}
//# sourceMappingURL=payload.d.ts.map