"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import api from "@/lib/api";

export type Role = "Admin" | "Buyer" | "PlantManager" | "Manager";

// Admin-panel routes a Manager may NOT open (they belong to the Admin only).
const MANAGER_BLOCKED = ["/admin/users", "/admin/performance"];

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  org_id?: number;
  org_name?: string;
  plant_id?: string;
  status: string;
  contact_no?: string;
  country?: string;
  address?: string;
  profile_pic_path?: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem("token");
      if (token) {
        try {
          const res = await api.get("/auth/me");
          setUser(res.data);
        } catch (error) {
          console.error("Auth check failed:", error);
          localStorage.removeItem("token");
          setUser(null);
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  // Protect routes based on role
  useEffect(() => {
    if (loading) return;

    // Auth pages: bounce a logged-in user to their dashboard.
    const authPages = ["/login", "/register"];
    // Public marketing pages: viewable by everyone, logged in or not.
    const publicPages = ["/", "/about", "/services", "/contact", "/privacy", "/terms"];
    const isAuthPage = authPages.includes(pathname);
    const isPublic = isAuthPage || publicPages.includes(pathname);

    if (!user && !isPublic) {
      router.push("/login");
      return;
    }

    if (user && isAuthPage) {
      if (user.role === "Admin" || user.role === "Manager") router.push("/admin");
      else if (user.role === "Buyer") router.push("/buyer");
      else if (user.role === "PlantManager") router.push("/plant");
      return;
    }

    // Role-based route protection. Admin + Manager both live in /admin, but a
    // Manager is bounced off the user-management and performance sub-routes.
    if (user && pathname.startsWith("/admin")) {
      if (user.role !== "Admin" && user.role !== "Manager") {
        router.push(`/${user.role.toLowerCase()}`);
      } else if (user.role === "Manager" && MANAGER_BLOCKED.some((p) => pathname === p || pathname.startsWith(p + "/"))) {
        router.push("/admin");
      }
    } else if (user && pathname.startsWith("/buyer") && user.role !== "Buyer") {
      router.push(`/${user.role.toLowerCase()}`);
    } else if (user && pathname.startsWith("/plant") && user.role !== "PlantManager") {
      router.push(`/${user.role.toLowerCase() === 'plantmanager' ? 'plant' : user.role.toLowerCase()}`);
    }
  }, [user, loading, pathname, router]);

  const login = async (token: string) => {
    localStorage.setItem("token", token);
    const res = await api.get("/auth/me");
    setUser(res.data);
    
    // Redirect based on role
    if (res.data.role === "Admin" || res.data.role === "Manager") router.push("/admin");
    else if (res.data.role === "Buyer") router.push("/buyer");
    else if (res.data.role === "PlantManager") router.push("/plant");
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
    router.push("/login");
  };

  const refreshUser = async () => {
    try {
      const res = await api.get("/auth/me");
      setUser(res.data);
    } catch {
      // ignore — a failed refresh leaves the existing user in place
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
