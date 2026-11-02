"use client";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Bell, CheckCircle2 } from "lucide-react";

export default function BuyerNotifications() {
  const [notifications, setNotifications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchNotifications = async () => {
    try {
      const res = await api.get("/buyer/notifications");
      setNotifications(res.data);
    } catch (err) {
      console.error("Failed to fetch notifications", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, []);

  const handleMarkRead = async (id: number) => {
    try {
      await api.post(`/buyer/notifications/${id}/read`);
      fetchNotifications();
    } catch (err) {
      console.error("Failed to mark as read");
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800 flex items-center">
          <Bell className="w-6 h-6 mr-2 text-slate-600" />
          Inbox & Alerts
        </h2>
      </div>

      {notifications.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center">
          <p className="text-slate-500">You have no notifications.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {notifications.map((notif) => (
            <div 
              key={notif.id} 
              className={`p-4 rounded-xl border flex justify-between items-start ${
                notif.is_read ? 'bg-white border-slate-200 text-slate-600' : 
                'bg-blue-50 border-blue-200 text-slate-900 shadow-sm'
              }`}
            >
              <div>
                <p className={`font-medium ${!notif.is_read && 'text-blue-900'}`}>{notif.message}</p>
                <p className="text-xs text-slate-500 mt-1">{new Date(notif.created_at).toLocaleString()}</p>
              </div>
              {!notif.is_read && (
                <Button size="sm" variant="ghost" onClick={() => handleMarkRead(notif.id)}>
                  <CheckCircle2 className="w-4 h-4 mr-1 text-blue-600" /> Mark Read
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
