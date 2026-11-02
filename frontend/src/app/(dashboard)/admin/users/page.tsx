"use client";
import Swal from "@/lib/swal";

import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { Users as UsersIcon, Search, Filter, Check, X, ChevronLeft, ChevronRight, UserPlus, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

const ITEMS_PER_PAGE = 10;

export default function AdminUsers() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters & Pagination State
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [currentPage, setCurrentPage] = useState(1);
  const [showCreateManager, setShowCreateManager] = useState(false);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const res = await api.get("/admin/users");
      setUsers(res.data);
    } catch (err) {
      console.error("Failed to fetch users", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  // Action Handlers
  const handleApprove = async (id: number) => {
    const result = await Swal.fire({ title: "Confirm", text: "Approve this user account?", icon: 'warning', showCancelButton: true, confirmButtonColor: '#3085d6', cancelButtonColor: '#d33', confirmButtonText: 'Yes' });
    if (!result.isConfirmed) return;
    try {
      await api.post(`/admin/users/${id}/approve`);
      fetchUsers();
    } catch (err) {
      Swal.fire({ icon: 'info', title: "Failed to approve user." });
    }
  };

  const handleReject = async (id: number) => {
    const result = await Swal.fire({ title: "Confirm", text: "Reject this user account?", icon: 'warning', showCancelButton: true, confirmButtonColor: '#3085d6', cancelButtonColor: '#d33', confirmButtonText: 'Yes' });
    if (!result.isConfirmed) return;
    try {
      await api.post(`/admin/users/${id}/reject`);
      fetchUsers();
    } catch (err) {
      Swal.fire({ icon: 'info', title: "Failed to reject user." });
    }
  };

  // Derived State: Filtering & Searching
  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      const matchesSearch = 
        user.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        user.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (user.org_name && user.org_name.toLowerCase().includes(searchQuery.toLowerCase()));
      
      const matchesRole = roleFilter === "All" || user.role === roleFilter;
      const matchesStatus = statusFilter === "All" || user.status === statusFilter;

      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [users, searchQuery, roleFilter, statusFilter]);

  // Derived State: Pagination
  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / ITEMS_PER_PAGE));
  const paginatedUsers = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredUsers.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [filteredUsers, currentPage]);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, roleFilter, statusFilter]);

  const uniqueRoles = Array.from(new Set(users.map(u => u.role)));
  const uniqueStatuses = Array.from(new Set(users.map(u => u.status)));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <UsersIcon className="w-6 h-6 mr-2 text-blue-600" />
          User Directory
        </h2>
        <Button onClick={() => setShowCreateManager(true)} className="bg-violet-600 hover:bg-violet-700">
          <UserPlus className="w-4 h-4 mr-1.5" /> Create Manager
        </Button>
      </div>

      {/* Filters Toolbar */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
        <div className="flex flex-col md:flex-row md:items-center space-y-4 md:space-y-0 md:space-x-4">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-slate-400" />
            </div>
            <Input
              type="text"
              placeholder="Search by name, email, or company..."
              className="pl-10 shadow-sm"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          
          <div className="flex space-x-4">
            <div className="flex items-center space-x-2">
              <Filter className="w-4 h-4 text-slate-400" />
              <select
                className="h-10 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950"
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
              >
                <option value="All">All Roles</option>
                {uniqueRoles.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            
            <select
              className="h-10 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-950"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="All">All Statuses</option>
              {uniqueStatuses.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Data Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left text-slate-600">
            <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-4 font-semibold">User Details</th>
                <th className="px-6 py-4 font-semibold">Role & Org</th>
                <th className="px-6 py-4 font-semibold">Status</th>
                <th className="px-6 py-4 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-slate-500">
                    Loading users...
                  </td>
                </tr>
              ) : paginatedUsers.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-slate-500">
                    No users found matching your criteria.
                  </td>
                </tr>
              ) : (
                paginatedUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4">
                      <p className="font-semibold text-slate-900">{user.full_name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{user.email}</p>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex bg-slate-100 text-slate-700 px-2 py-1 rounded-md text-xs font-medium mb-1">
                        {user.role}
                      </span>
                      {user.org_name && (
                        <p className="text-xs text-slate-500">{user.org_name}</p>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-medium border ${
                        user.status === 'Approved' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                        user.status === 'Pending' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                        'bg-red-50 text-red-700 border-red-200'
                      }`}>
                        {user.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      {user.status === 'Pending' ? (
                        <div className="flex items-center justify-end space-x-2">
                          <Button size="sm" onClick={() => handleApprove(user.id)} className="bg-emerald-600 hover:bg-emerald-700 text-white border-0 shadow-sm px-3">
                            <Check className="w-4 h-4" />
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => handleReject(user.id)} className="text-red-600 hover:bg-red-50 hover:text-red-700 border-red-200 px-3">
                            <X className="w-4 h-4" />
                          </Button>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">No actions</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {!loading && filteredUsers.length > 0 && (
          <div className="border-t border-slate-100 px-6 py-4 flex items-center justify-between bg-slate-50/50">
            <p className="text-sm text-slate-500">
              Showing <span className="font-medium text-slate-900">{((currentPage - 1) * ITEMS_PER_PAGE) + 1}</span> to <span className="font-medium text-slate-900">{Math.min(currentPage * ITEMS_PER_PAGE, filteredUsers.length)}</span> of <span className="font-medium text-slate-900">{filteredUsers.length}</span> results
            </p>
            <div className="flex items-center space-x-2">
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-2"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm text-slate-600 font-medium px-2">
                Page {currentPage} of {totalPages}
              </span>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-2"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {showCreateManager && (
        <CreateManagerModal
          onClose={() => setShowCreateManager(false)}
          onCreated={() => { setShowCreateManager(false); fetchUsers(); }}
        />
      )}
    </div>
  );
}

function CreateManagerModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.full_name.trim() || !form.email.trim() || form.password.length < 8) {
      Swal.fire({ icon: "warning", title: "Enter a name, email, and a password of at least 8 characters." });
      return;
    }
    setSaving(true);
    try {
      await api.post("/admin/users/manager", form);
      Swal.fire({ icon: "success", title: "Manager account created", text: `${form.email} can now sign in with manager access.` });
      onCreated();
    } catch (err: any) {
      Swal.fire({ icon: "error", title: "Error", text: err.response?.data?.error || "Failed to create manager." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form onSubmit={submit} className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-slate-800 mb-1 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-violet-600" /> Create Manager Account
        </h3>
        <p className="text-sm text-slate-500 mb-4">
          A manager can run order, style, and capacity operations in the admin panel — but not user management or the performance dashboard.
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Full Name</label>
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Jane Manager" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="jane@fabricflow.com" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Temporary Password</label>
            <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="At least 8 characters" minLength={8} required />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving} className="bg-violet-600 hover:bg-violet-700">
            {saving ? "Creating..." : "Create Manager"}
          </Button>
        </div>
      </form>
    </div>
  );
}
