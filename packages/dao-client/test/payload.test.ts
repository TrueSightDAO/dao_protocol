import { describe, it, expect } from 'vitest';
import { PayloadBuilder } from '../src/payload';
import vectors from './vectors/submit-event-vectors.json';

describe('PayloadBuilder', () => {
  describe('build() — v1.0.x compatible', () => {
    it('builds a basic event payload', () => {
      const builder = new PayloadBuilder();
      const result = builder.build('CONTRIBUTION EVENT', {
        Type: 'Time (Minutes)',
        Amount: '40',
      });
      expect(result).toBe(
        '[CONTRIBUTION EVENT]\n' +
        '- Type: Time (Minutes)\n' +
        '- Amount: 40\n' +
        '--------'
      );
    });

    it('builds an event with array values', () => {
      const builder = new PayloadBuilder();
      const result = builder.build('PRACTICE EVENT', {
        Program: 'capoeira-tribo-mirim',
        'Moves Practiced': ['ginga', 'au', 'cocorinha'],
      });
      expect(result).toBe(
        '[PRACTICE EVENT]\n' +
        '- Program: capoeira-tribo-mirim\n' +
        '- Moves Practiced: ginga, au, cocorinha\n' +
        '--------'
      );
    });

    it('indents multi-line values', () => {
      const builder = new PayloadBuilder();
      const result = builder.build('NOTE EVENT', {
        Description: 'Line one\nLine two\nLine three',
      });
      expect(result).toBe(
        '[NOTE EVENT]\n' +
        '- Description: Line one\n' +
        '  Line two\n' +
        '  Line three\n' +
        '--------'
      );
    });

    it('skips null and undefined fields', () => {
      const builder = new PayloadBuilder();
      const result = builder.build('TEST EVENT', {
        Name: 'test',
        NullField: null,
        UndefinedField: undefined,
      });
      expect(result).toBe(
        '[TEST EVENT]\n' +
        '- Name: test\n' +
        '--------'
      );
    });

    it('stringifies numeric values', () => {
      const builder = new PayloadBuilder();
      const result = builder.build('TREE PLANTING EVENT', {
        Latitude: -23.5505,
        'Trees Planted': 5,
      });
      expect(result).toBe(
        '[TREE PLANTING EVENT]\n' +
        '- Latitude: -23.5505\n' +
        '- Trees Planted: 5\n' +
        '--------'
      );
    });

    it('stringifies boolean values', () => {
      const builder = new PayloadBuilder();
      const result = builder.build('FLAG EVENT', {
        Active: true,
        Verified: false,
      });
      expect(result).toBe(
        '[FLAG EVENT]\n' +
        '- Active: true\n' +
        '- Verified: false\n' +
        '--------'
      );
    });

    it('JSON-stringifies object values', () => {
      const builder = new PayloadBuilder();
      const result = builder.build('CONFIG EVENT', {
        Settings: { theme: 'dark', notifications: true },
      });
      expect(result).toBe(
        '[CONFIG EVENT]\n' +
        '- Settings: {"theme":"dark","notifications":true}\n' +
        '--------'
      );
    });

    it('throws on empty event name', () => {
      const builder = new PayloadBuilder();
      expect(() => builder.build('', {})).toThrow('eventName is required');
    });

    it('produces canonical format that matches Ruby SignatureVerifier contract', () => {
      // The Ruby verifier does:
      //   message = lines[0..separator_index].join("\n")
      //   message_to_sign = message.strip
      //
      // Our output has no trailing newline, so .strip() is a no-op.
      // This test asserts the exact byte sequence the Ruby verifier will sign.
      const builder = new PayloadBuilder();
      const result = builder.build('TEST EVENT', { Key: 'value' });
      
      // Should end with -------- (no trailing newline)
      expect(result.endsWith('--------')).toBe(true);
      
      // Should contain the event header
      expect(result.startsWith('[TEST EVENT]\n')).toBe(true);
      
      // Should contain the field
      expect(result).toContain('- Key: value');
      
      // The Ruby verifier's message_to_sign = result (since .strip() is a no-op)
      // Verify: no leading/trailing whitespace
      expect(result).toBe(result.trim());
    });
  });

  describe('buildSubmitEvent() — v1.1.0', () => {
    it('auto-injects Timestamp as the first field', () => {
      const builder = new PayloadBuilder();
      const fixedTs = '2026-06-07T12:00:00.000Z';
      const result = builder.buildSubmitEvent('CONTRIBUTION EVENT', {
        Type: 'Time (Minutes)',
        Amount: '40',
      }, fixedTs);
      
      // Timestamp should be the first field after the header
      const lines = result.split('\n');
      expect(lines[0]).toBe('[CONTRIBUTION EVENT]');
      expect(lines[1]).toBe(`- Timestamp: ${fixedTs}`);
      expect(lines[2]).toBe('- Type: Time (Minutes)');
      expect(lines[3]).toBe('- Amount: 40');
      expect(lines[4]).toBe('--------');
    });

    it('generates current timestamp when not provided', () => {
      const builder = new PayloadBuilder();
      const before = new Date();
      const result = builder.buildSubmitEvent('TEST EVENT', { Key: 'value' });
      const after = new Date();
      
      // Extract the timestamp from the result
      const match = result.match(/- Timestamp: (.+)$/m);
      expect(match).not.toBeNull();
      const ts = new Date(match![1]);
      expect(ts.getTime()).toBeGreaterThanOrEqual(before.getTime() - 1000);
      expect(ts.getTime()).toBeLessThanOrEqual(after.getTime() + 1000);
    });

    it('rejects field values containing [CONTRIBUTION EVENT]', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.buildSubmitEvent('TEST EVENT', {
          Notes: 'See [CONTRIBUTION EVENT] notes',
        });
      }).toThrow(/Field 'Notes' contains a bracketed event tag/);
    });

    it('rejects field values containing [PRACTICE EVENT]', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.buildSubmitEvent('TEST EVENT', {
          Notes: 'See [PRACTICE EVENT] for details',
        });
      }).toThrow(/Field 'Notes' contains a bracketed event tag/);
    });

    it('rejects on the first offending field', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.buildSubmitEvent('TEST EVENT', {
          Title: 'Safe value',
          Notes: 'See [PRACTICE EVENT] for details',
          Reference: 'Also [CONTRIBUTION EVENT]',
        });
      }).toThrow(/Field 'Notes' contains a bracketed event tag/);
    });

    it('allows safe values through', () => {
      const builder = new PayloadBuilder();
      const result = builder.buildSubmitEvent('TEST EVENT', {
        Name: 'Safe value',
        Description: 'No brackets here',
      });
      expect(result).toContain('- Name: Safe value');
      expect(result).toContain('- Description: No brackets here');
    });

    it('matches all test vectors', () => {
      const builder = new PayloadBuilder();
      
      for (const vector of vectors) {
        if (vector.expectedError) {
          // Should throw
          expect(() => {
            builder.buildSubmitEvent(vector.eventType, vector.fields as Record<string, unknown>);
          }).toThrow(vector.expectedError);
        } else {
          // Should match the pattern
          // Convert \n in JSON strings to actual newlines
          const fields = JSON.parse(JSON.stringify(vector.fields), (key, val) =>
            typeof val === 'string' ? val.replace(/\\n/g, '\n') : val
          );
          const result = builder.buildSubmitEvent(
            vector.eventType,
            fields as Record<string, unknown>
          );
          const pattern = new RegExp(vector.expectedCanonicalPattern);
          expect(result).toMatch(pattern);
        }
      }
    });
  });

  describe('validateFieldValues()', () => {
    it('passes clean values', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.validateFieldValues({ Name: 'test', Value: '123' });
      }).not.toThrow();
    });

    it('rejects [CONTRIBUTION EVENT] in value', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.validateFieldValues({ Notes: 'See [CONTRIBUTION EVENT]' });
      }).toThrow(/bracketed event tag/);
    });

    it('rejects [practice event] (case-insensitive)', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.validateFieldValues({ Notes: 'See [practice event]' });
      }).toThrow(/bracketed event tag/);
    });

    it('rejects [EMAIL REGISTERED EVENT] in value', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.validateFieldValues({ Notes: 'See [EMAIL REGISTERED EVENT]' });
      }).toThrow(/bracketed event tag/);
    });

    it('skips null and undefined values', () => {
      const builder = new PayloadBuilder();
      expect(() => {
        builder.validateFieldValues({ Name: null, Notes: undefined });
      }).not.toThrow();
    });
  });
});
