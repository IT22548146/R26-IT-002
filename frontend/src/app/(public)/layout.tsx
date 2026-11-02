"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Factory, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

const NAV = [
  { name: "Home", href: "/" },
  { name: "About Us", href: "/about" },
  { name: "Our Services", href: "/services" },
  { name: "Contact Us", href: "/contact" },
];

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, logout } = useAuth();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href.replace(/#.*$/, "")) && href !== "/#services";

  return (
    <div className="min-h-screen flex flex-col bg-white text-slate-800">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="h-9 w-9 bg-slate-900 rounded-lg flex items-center justify-center">
              <Factory className="h-5 w-5 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight text-slate-900">FabricFlow</span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1">
            {NAV.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "px-3 py-2 text-sm font-medium rounded-md transition-colors",
                  isActive(item.href) ? "text-blue-600" : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                )}
              >
                {item.name}
              </Link>
            ))}
          </nav>

          <div className="hidden md:flex items-center gap-2">
            {user ? (
              <div className="flex items-center gap-4">
                <Link
                  href={(user.role === "Admin" || user.role === "Manager") ? "/admin" : user.role === "Buyer" ? "/buyer" : "/plant"}
                  className="text-sm font-medium text-slate-700 hover:text-slate-900"
                >
                  Dashboard
                </Link>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-900">{user.full_name}</span>
                  <button
                    onClick={logout}
                    className="px-3 py-1.5 text-sm font-medium text-slate-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    Logout
                  </button>
                </div>
              </div>
            ) : (
              <>
                <Link href="/login" className="px-4 py-2 text-sm font-medium text-slate-700 hover:text-slate-900">
                  Sign In
                </Link>
                <Link
                  href="/register"
                  className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
                >
                  Register
                </Link>
              </>
            )}
          </div>

          {/* Mobile toggle */}
          <button
            className="md:hidden p-2 text-slate-600 hover:text-slate-900"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="Toggle menu"
          >
            {menuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile menu */}
        {menuOpen && (
          <div className="md:hidden border-t border-slate-200 bg-white px-4 py-3 space-y-1">
            {NAV.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className="block px-3 py-2 text-sm font-medium text-slate-700 rounded-md hover:bg-slate-50"
              >
                {item.name}
              </Link>
            ))}
            <div className="pt-2 flex flex-col gap-2">
              {user ? (
                <>
                  <Link 
                    href={(user.role === "Admin" || user.role === "Manager") ? "/admin" : user.role === "Buyer" ? "/buyer" : "/plant"} 
                    onClick={() => setMenuOpen(false)} 
                    className="block px-3 py-2 text-sm font-medium text-slate-700 rounded-md hover:bg-slate-50"
                  >
                    Dashboard
                  </Link>
                  <div className="flex items-center justify-between px-3 py-2 mt-2 border-t border-slate-100">
                     <span className="text-sm font-medium text-slate-900">{user.full_name}</span>
                     <button
                        onClick={() => {
                          logout();
                          setMenuOpen(false);
                        }}
                        className="text-sm font-medium text-red-600"
                     >
                       Logout
                     </button>
                  </div>
                </>
              ) : (
                <div className="flex gap-2 w-full mt-2">
                  <Link href="/login" onClick={() => setMenuOpen(false)} className="flex-1 text-center px-4 py-2 text-sm font-medium text-slate-700 border border-slate-200 rounded-lg">
                    Sign In
                  </Link>
                  <Link href="/register" onClick={() => setMenuOpen(false)} className="flex-1 text-center px-4 py-2 text-sm font-semibold text-white bg-blue-600 rounded-lg">
                    Register
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}
      </header>

      {/* Page content */}
      <main className="flex-1">{children}</main>

      {/* Footer */}
      <footer className="bg-slate-900 text-slate-300 mt-auto">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12 grid gap-8 md:grid-cols-4">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2 mb-3">
              <Factory className="h-5 w-5 text-white" />
              <span className="font-bold text-white">FabricFlow</span>
            </div>
            <p className="text-sm text-slate-400 max-w-sm">
              AI-driven decision support for garment production — from sample feasibility
              to bulk allocation across our factory network.
            </p>
          </div>
          <div>
            <h4 className="text-white font-semibold text-sm mb-3">Company</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/about" className="hover:text-white">About Us</Link></li>
              <li><Link href="/services" className="hover:text-white">Our Services</Link></li>
              <li><Link href="/contact" className="hover:text-white">Contact Us</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-white font-semibold text-sm mb-3">Legal</h4>
            <ul className="space-y-2 text-sm">
              <li><Link href="/privacy" className="hover:text-white">Privacy Policy</Link></li>
              <li><Link href="/terms" className="hover:text-white">Terms &amp; Conditions</Link></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-slate-800 py-6 text-center text-sm text-slate-500">
          &copy; {new Date().getFullYear()} FabricFlow International. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
