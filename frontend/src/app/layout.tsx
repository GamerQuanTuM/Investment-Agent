import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { AppNav } from "@/components/AppNav";
import { Footer } from "@/components/Footer";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MudraLens | AI Investment Research & Portfolio Guidance",
  description: "Evidence-based, disciplined Indian equity and mutual fund research agent with multi-model LLM routing, dialectic bull/bear stress-testing, and live INDmoney broker integration.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body className="flex min-h-screen flex-col bg-[#f6f7fb] text-[#0f1629] antialiased selection:bg-blue-100 selection:text-blue-900">
        <Providers>
          <AppNav />
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
