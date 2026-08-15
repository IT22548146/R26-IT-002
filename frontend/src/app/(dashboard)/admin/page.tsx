"use client";
import Swal from "@/lib/swal";

import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Check, X, Clock, Users, Building2, Package, ClipboardList, BarChart3, Activity, AlertTriangle, Search, ChevronRight } from "lucide-react";
import Link from "next/link";

interface PendingUser {
  id: number;
  full_name: string;
  email: string;
  created_at: string;
  org_name: string;
}

export default function AdminDashboard() {
  const { user } = useAuth();
  // Managers share this dashboard but can't see user management.
  const isAdmin = user?.role === "Admin";
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([]);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [sampleOrders, setSampleOrders] = useState<any[]>([]);
  const [bulkOrders, setBulkOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchPending, setSearchPending] = useState("");

  const fetchData = async () => {
    try {
      const [sampleRes, bulkRes] = await Promise.all([
        api.get("/admin/orders/sample"),
        api.get("/admin/orders/bulk"),
      ]);
      setSampleOrders(sampleRes.data);
      setBulkOrders(bulkRes.data);

      // User management is Admin-only — skip these calls for Managers.
      if (isAdmin) {
        const [pendingRes, allRes] = await Promise.all([
          api.get("/admin/users/pending"),
          api.get("/admin/users"),
        ]);
        setPendingUsers(pendingRes.data);
        setAllUsers(allRes.data);
      }
    } catch (err) {
      console.error("Failed to fetch dashboard data", err);
    } finally {
      setLoading(false);
    }
  };

  // Days from today until an order's required date.
  const daysUntil = (d: string) => {
    if (!d) return Infinity;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const due = new Date(d); due.setHours(0, 0, 0, 0);
    return Math.round((due.getTime() - today.getTime()) / 86400000);
  };

  // Active orders (still need work) across sample + bulk, tagged with type + due days.
  const activeOrders = [
    ...sampleOrders
      .filter((o) => ["Pending", "Processing"].includes(o.status))
      .map((o) => ({ ...o, type: "Sample", due: daysUntil(o.buyer_required_date) })),
    ...bulkOrders
      .filter((o) => ["Pending", "CustomerPending", "Processing", "Hold"].includes(o.status))
      .map((o) => ({ ...o, type: "Bulk", due: daysUntil(o.buyer_required_date) })),
  ];
  const dueUrgent = activeOrders.filter((o) => o.due >= 1 && o.due <= 5).sort((a, b) => a.due - b.due);
  const dueSoon = activeOrders.filter((o) => o.due > 5 && o.due <= 10).sort((a, b) => a.due - b.due);

  // Categorized pending approvals (orders awaiting admin action).
  const pendingSampleCount = sampleOrders.filter((o) => o.status === "Pending").length;
  const pendingBulkCount = bulkOrders.filter((o) => o.status === "Pending").length;

  useEffect(() => {
    if (user) fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, user?.role]);

  const handleApprove = async (id: number) => {
    const result = await Swal.fire({ title: "Confirm", text: "Are you sure you want to approve this buyer?", icon: 'warning', showCancelButton: true, confirmButtonColor: '#3085d6', cancelButtonColor: '#d33', confirmButtonText: 'Yes' });
    if (!result.isConfirmed) return;
    try {
      await api.post(`/admin/users/${id}/approve`);
      fetchData();
    } catch (err) {
      Swal.fire({ icon: 'info', title: "Failed to approve user." });
    }
  };

  const handleReject = async (id: number) => {
    const result = await Swal.fire({ title: "Confirm", text: "Are you sure you want to reject this buyer?", icon: 'warning', showCancelButton: true, confirmButtonColor: '#3085d6', cancelButtonColor: '#d33', confirmButtonText: 'Yes' });
    if (!result.isConfirmed) return;
    try {
      await api.post(`/admin/users/${id}/reject`);
      fetchData();
    } catch (err) {
      Swal.fire({ icon: 'info', title: "Failed to reject user." });
    }
  };

  const totalBuyers = allUsers.filter(u => u.role === "Buyer" && u.status === "Approved").length;
  const totalPlants = allUsers.filter(u => u.role === "PlantManager").length;

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="bg-gradient-to-r from-slate-900 to-black rounded-xl shadow-lg border border-slate-800 p-8 text-white relative overflow-hidden">
        <div className="relative z-10">
          <h2 className="text-3xl font-bold mb-2">{isAdmin ? "System Administration" : "Operations Console"}</h2>
          <p className="text-slate-300 max-w-2xl">
            Welcome, {user?.full_name}. Oversee factory capacity{isAdmin ? ", manage buyer accounts," : ""} and review AI allocations across the FabricFlow network.
          </p>
        </div>
        <div className="absolute right-0 top-0 opacity-10 pointer-events-none transform translate-x-1/4 -translate-y-1/4">
           <Activity className="w-64 h-64" />
        </div>
      </div>

      {/* Quick Stats — user/network figures are Admin-only */}
      {isAdmin && (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex items-center">
          <div className="p-4 bg-amber-50 text-amber-600 rounded-full mr-4">
            <Clock className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500">Pending Approvals</p>
            <p className="text-2xl font-bold text-slate-900">{loading ? "-" : pendingUsers.length}</p>
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex items-center">
          <div className="p-4 bg-blue-50 text-blue-600 rounded-full mr-4">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500">Active Buyers</p>
            <p className="text-2xl font-bold text-slate-900">{loading ? "-" : totalBuyers}</p>
          </div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex items-center">
          <div className="p-4 bg-emerald-50 text-emerald-600 rounded-full mr-4">
            <Building2 className="w-6 h-6" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500">Plant Facilities</p>
            <p className="text-2xl font-bold text-slate-900">{loading ? "-" : totalPlants}</p>
          </div>
        </div>
      </div>
      )}

      {/* Categorized pending approvals (orders awaiting admin action) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Link href="/admin/samples" className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex items-center justify-between hover:border-blue-300 hover:shadow-md transition-all">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-50 text-blue-600 rounded-lg"><ClipboardList className="w-5 h-5" /></div>
            <div>
              <p className="text-sm text-slate-500">Sample Pendings</p>
              <p className="text-xs text-slate-400">Awaiting feasibility review / assignment</p>
            </div>
          </div>
          <span className="text-2xl font-bold text-slate-900">{loading ? "-" : pendingSampleCount}</span>
        </Link>
        <Link href="/admin/bulk" className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex items-center justify-between hover:border-indigo-300 hover:shadow-md transition-all">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-indigo-50 text-indigo-600 rounded-lg"><Package className="w-5 h-5" /></div>
            <div>
              <p className="text-sm text-slate-500">Bulk Pendings</p>
              <p className="text-xs text-slate-400">Awaiting timeline / plant assignment</p>
            </div>
          </div>
          <span className="text-2xl font-bold text-slate-900">{loading ? "-" : pendingBulkCount}</span>
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Action Area */}
        <div className="lg:col-span-2 space-y-6">
          {/* Urgent orders by deadline — shown ABOVE pending accounts */}
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-lg font-bold text-slate-800 flex items-center mb-4 border-b border-slate-100 pb-4">
              <AlertTriangle className="w-5 h-5 mr-2 text-red-500" />
              Orders by Deadline
            </h2>
            {loading ? (
              <p className="text-slate-500 text-sm py-4">Loading orders...</p>
            ) : dueUrgent.length === 0 && dueSoon.length === 0 ? (
              <p className="text-sm text-slate-500 py-4">No active orders due within 10 days.</p>
            ) : (
              <div className="space-y-5">
                <UrgentGroup title="Due in 1–5 days" tone="red" orders={dueUrgent} />
                <UrgentGroup title="Due in 5–10 days" tone="amber" orders={dueSoon} />
              </div>
            )}
          </div>

          {isAdmin && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <div className="flex items-center justify-between mb-4 border-b border-slate-100 pb-4">
              <h2 className="text-lg font-bold text-slate-800 flex items-center">
                <Clock className="w-5 h-5 mr-2 text-amber-500" />
                Action Required: Pending Accounts
              </h2>
              <div className="relative w-full max-w-xs ml-4">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-4 w-4 text-slate-400" />
                </div>
                <Input
                  type="text"
                  placeholder="Search pending accounts..."
                  className="pl-10 shadow-sm"
                  value={searchPending}
                  onChange={(e) => setSearchPending(e.target.value)}
                />
              </div>
            </div>

            {loading ? (
              <p className="text-slate-500 text-sm py-4">Loading accounts...</p>
            ) : pendingUsers.length === 0 ? (
              <div className="text-center py-8">
                <div className="mx-auto w-12 h-12 bg-slate-50 rounded-full flex items-center justify-center mb-3">
                  <Check className="w-5 h-5 text-emerald-500" />
                </div>
                <p className="text-sm text-slate-500">All caught up! No pending approvals at this time.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-slate-600">
                  <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-y border-slate-200">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Company</th>
                      <th className="px-4 py-3 font-semibold">Contact Person</th>
                      <th className="px-4 py-3 font-semibold">Registered</th>
                      <th className="px-4 py-3 text-right font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {pendingUsers
                      .filter((u) => 
                        (u.org_name || "").toLowerCase().includes(searchPending.toLowerCase()) ||
                        (u.full_name || "").toLowerCase().includes(searchPending.toLowerCase()) ||
                        (u.email || "").toLowerCase().includes(searchPending.toLowerCase())
                      )
                      .map((u) => (
                      <tr key={u.id} className="hover:bg-slate-50/50 transition-colors">
                        <td className="px-4 py-4">
                          <p className="font-medium text-slate-900">{u.org_name}</p>
                          <p className="text-xs text-slate-500">{u.email}</p>
                        </td>
                        <td className="px-4 py-4">{u.full_name}</td>
                        <td className="px-4 py-4">{new Date(u.created_at).toLocaleDateString()}</td>
                        <td className="px-4 py-4 text-right space-x-2">
                          <Button size="sm" onClick={() => handleApprove(u.id)} className="bg-emerald-600 hover:bg-emerald-700 text-white border-0 shadow-sm">
                            <Check className="w-4 h-4 mr-1" /> Approve
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => handleReject(u.id)} className="text-red-600 hover:bg-red-50 hover:text-red-700 border-red-200">
                            Reject
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          )}
        </div>

        {/* Quick Links / Operations Sidebar */}
        <div className="space-y-4">
          <Link href="/admin/samples" className="block bg-white rounded-xl shadow-sm border border-slate-200 p-5 hover:border-blue-300 hover:shadow-md transition-all group">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-lg group-hover:bg-blue-600 group-hover:text-white transition-colors">
                <ClipboardList className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Sample Orders</h3>
                <p className="text-xs text-slate-500 mt-1">Review AI feasibility & assign factories</p>
              </div>
            </div>
          </Link>

          <Link href="/admin/bulk" className="block bg-white rounded-xl shadow-sm border border-slate-200 p-5 hover:border-indigo-300 hover:shadow-md transition-all group">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-indigo-50 text-indigo-600 rounded-lg group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                <Package className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Bulk Orders</h3>
                <p className="text-xs text-slate-500 mt-1">Manage AI splits & monitor production</p>
              </div>
            </div>
          </Link>

          <Link href="/admin/capacity" className="block bg-white rounded-xl shadow-sm border border-slate-200 p-5 hover:border-emerald-300 hover:shadow-md transition-all group">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-emerald-50 text-emerald-600 rounded-lg group-hover:bg-emerald-600 group-hover:text-white transition-colors">
                <BarChart3 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Capacity Overview</h3>
                <p className="text-xs text-slate-500 mt-1">Live factory load & booking limits</p>
              </div>
            </div>
          </Link>
          
          {isAdmin && (
          <Link href="/admin/users" className="block bg-white rounded-xl shadow-sm border border-slate-200 p-5 hover:border-slate-300 hover:shadow-md transition-all group">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-slate-100 text-slate-600 rounded-lg group-hover:bg-slate-800 group-hover:text-white transition-colors">
                <Users className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">User Directory</h3>
                <p className="text-xs text-slate-500 mt-1">Manage all accounts and roles</p>
              </div>
            </div>
          </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function UrgentGroup({ title, tone, orders }: { title: string; tone: "red" | "amber"; orders: any[] }) {
  if (orders.length === 0) return null;
  const dot = tone === "red" ? "bg-red-500" : "bg-amber-500";
  const chip = tone === "red" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700";
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-2 h-2 rounded-full ${dot}`} />
        <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${chip}`}>{orders.length}</span>
      </div>
      <ul className="space-y-2">
        {orders.map((o) => (
          <li key={`${o.type}-${o.id}`}>
            {/* Each row opens that order's detail page. */}
            <Link
              href={o.type === "Sample" ? `/admin/samples/${o.id}` : `/admin/bulk/${o.id}`}
              className="group flex items-center justify-between gap-3 bg-slate-50 border border-slate-100 rounded-lg px-3 py-2 text-sm hover:bg-white hover:border-slate-300 hover:shadow-sm transition-all"
            >
              <span className="text-slate-700 min-w-0 truncate">
                <span className="font-medium">{o.type}</span> · {o.style_number}
                <span className="text-slate-400"> · {o.buyer_name}</span>
              </span>
              <span className="text-slate-500 flex items-center gap-1.5 shrink-0">
                {o.status} · <strong className="text-slate-700">{o.due}d</strong>
                <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-colors" />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
