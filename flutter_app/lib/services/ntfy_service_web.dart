// ignore_for_file: deprecated_member_use
import 'dart:convert';
import 'dart:html' as html;

import 'notification_service.dart';
import 'ntfy_config.dart';

class NtfyService {
  static html.EventSource? _source;

  static bool get isConnected => _source != null;

  static Future<void> startIfEnabled() async {
    final enabled = await NtfyConfig.getEnabled();
    if (!enabled) return;
    final topic = await NtfyConfig.getTopic();
    if (topic.trim().isEmpty) return;
    final server = await NtfyConfig.getServer();
    connect(server: server, topic: topic);
  }

  static void connect({required String server, required String topic}) {
    stop();
    final url = '${server.replaceAll(RegExp(r"/$"), "")}/$topic/sse';
    final source = html.EventSource(url);
    source.onMessage.listen((event) {
      final data = event.data;
      if (data == null) return;
      try {
        final json = jsonDecode(data as String) as Map<String, dynamic>;
        final title = (json['title'] as String?) ?? 'Crypto Signal Station';
        final message = (json['message'] as String?) ?? '';
        NotificationService.show(title, body: message);
      } catch (_) {
        // keepalive / open events aren't JSON signal payloads -- ignore
      }
    });
    _source = source;
  }

  static void stop() {
    _source?.close();
    _source = null;
  }
}
