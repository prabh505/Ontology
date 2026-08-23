import type { ReactNode } from 'react';

export const metadata = {
  title: 'CausaLog',
  description: 'A domain-agnostic causal intelligence engine.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
