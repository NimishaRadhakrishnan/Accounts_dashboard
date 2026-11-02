import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "./globals.css";

export const metadata: Metadata = {
  title: "Accounts · Vishakan Bio Tech",
  description: "Accounts department dashboard",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className="h-full antialiased">
      <body className="min-h-full bg-page text-ink">{children}</body>
    </html>
  );
}
