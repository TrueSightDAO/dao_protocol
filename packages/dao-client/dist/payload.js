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
export class PayloadBuilder {
    /**
     * Build a canonical payload string from an event name and attributes.
     * (v1.0.x compatible — no Timestamp injection, no field guard)
     */
    build(eventName, attributes) {
        if (!eventName) {
            throw new Error('eventName is required');
        }
        const lines = [];
        for (const [key, rawValue] of Object.entries(attributes)) {
            if (rawValue === undefined || rawValue === null)
                continue;
            let value;
            if (Array.isArray(rawValue)) {
                value = rawValue.join(', ');
            }
            else if (typeof rawValue === 'object') {
                try {
                    value = JSON.stringify(rawValue);
                }
                catch {
                    value = String(rawValue);
                }
            }
            else {
                value = String(rawValue);
            }
            // Indent multi-line values
            if (value.includes('\n')) {
                value = value.replace(/\r?\n/g, '\n  ');
            }
            lines.push(`- ${key}: ${value}`);
        }
        return `[${eventName.trim()}]\n${lines.join('\n')}\n--------`;
    }
    /**
     * Build a canonical payload with v1.1.0 safety features:
     *   - Auto-injects Timestamp as the first field (ISO 8601 UTC)
     *   - Rejects field values containing [... EVENT] substrings
     *
     * The Timestamp is INSIDE the signed body (before --------), so it
     * varies the signature on each call — preventing HTTP 409 "Duplicate
     * submission" errors from persistent keys.
     */
    buildSubmitEvent(eventName, fields, timestamp) {
        if (!eventName) {
            throw new Error('eventName is required');
        }
        // Validate field values before building
        this.validateFieldValues(fields);
        // Inject Timestamp as the first field
        const ts = timestamp || new Date().toISOString();
        const augmented = {
            Timestamp: ts,
            ...fields,
        };
        return this.build(eventName, augmented);
    }
    /**
     * Validate that no field value contains a bracketed event tag like
     * [CONTRIBUTION EVENT] or [PRACTICE EVENT]. Edgar dispatches by
     * substring matching on the event name — a bracketed tag inside a
     * value causes a 422 misdispatch.
     *
     * Throws an error with the offending field name if found.
     */
    validateFieldValues(fields) {
        // Match [<any word ending in EVENT>] — case-insensitive
        const eventTagPattern = /\[[A-Za-z]+(?:\s+[A-Za-z]+)*\s+EVENT\]/i;
        for (const [key, rawValue] of Object.entries(fields)) {
            if (rawValue === undefined || rawValue === null)
                continue;
            let value;
            if (Array.isArray(rawValue)) {
                value = rawValue.join(', ');
            }
            else if (typeof rawValue === 'object') {
                try {
                    value = JSON.stringify(rawValue);
                }
                catch {
                    value = String(rawValue);
                }
            }
            else {
                value = String(rawValue);
            }
            if (eventTagPattern.test(value)) {
                throw new Error(`Field '${key}' contains a bracketed event tag which would cause Edgar misdispatch. ` +
                    `Value: "${value.slice(0, 100)}". Remove or escape the bracketed tag.`);
            }
        }
    }
}
//# sourceMappingURL=payload.js.map