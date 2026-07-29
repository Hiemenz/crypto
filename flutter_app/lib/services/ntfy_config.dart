import 'package:shared_preferences/shared_preferences.dart';

/// Persisted settings for the ntfy.sh live-notification subscription.
/// This mirrors whatever `notify.ntfy_server` / `notify.ntfy_topic` you set
/// in crypto_signal_station/cryptos.yml on the backend -- the backend posts
/// signal-change and price-alert messages to that topic on every pipeline
/// refresh, and this app just needs to listen on the same topic.
class NtfyConfig {
  static const _serverKey = 'ntfy_server';
  static const _topicKey = 'ntfy_topic';
  static const _enabledKey = 'ntfy_enabled';
  static const defaultServer = 'https://ntfy.sh';

  static Future<String> getServer() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_serverKey) ?? defaultServer;
  }

  static Future<String> getTopic() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_topicKey) ?? '';
  }

  static Future<bool> getEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_enabledKey) ?? false;
  }

  static Future<void> save({
    required String server,
    required String topic,
    required bool enabled,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_serverKey, server);
    await prefs.setString(_topicKey, topic);
    await prefs.setBool(_enabledKey, enabled);
  }
}
