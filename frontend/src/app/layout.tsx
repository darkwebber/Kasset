import type { Metadata } from "next";
import { VT323, Fira_Code } from "next/font/google";
import "./globals.css";

const vt323 = VT323({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-vt323",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  variable: "--font-fira-code",
});

export const metadata: Metadata = {
  title: "Cartridge Console | Qwen Studio",
  description: "A retro-futuristic AI interface powered by Qwen 3.5.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${vt323.variable} ${firaCode.variable} font-sans`}>
        {children}
      </body>
    </html>
  );
}
