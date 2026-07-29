import 'package:shared_preferences/shared_preferences.dart';

/// Raw JSON response cache, keyed by endpoint (+query). Used to show the
/// last-known feed/watch/crosses data instantly on cold start while a fresh
/// request runs in the background.
class CacheService {
  static String _dataKey(String key) => 'cache_data_$key';
  static String _tsKey(String key) => 'cache_ts_$key';

  static Future<String?> readRaw(String key) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_dataKey(key));
  }

  static Future<DateTime?> readTimestamp(String key) async {
    final prefs = await SharedPreferences.getInstance();
    final ms = prefs.getInt(_tsKey(key));
    return ms == null ? null : DateTime.fromMillisecondsSinceEpoch(ms);
  }

  static Future<void> write(String key, String raw) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_dataKey(key), raw);
    await prefs.setInt(_tsKey(key), DateTime.now().millisecondsSinceEpoch);
  }
}

/// A list of items alongside whether it's a cached (possibly stale) copy or
/// freshly fetched, and when it was last actually retrieved from the server.
class CachedList<T> {
  final List<T> items;
  final bool isStale;
  final DateTime? fetchedAt;

  CachedList({required this.items, required this.isStale, this.fetchedAt});
}
