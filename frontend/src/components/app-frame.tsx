"use client";

import { usePathname } from "next/navigation";

import { AuthProvider } from "@/components/auth-provider";
import { Shell } from "@/components/shell";
import { StreamProvider } from "@/components/stream";

const PUBLIC = new Set(["/login", "/register"]);

export function AppFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (PUBLIC.has(pathname)) {
    return children;
  }
  return (
    <AuthProvider>
      <StreamProvider>
        <Shell>{children}</Shell>
      </StreamProvider>
    </AuthProvider>
  );
}
