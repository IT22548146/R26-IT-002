export interface AppNotification {
  id: number;
  message: string;
  created_at: string;
  is_read: boolean | number;
  type?: string | null;
}

export interface BasicOrderSummary {
  id: number;
  style_number: string;
  status: string;
  created_at: string;
}
