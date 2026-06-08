/**
 * Canonical payload formatting for Edgar submissions.
 *
 * Format:
 *   [EVENT NAME]
 *   - Label: value
 *   - Label2: value2
 *   --------
 */
export declare class PayloadBuilder {
    /**
     * Build a canonical payload string from an event name and attributes.
     */
    build(eventName: string, attributes: Record<string, unknown>): string;
}
//# sourceMappingURL=payload.d.ts.map