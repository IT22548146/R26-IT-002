"""
services/notification_service.py
Creates in-portal notifications for all roles.
"""

from database.db import get_db


def create_notification(user_id: int, title: str, message: str,
                         notif_type: str = "info",
                         related_order_type: str = None,
                         related_order_id: int = None):
    """
    Insert a notification row for a user.
    notif_type: 'info' | 'success' | 'warning' | 'critical'
    """
    db = get_db()
    db.execute(
        """INSERT INTO notifications
           (user_id, title, message, type, related_order_type, related_order_id)
           VALUES (?,?,?,?,?,?)""",
        (user_id, title, message, notif_type, related_order_type, related_order_id),
    )
    db.commit()
