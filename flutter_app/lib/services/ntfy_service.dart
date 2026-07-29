/// Live subscription to an ntfy.sh topic via Server-Sent Events. Web-only
/// (SSE via dart:html); no-op stub elsewhere so non-web targets still
/// compile. See NtfyConfig for what this depends on.
export 'ntfy_service_stub.dart' if (dart.library.html) 'ntfy_service_web.dart';
