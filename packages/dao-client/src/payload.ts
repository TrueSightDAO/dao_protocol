/**
 * Canonical payload formatting for Edgar submissions.
 *
 * Format:
 *   [EVENT NAME]
 *   - Label: value
 *   - Label2: value2
 *   --------
 */

export class PayloadBuilder {
  /**
   * Build a canonical payload string from an event name and attributes.
   */
  build(eventName: string, attributes: Record<string, unknown>): string {
    if (!eventName) {
      throw new Error('eventName is required');
    }

    const lines: string[] = [];

    for (const [key, rawValue] of Object.entries(attributes)) {
      if (rawValue === undefined || rawValue === null) continue;

      let value: string;
      if (Array.isArray(rawValue)) {
        value = rawValue.join(', ');
      } else if (typeof rawValue === 'object') {
        try {
          value = JSON.stringify(rawValue);
        } catch {
          value = String(rawValue);
        }
      } else {
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
}
