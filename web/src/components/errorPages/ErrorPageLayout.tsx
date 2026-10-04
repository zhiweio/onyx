import React from "react";
import { Logo } from "@/lib/app/components";

interface ErrorPageLayoutProps {
  children: React.ReactNode;
}

export default function ErrorPageLayout({ children }: ErrorPageLayoutProps) {
  return (
    <div className="flex flex-col items-center justify-center w-full h-screen gap-4">
      {/* White-label aware: renders the enterprise logo/name when branded. */}
      <Logo size={44} />
      <div className="max-w-160 w-full border bg-background-neutral-00 shadow-box-02 rounded-16 p-6 flex flex-col gap-4">
        {children}
      </div>
    </div>
  );
}
