"use client";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { BarChart3, Calendar, Search } from "lucide-react";
import { Input } from "@/components/ui/Input";

export default function AdminCapacity() {
  const [capacity, setCapacity] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  
  // Default to current year-month
  const [month, setMonth] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });

  const fetchCapacity = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/capacity?month=${month}`);
      setCapacity(res.data);
    } catch (err) {
      console.error("Failed to fetch capacity", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCapacity();
  }, [month]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <BarChart3 className="w-6 h-6 mr-2 text-emerald-600" />
          Live Plant Capacity
        </h2>
        <div className="flex items-center gap-2">
          <div className="relative w-56">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-slate-400" />
            </div>
            <Input
              type="text"
              placeholder="Search plants..."
              className="pl-9 shadow-sm"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center space-x-2 bg-white px-3 py-2 rounded-lg border border-slate-200 shadow-sm">
             <Calendar className="w-4 h-4 text-slate-500" />
             <input 
               type="month" 
               value={month}
               onChange={(e) => setMonth(e.target.value)}
               className="text-sm border-none focus:ring-0 text-slate-700 bg-transparent p-0"
             />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="text-slate-500">Loading capacity data...</div>
      ) : !capacity || capacity.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">No capacity data found for {month}.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {capacity
            .filter((p: any) => (p.plant_name || "").toLowerCase().includes(searchQuery.toLowerCase()))
            .map((plantData: any) => {
            // Calculate progress percentage if we have total_capacity
            const percentUsed = plantData.total_capacity 
              ? Math.round((plantData.used_capacity / plantData.total_capacity) * 100) 
              : 0;

            return (
              <div key={plantData.plant_id} className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col h-full hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="font-bold text-slate-800 truncate" title={plantData.plant_name}>{plantData.plant_name}</h3>
                  <div className="h-8 w-8 rounded-full bg-emerald-50 flex items-center justify-center shrink-0 ml-2">
                    <BarChart3 className="w-4 h-4 text-emerald-600" />
                  </div>
                </div>
                
                {plantData.location && (
                  <p className="text-xs text-slate-500 mb-4">{plantData.location}</p>
                )}
                
                <div className="mt-auto">
                  <div className="flex justify-between items-end mb-2">
                    <div>
                      <p className="text-xs text-slate-500 mb-0.5">Available Units</p>
                      <p className="text-2xl font-black text-emerald-700">
                        {plantData.available_capacity != null ? plantData.available_capacity.toLocaleString() : "N/A"}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-500 mb-0.5">Total Cap.</p>
                      <p className="text-sm font-semibold text-slate-700">
                        {plantData.total_capacity != null ? plantData.total_capacity.toLocaleString() : "N/A"}
                      </p>
                    </div>
                  </div>

                  {plantData.total_capacity > 0 && (
                    <div className="w-full bg-slate-100 rounded-full h-2 mt-4 overflow-hidden">
                      <div 
                        className={`h-2 rounded-full ${percentUsed > 90 ? 'bg-red-500' : percentUsed > 75 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                        style={{ width: `${Math.min(percentUsed, 100)}%` }}
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
