"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import api from "@/lib/api";

export interface SubPlantUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
  plant_id?: string;
  status: string;
  org_name?: string;
}

export interface SubPlant {
  id?: number;
  plant_id?: string;
  name: string;
  location?: string | null;
}

interface AuthContextType {
  user: SubPlantUser | null;
  plant: SubPlant | null;
  loading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// This portal serves sub plants only. Any other role is bounced back to login.
const REQUIRED_ROLE = "SubPlant";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SubPlantUser | null>(null);
  const [plant, setPlant] = useState<SubPlant | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const loadPlant = async () => {
    try {
      const res = await api.get("/subplant/me");
      setPlant(res.data.plant);
    } catch {
      setPlant(null);
    }
  };

  useEffect(() => {
    const init = async () => {
      const token = localStorage.getItem("sp_token");
      if (token) {
        try {
          const res = await api.get("/auth/me");
          if (res.data.role !== REQUIRED_ROLE) {
            localStorage.removeItem("sp_token");
            setUser(null);
          } else {
            setUser(res.data);
            await loadPlant();
          }
        } catch {
          localStorage.removeItem("sp_token");
          setUser(null);
        }
      }
      setLoading(false);
    };
    init();
  }, []);

  // Route guard: everything except /login needs a signed-in sub plant.
  useEffect(() => {
    if (loading) return;
    if (!user && pathname !== "/login") {
      router.push("/login");
    } else if (user && pathname === "/login") {
      router.push("/portal");
    }
  }, [user, loading, pathname, router]);

  const login = async (token: string) => {
    localStorage.setItem("sp_token", token);
    const res = await api.get("/auth/me");
    if (res.data.role !== REQUIRED_ROLE) {
      localStorage.removeItem("sp_token");
      throw new Error("This portal is for sub plant accounts only.");
    }
    setUser(res.data);
    await loadPlant();
    router.push("/portal");
  };

  const logout = () => {
    localStorage.removeItem("sp_token");
    setUser(null);
    setPlant(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, plant, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
