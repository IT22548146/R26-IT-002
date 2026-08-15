"use client";

import { useAuth } from "@/contexts/AuthContext";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useState, useRef, useEffect } from "react";
import { 
  LayoutDashboard, 
  Users, 
  Package, 
  BarChart3, 
  ClipboardList, 
  Bell, 
  LogOut,
  Factory,
  Menu,
  X,
  UserCircle,
  Shirt,
  Activity,
  TrendingUp,
  Building2
} from "lucide-react";

type NavItem = {
  name: string;
  href: string;
  icon: any;
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, logout, loading } = useAuth();
  const pathname = usePathname();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setIsProfileOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (loading || !user) {
    return <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-500">Loading...</div>;
  }

  const navigation: Record<string, NavItem[]> = {
    Admin: [
      { name: "Dashboard", href: "/admin", icon: LayoutDashboard },
      { name: "Users", href: "/admin/users", icon: Users },
      { name: "Sample Orders", href: "/admin/samples", icon: ClipboardList },
      { name: "Bulk Orders", href: "/admin/bulk", icon: Package },
      { name: "Email Replies", href: "/admin/email-replies", icon: Bell },
      { name: "Performance", href: "/admin/performance", icon: Activity },
      { name: "Plant Analytics", href: "/admin/analytics", icon: TrendingUp },
      { name: "Sub Plants", href: "/admin/sub-plants", icon: Building2 },
      { name: "Capacity", href: "/admin/capacity", icon: BarChart3 },
      { name: "Styles Directory", href: "/admin/styles", icon: Shirt },
      { name: "Style Reviews", href: "/admin/style-submissions", icon: Shirt },
    ],
    // Manager: the admin panel minus Users and Performance.
    Manager: [
      { name: "Dashboard", href: "/admin", icon: LayoutDashboard },
      { name: "Sample Orders", href: "/admin/samples", icon: ClipboardList },
      { name: "Bulk Orders", href: "/admin/bulk", icon: Package },
      { name: "Email Replies", href: "/admin/email-replies", icon: Bell },
      { name: "Plant Analytics", href: "/admin/analytics", icon: TrendingUp },
      { name: "Sub Plants", href: "/admin/sub-plants", icon: Building2 },
      { name: "Capacity", href: "/admin/capacity", icon: BarChart3 },
      { name: "Styles Directory", href: "/admin/styles", icon: Shirt },
      { name: "Style Reviews", href: "/admin/style-submissions", icon: Shirt },
    ],
    Buyer: [
      { name: "Dashboard", href: "/buyer", icon: LayoutDashboard },
      { name: "Sample Orders", href: "/buyer/samples", icon: ClipboardList },
      { name: "Bulk Orders", href: "/buyer/bulk", icon: Package },
      { name: "My Styles", href: "/buyer/styles", icon: Shirt },
      { name: "Notifications", href: "/buyer/notifications", icon: Bell },
    ],
    PlantManager: [
      { name: "Dashboard", href: "/plant", icon: LayoutDashboard },
      { name: "Bulk Orders", href: "/plant/orders", icon: Package },
      { name: "Sample Orders", href: "/plant/samples", icon: ClipboardList },
      { name: "Style Reviews", href: "/plant/style-submissions", icon: Shirt },
      { name: "Notifications", href: "/plant/notifications", icon: Bell },
    ],
  };

  const navItems = navigation[user.role] || [];

  // Per-role visual identity so each area reads as its own workspace.
  const THEME: Record<string, { sidebar: string; active: string; hover: string; logo: string; accent: string }> = {
    Admin:        { sidebar: "bg-slate-950", active: "bg-slate-700 text-white", hover: "hover:bg-slate-800/70 hover:text-white", logo: "text-slate-300", accent: "text-slate-300" },
    Manager:      { sidebar: "bg-violet-950", active: "bg-violet-600 text-white", hover: "hover:bg-violet-900/60 hover:text-white", logo: "text-violet-300", accent: "text-violet-300" },
    Buyer:        { sidebar: "bg-blue-950",  active: "bg-blue-600 text-white",  hover: "hover:bg-blue-900/60 hover:text-white",  logo: "text-blue-300",  accent: "text-blue-300" },
    PlantManager: { sidebar: "bg-emerald-950", active: "bg-emerald-600 text-white", hover: "hover:bg-emerald-900/60 hover:text-white", logo: "text-emerald-300", accent: "text-emerald-300" },
  };
  const theme = THEME[user.role] || THEME.Admin;

  const isActive = (href: string) =>
    href === "/buyer" ? pathname === "/buyer" : pathname === href || pathname.startsWith(href + "/");

  // ── Customer (Buyer) experience — feels like the public website, not an admin panel ──
  if (user.role === "Buyer") {
    return (
      <div className="min-h-screen flex flex-col bg-white text-slate-800">
        {/* Website-style top navigation */}
        <header className="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
            <Link href="/buyer" className="flex items-center gap-2">
              <div className="h-9 w-9 bg-blue-600 rounded-lg flex items-center justify-center">
                <Factory className="h-5 w-5 text-white" />
              </div>
              <span className="font-bold text-lg tracking-tight text-slate-900">FabricFlow</span>
            </Link>

            {/* Desktop nav */}
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    "px-3 py-2 text-sm font-medium rounded-md transition-colors",
                    isActive(item.href) ? "text-blue-600 bg-blue-50" : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                  )}
                >
                  {item.name}
                </Link>
              ))}
            </nav>

            {/* Right actions */}
            <div className="flex items-center gap-2">
              <Link href="/buyer/notifications" className="hidden sm:flex p-2 rounded-full text-slate-500 hover:text-blue-600 hover:bg-slate-50 transition-colors" aria-label="Notifications">
                <Bell className="w-5 h-5" />
              </Link>
              <div className="relative" ref={profileRef}>
                <button
                  onClick={() => setIsProfileOpen(!isProfileOpen)}
                  className="flex items-center gap-2 p-1.5 pr-3 rounded-full hover:bg-slate-50 transition-colors focus:outline-none"
                >
                  <div className="bg-blue-600 text-white rounded-full w-8 h-8 flex items-center justify-center">
                    <UserCircle className="w-5 h-5" />
                  </div>
                  <span className="hidden sm:inline text-sm font-medium text-slate-700 max-w-[8rem] truncate">{user.full_name}</span>
                </button>
                {isProfileOpen && (
                  <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-[60]">
                    <div className="px-4 py-3 border-b border-slate-100 mb-2">
                      <p className="text-sm font-semibold text-slate-900 truncate">{user.full_name}</p>
                      <p className="text-xs text-slate-500 truncate">{user.email}</p>
                    </div>
                    <div className="px-2 space-y-1">
                      <Link href="/profile" onClick={() => setIsProfileOpen(false)} className="w-full text-left flex items-center px-3 py-2 text-sm text-slate-700 font-medium rounded-lg hover:bg-slate-50 transition-colors">
                        <UserCircle className="w-4 h-4 mr-2" /> My Profile
                      </Link>
                      <button onClick={logout} className="w-full text-left flex items-center px-3 py-2 text-sm text-red-600 font-medium rounded-lg hover:bg-red-50 transition-colors">
                        <LogOut className="w-4 h-4 mr-2" /> Sign Out
                      </button>
                    </div>
                  </div>
                )}
              </div>
              {/* Mobile toggle */}
              <button className="md:hidden p-2 text-slate-600 hover:text-slate-900" onClick={() => setIsSidebarOpen((v) => !v)} aria-label="Toggle menu">
                {isSidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
              </button>
            </div>
          </div>

          {/* Mobile menu */}
          {isSidebarOpen && (
            <div className="md:hidden border-t border-slate-200 bg-white px-4 py-3 space-y-1">
              {navItems.map((item) => (
                <Link
                  key={item.name}
                  href={item.href}
                  onClick={() => setIsSidebarOpen(false)}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md",
                    isActive(item.href) ? "text-blue-600 bg-blue-50" : "text-slate-700 hover:bg-slate-50"
                  )}
                >
                  <item.icon className="w-4 h-4" /> {item.name}
                </Link>
              ))}
            </div>
          )}
        </header>

        {/* Page content */}
        <main className="flex-1">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">{children}</div>
        </main>

        {/* Website footer */}
        <footer className="bg-slate-900 text-slate-300 mt-auto">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Factory className="h-5 w-5 text-white" />
              <span className="font-bold text-white">FabricFlow</span>
            </div>
            <div className="flex items-center gap-6 text-sm">
              <Link href="/about" className="hover:text-white">About</Link>
              <Link href="/services" className="hover:text-white">Services</Link>
              <Link href="/contact" className="hover:text-white">Contact</Link>
              <Link href="/privacy" className="hover:text-white">Privacy</Link>
            </div>
            <p className="text-xs text-slate-500">&copy; {new Date().getFullYear()} FabricFlow International</p>
          </div>
        </footer>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">

      {/* Mobile sidebar overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-slate-900/50 backdrop-blur-sm md:hidden transition-opacity"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-30 w-64 text-slate-300 flex flex-col transition-transform duration-300 ease-in-out md:relative md:translate-x-0",
        theme.sidebar,
        isSidebarOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="h-16 flex items-center justify-between px-6 border-b border-white/10">
          <div className="flex items-center">
            <Factory className={cn("h-6 w-6 mr-2", theme.logo)} />
            <span className="text-white font-bold text-lg tracking-tight">FabricFlow</span>
          </div>
          <button className="md:hidden text-white/60 hover:text-white" onClick={() => setIsSidebarOpen(false)}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-6 px-3 space-y-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + '/');

            return (
              <Link
                key={item.name}
                href={item.href}
                onClick={() => setIsSidebarOpen(false)}
                className={cn(
                  "group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors",
                  isActive ? theme.active : cn("text-white/70", theme.hover)
                )}
              >
                <item.icon className={cn("mr-3 flex-shrink-0 h-5 w-5", isActive ? "text-white" : "text-white/50 group-hover:text-white")} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Role badge */}
        <div className="px-4 py-3 border-t border-white/10">
          <span className={cn("text-xs font-medium uppercase tracking-wider", theme.accent)}>
            {user.role === "PlantManager" ? "Plant Workspace" : `${user.role} Workspace`}
          </span>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* Top Navigation Bar */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center px-4 md:px-8 z-40 shadow-sm shrink-0">
          <button 
            className="md:hidden p-2 mr-4 text-slate-500 hover:text-slate-900 rounded-md hover:bg-slate-100"
            onClick={() => setIsSidebarOpen(true)}
          >
            <Menu className="w-6 h-6" />
          </button>
          
          <div className="flex-1">
            <h1 className="text-lg md:text-xl font-semibold text-slate-800 truncate">
              {navItems.find((item) => pathname === item.href || pathname.startsWith(item.href + '/'))?.name || "Dashboard"}
            </h1>
          </div>
          
          <div className="flex items-center space-x-4 ml-4">
             <span className="hidden sm:inline-block text-xs md:text-sm font-medium text-slate-500 bg-slate-100 px-3 py-1 rounded-full whitespace-nowrap">
               {user.full_name}
             </span>
             
             {/* Profile Dropdown */}
             <div className="relative" ref={profileRef}>
               <button 
                 onClick={() => setIsProfileOpen(!isProfileOpen)}
                 className="flex items-center space-x-2 p-1.5 rounded-full hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-200"
               >
                 <div className="bg-slate-900 text-white rounded-full w-8 h-8 flex items-center justify-center">
                   <UserCircle className="w-5 h-5" />
                 </div>
               </button>
               
               {isProfileOpen && (
                 <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-[60]">
                   <div className="px-4 py-3 border-b border-slate-100 mb-2">
                     <p className="text-sm font-semibold text-slate-900 truncate">{user.full_name}</p>
                     <p className="text-xs text-slate-500 truncate">{user.email}</p>
                   </div>
                   <div className="px-2 space-y-1">
                     <Link
                       href="/profile"
                       onClick={() => setIsProfileOpen(false)}
                       className="w-full text-left flex items-center px-3 py-2 text-sm text-slate-700 font-medium rounded-lg hover:bg-slate-50 transition-colors"
                     >
                       <UserCircle className="w-4 h-4 mr-2" />
                       My Profile
                     </Link>
                     <button
                       onClick={logout}
                       className="w-full text-left flex items-center px-3 py-2 text-sm text-red-600 font-medium rounded-lg hover:bg-red-50 transition-colors"
                     >
                       <LogOut className="w-4 h-4 mr-2" />
                       Sign Out
                     </button>
                   </div>
                 </div>
               )}
             </div>
          </div>
        </header>

        {/* Page Content & Footer Wrapper */}
        <div className="flex-1 overflow-y-auto bg-slate-50/50 flex flex-col">
          <div className="p-4 md:p-8 flex-1">
            <div className="max-w-7xl mx-auto">
              {children}
            </div>
          </div>
          
          {/* Footer */}
          <footer className="border-t border-slate-200 py-6 px-8 text-center text-sm text-slate-500 shrink-0">
            <p>&copy; {new Date().getFullYear()} FabricFlow Garment Production System. All rights reserved.</p>
          </footer>
        </div>
      </main>
    </div>
  );
}
