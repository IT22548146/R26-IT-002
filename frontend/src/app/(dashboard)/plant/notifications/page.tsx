"use client";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Bell, CheckCircle2, AlertOctagon } from "lucide-react";

export default function PlantNotifications() {
  const [notifications, setNotifications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchNotifications = async () => {
    try {
      const res = await api.get("/plant/notifications");
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
      await api.post(`/plant/notifications/${id}/read`);
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
          Plant Alerts & Notifications
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
                notif.type === 'critical' ? 'bg-red-50 border-red-200 text-red-900 shadow-sm' :
                'bg-purple-50 border-purple-200 text-slate-900 shadow-sm'
              }`}
            >
              <div className="flex items-start">
                {notif.type === 'critical' && <AlertOctagon className="w-5 h-5 mr-2 mt-0.5 text-red-600 flex-shrink-0" />}
                <div>
                  <p className={`font-medium ${!notif.is_read && notif.type !== 'critical' && 'text-purple-900'}`}>{notif.message}</p>
                  <p className="text-xs opacity-75 mt-1">{new Date(notif.created_at).toLocaleString()}</p>
                </div>
              </div>
              {!notif.is_read && (
                <Button size="sm" variant="ghost" onClick={() => handleMarkRead(notif.id)} className={notif.type === 'critical' ? 'hover:bg-red-100 hover:text-red-700' : ''}>
                  <CheckCircle2 className="w-4 h-4 mr-1 opacity-70" /> Mark Read
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
