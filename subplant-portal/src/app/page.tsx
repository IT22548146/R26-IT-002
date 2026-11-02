"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => { router.replace("/portal"); }, [router]);
  return (
    <div className="min-h-screen flex items-center justify-center text-slate-500">
      Loading Sub Plant Portal...
    </div>
  );
}
