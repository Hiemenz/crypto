/// No-op implementation used on non-web targets (VM tests, and any future
/// native build before this gets a real platform channel).
class NotificationService {
  static bool get isSupported => false;
  static String get permission => 'unsupported';
  static Future<bool> requestPermission() async => false;
  static void show(String title, {String? body}) {}
}
