import type { Metadata } from "next";
import { Inter, Spectral } from "next/font/google";
import "./globals.css";

const spectral = Spectral({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-spectral",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Grad Connect",
  description:
    "Find professors whose published research matches your interests — every match backed by text from their own pages.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${spectral.variable} ${inter.variable}`}>
      <body>
        <div className="container">
          <header className="masthead">
            <h1>
              <a href="/">Grad Connect</a>
            </h1>
            <p>
              Search professors by research topic. Every result cites text from
              the professor&apos;s own pages.
            </p>
            <nav className="site-nav" aria-label="Main">
              <a href="/match">Match my resume</a>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
