// ignore_for_file: deprecated_member_use
import 'dart:html' as html;

/// Web implementation backed directly by the browser Notification API.
class NotificationService {
  static bool get isSupported => html.Notification.supported;

  static String get permission =>
      isSupported ? html.Notification.permission ?? 'default' : 'unsupported';

  static Future<bool> requestPermission() async {
    if (!isSupported) return false;
    final result = await html.Notification.requestPermission();
    return result == 'granted';
  }

  static void show(String title, {String? body}) {
    if (!isSupported || html.Notification.permission != 'granted') return;
    html.Notification(title, body: body);
  }
}
