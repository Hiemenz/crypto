import 'package:shared_preferences/shared_preferences.dart';

/// On-device watchlist: a set of "category|symbol" keys. Doesn't sync across
/// devices -- there's no account system, so this is scoped to local storage.
class WatchlistService {
  static const _prefsKey = 'watchlist_symbols';

  static String _key(String category, String symbol) => '$category|$symbol';

  static Future<Set<String>> _load() async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getStringList(_prefsKey) ?? []).toSet();
  }

  static Future<void> _save(Set<String> keys) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_prefsKey, keys.toList());
  }

  static Future<bool> isWatched(String category, String symbol) async {
    final keys = await _load();
    return keys.contains(_key(category, symbol));
  }

  static Future<Set<String>> all() => _load();

  static Future<bool> toggle(String category, String symbol) async {
    final keys = await _load();
    final key = _key(category, symbol);
    final nowWatched = !keys.contains(key);
    if (nowWatched) {
      keys.add(key);
    } else {
      keys.remove(key);
    }
    await _save(keys);
    return nowWatched;
  }
}
