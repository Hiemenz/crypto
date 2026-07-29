/// Thin wrapper around the browser Notification API. Conditionally exports
/// a dart:html-backed implementation on web and a no-op stub everywhere
/// else, so non-web targets (including `flutter test`, which runs on the
/// Dart VM) still compile.
export 'notification_service_stub.dart'
    if (dart.library.html) 'notification_service_web.dart';
