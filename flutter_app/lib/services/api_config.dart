import 'package:shared_preferences/shared_preferences.dart';

/// Holds the backend base URL. Defaults to localhost for dev; override
/// at build time with --dart-define=API_BASE_URL=https://your-api.example.com
/// or change it at runtime from the Settings screen.
class ApiConfig {
  static const _prefsKey = 'api_base_url';
  static const _defaultUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static String _baseUrl = _defaultUrl;

  static String get baseUrl => _baseUrl;

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(_prefsKey) ?? _defaultUrl;
  }

  static Future<void> setBaseUrl(String url) async {
    _baseUrl = url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, url);
  }
}
