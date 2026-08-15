"use client";

import { useAuth } from "@/contexts/AuthContext";
import { Package, ArrowRight, ClipboardEdit, Factory } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";

export default function PlantDashboard() {
  const { user } = useAuth();

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      {/* Premium Welcome Header */}
      <div className="relative overflow-hidden bg-gradient-to-br from-slate-900 via-slate-800 to-black rounded-3xl shadow-2xl p-10 lg:p-14 text-white">
        <div className="absolute top-0 right-0 p-8 opacity-10 transform translate-x-1/4 -translate-y-1/4 pointer-events-none">
          <Factory className="w-72 h-72" />
        </div>
        
        <div className="relative z-10">
          
          <h2 className="text-4xl lg:text-5xl font-extrabold tracking-tight mb-5">
            Welcome back, <span className="text-white">{user?.full_name?.split(' ')[0] || 'Manager'}</span>!
          </h2>
          <p className="text-slate-300 max-w-2xl text-lg lg:text-xl leading-relaxed">
            This is your centralized control room. Manage assigned production orders, submit your daily logs, and let Component 3 AI automatically monitor your factory floor for critical risks.
          </p>
        </div>
      </div>

      {/* Action Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* Card 1 */}
        <div className="group relative bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 overflow-hidden hover:shadow-[0_20px_40px_rgb(0,0,0,0.08)] hover:-translate-y-1.5 transition-all duration-500">
          <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-slate-800 to-black"></div>
          <div className="p-8 lg:p-10 flex flex-col h-full justify-between">
            <div>
              <div className="w-16 h-16 rounded-2xl bg-slate-100 text-slate-800 flex items-center justify-center mb-8 group-hover:scale-110 group-hover:bg-slate-800 group-hover:text-white transition-all duration-500 shadow-sm group-hover:shadow-slate-200 group-hover:shadow-lg">
                <Package className="w-8 h-8" />
              </div>
              <h3 className="text-2xl font-bold text-slate-800 mb-4 tracking-tight">Assigned Orders</h3>
              <p className="text-slate-500 leading-relaxed mb-10 text-lg">
                View your complete queue of active Bulk Orders allocated by the Admin. Monitor priorities, deadlines, and required daily commitments.
              </p>
            </div>
            <Link href="/plant/orders" className="block">
              <Button className="w-full h-14 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-lg justify-between group/btn transition-all duration-300 shadow-md hover:shadow-xl hover:shadow-slate-200">
                <span className="font-semibold">View Production Queue</span>
                <ArrowRight className="w-5 h-5 group-hover/btn:translate-x-1.5 transition-transform duration-300" />
              </Button>
            </Link>
          </div>
        </div>

        {/* Card 2 */}
        <div className="group relative bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 overflow-hidden hover:shadow-[0_20px_40px_rgb(0,0,0,0.08)] hover:-translate-y-1.5 transition-all duration-500">
          <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-black to-slate-800"></div>
          <div className="p-8 lg:p-10 flex flex-col h-full justify-between">
            <div>
              <div className="w-16 h-16 rounded-2xl bg-slate-100 text-slate-800 flex items-center justify-center mb-8 group-hover:scale-110 group-hover:bg-slate-800 group-hover:text-white transition-all duration-500 shadow-sm group-hover:shadow-slate-200 group-hover:shadow-lg">
                <ClipboardEdit className="w-8 h-8" />
              </div>
              <h3 className="text-2xl font-bold text-slate-800 mb-4 tracking-tight">Daily Logs & AI Alerts</h3>
              <p className="text-slate-500 leading-relaxed mb-10 text-lg">
                Submit your daily machine breakdowns and worker shortages. Our AI risk engine automatically scans your data for potential failures.
              </p>
            </div>
            <Link href="/plant/orders" className="block">
              <Button className="w-full h-14 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-lg justify-between group/btn transition-all duration-300 shadow-md hover:shadow-xl hover:shadow-slate-200">
                <span className="font-semibold">Submit Daily Logs</span>
                <ArrowRight className="w-5 h-5 group-hover/btn:translate-x-1.5 transition-transform duration-300" />
              </Button>
            </Link>
          </div>
        </div>

      </div>
    </div>
  );
}
