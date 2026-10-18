"use client";

import { useAuth } from "@/contexts/AuthContext";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useState, useRef, useEffect } from "react";
import {
  LayoutDashboard, Users, ClipboardList, Truck, Receipt, TrendingUp,
  LogOut, Factory, Menu, X, UserCircle,
} from "lucide-react";

const NAV = [
  { name: "Dashboard", href: "/portal", icon: LayoutDashboard },
  { name: "Customers", href: "/portal/customers", icon: Users },
  { name: "Orders", href: "/portal/orders", icon: ClipboardList },
  { name: "Gatepass", href: "/portal/gatepass", icon: Truck },
  { name: "Invoices", href: "/portal/invoices", icon: Receipt },
  { name: "My Performance", href: "/portal/performance", icon: TrendingUp },
];

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const { user, plant, logout, loading } = useAuth();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-500">
        Loading...
      </div>
    );
  }

  const isActive = (href: string) =>
    href === "/portal" ? pathname === "/portal" : pathname === href || pathname.startsWith(href + "/");

  const current = NAV.find((n) => isActive(n.href))?.name || "Dashboard";

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {sidebarOpen && (
        <div className="fixed inset-0 z-20 bg-slate-900/50 backdrop-blur-sm md:hidden"
             onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar — teal identity so the portal reads as its own workspace */}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-30 w-64 bg-teal-950 text-slate-300 flex flex-col transition-transform duration-300 md:relative md:translate-x-0",
        sidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="h-16 flex items-center justify-between px-6 border-b border-white/10">
          <div className="flex items-center min-w-0">
            <Factory className="h-6 w-6 mr-2 text-teal-300 shrink-0" />
            <span className="text-white font-bold text-lg tracking-tight truncate">Sub Plant</span>
          </div>
          <button className="md:hidden text-white/60 hover:text-white" onClick={() => setSidebarOpen(false)}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-6 px-3 space-y-1.5">
          {NAV.map((item) => (
            <Link
              key={item.name}
              href={item.href}
              onClick={() => setSidebarOpen(false)}
              className={cn(
                "group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors",
                isActive(item.href)
                  ? "bg-teal-600 text-white"
                  : "text-white/70 hover:bg-teal-900/60 hover:text-white"
              )}
            >
              <item.icon className={cn("mr-3 h-5 w-5 shrink-0",
                isActive(item.href) ? "text-white" : "text-white/50 group-hover:text-white")} />
              {item.name}
            </Link>
          ))}
        </nav>

        <div className="px-4 py-3 border-t border-white/10">
          <p className="text-xs font-medium uppercase tracking-wider text-teal-300 truncate">
            {plant?.name || "Sub Plant"}
          </p>
          <p className="text-[11px] text-white/40 truncate">{plant?.location || ""}</p>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-16 bg-white border-b border-slate-200 flex items-center px-4 md:px-8 shrink-0 shadow-sm relative z-40">
          <button className="md:hidden p-2 mr-3 text-slate-500 hover:text-slate-900 rounded-md hover:bg-slate-100"
                  onClick={() => setSidebarOpen(true)}>
            <Menu className="w-6 h-6" />
          </button>
          <h1 className="flex-1 text-lg md:text-xl font-semibold text-slate-800 truncate">{current}</h1>

          <div className="flex items-center gap-3">
            <span className="hidden sm:inline text-xs md:text-sm font-medium text-slate-500 bg-slate-100 px-3 py-1 rounded-full truncate max-w-[12rem]">
              {plant?.name || user.full_name}
            </span>
            <div className="relative" ref={profileRef}>
              <button onClick={() => setProfileOpen(!profileOpen)}
                      className="flex items-center p-1.5 rounded-full hover:bg-slate-100 transition-colors">
                <div className="bg-teal-700 text-white rounded-full w-8 h-8 flex items-center justify-center">
                  <UserCircle className="w-5 h-5" />
                </div>
              </button>
              {profileOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-[60]">
                  <div className="px-4 py-3 border-b border-slate-100 mb-2">
                    <p className="text-sm font-semibold text-slate-900 truncate">{user.full_name}</p>
                    <p className="text-xs text-slate-500 truncate">{user.email}</p>
                  </div>
                  <div className="px-2">
                    <button onClick={logout}
                            className="w-full text-left flex items-center px-3 py-2 text-sm text-red-600 font-medium rounded-lg hover:bg-red-50 transition-colors">
                      <LogOut className="w-4 h-4 mr-2" /> Sign Out
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="p-4 md:p-8 max-w-7xl mx-auto">{children}</div>
        </div>
      </main>
    </div>
  );
}
