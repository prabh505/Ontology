import { FlatCompat } from '@eslint/eslintrc';

// eslint-config-next still ships eslintrc-style configuration, so ESLint 9's flat config
// reaches it through FlatCompat. This is Next.js's own documented bridge, not a workaround
// of our own invention.
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

/** @type {import('eslint').Linter.Config[]} */
const config = [
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'] },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      // Provenance classes must survive into the UI visually distinct (LAW-PROVENANCE).
      // An `any` on a response type is exactly how a provenance_class field goes missing
      // without anyone noticing.
      '@typescript-eslint/no-explicit-any': 'error',
    },
  },
];

export default config;
