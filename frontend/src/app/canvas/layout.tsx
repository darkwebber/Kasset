import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kasset — Image Canvas",
  description: "Pop-out image editing canvas",
};

export default function CanvasLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen w-screen bg-[#0a0a0a] overflow-hidden">
      {children}
    </div>
  );
}
