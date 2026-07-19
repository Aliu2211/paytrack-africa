import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
// Imported here (root layout), after globals.css, so cascade order relative
// to Tailwind's reset is predictable. Importing it from a nested component
// (as it was originally) left the order up to the bundler's module graph,
// which broke the Authenticator's default centered-card layout.
import "@aws-amplify/ui-react/styles.css";
import ConfigureAmplify from "@/components/ConfigureAmplify";
import AppShell from "@/components/AppShell";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PayTrack Africa",
  description: "Invoice and payment tracking for Ghanaian SMEs",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ConfigureAmplify />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
