import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/signal.dart';
import 'api_config.dart';
import 'cache_service.dart';

class ApiClient {
  final http.Client _client;

  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  Uri _u(String path, [Map<String, String>? query]) =>
      Uri.parse('${ApiConfig.baseUrl}$path').replace(queryParameters: query);

  List<T> _decodeList<T>(String body, T Function(Map<String, dynamic>) fromJson) {
    final List data = jsonDecode(body);
    return data.map((e) => fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<T>> _getList<T>(
    String path,
    T Function(Map<String, dynamic>) fromJson, {
    Map<String, String>? query,
  }) async {
    final res = await _client.get(_u(path, query));
    if (res.statusCode != 200) throw Exception('GET $path failed: ${res.statusCode} ${res.body}');
    return _decodeList(res.body, fromJson);
  }

  /// Cache-first-then-network: yields the last-known cached copy right away
  /// (if any), then the freshly-fetched copy once the request resolves. If
  /// the network call fails and a cache existed, only the cached copy is
  /// emitted (offline-friendly); if no cache exists, the error propagates.
  Stream<CachedList<T>> _getListCached<T>(
    String cacheKey,
    String path,
    T Function(Map<String, dynamic>) fromJson, {
    Map<String, String>? query,
  }) async* {
    final cachedRaw = await CacheService.readRaw(cacheKey);
    if (cachedRaw != null) {
      try {
        yield CachedList(
          items: _decodeList(cachedRaw, fromJson),
          isStale: true,
          fetchedAt: await CacheService.readTimestamp(cacheKey),
        );
      } catch (_) {
        // corrupt cache entry -- ignore and fall through to the network call
      }
    }

    try {
      final res = await _client.get(_u(path, query));
      if (res.statusCode != 200) {
        throw Exception('GET $path failed: ${res.statusCode} ${res.body}');
      }
      await CacheService.write(cacheKey, res.body);
      yield CachedList(items: _decodeList(res.body, fromJson), isStale: false, fetchedAt: DateTime.now());
    } catch (e) {
      if (cachedRaw == null) rethrow; // no cache to fall back on
    }
  }

  Future<List<Signal>> getFeed({String? category, String timeframe = '1d'}) {
    return _getList(
      '/api/feed',
      Signal.fromJson,
      query: {
        if (category != null) 'category': category,
        'timeframe': timeframe,
      },
    );
  }

  Stream<CachedList<Signal>> feedStream({String? category, String timeframe = '1d'}) {
    return _getListCached(
      'feed_${category ?? 'all'}_$timeframe',
      '/api/feed',
      Signal.fromJson,
      query: {
        if (category != null) 'category': category,
        'timeframe': timeframe,
      },
    );
  }

  Future<List<Signal>> getHistory(
    String symbol, {
    required String category,
    String timeframe = '1d',
    int limit = 200,
  }) {
    return _getList(
      '/api/history/$symbol',
      Signal.fromJson,
      query: {
        'category': category,
        'timeframe': timeframe,
        'limit': '$limit',
      },
    );
  }

  Future<List<WatchItem>> getWatch() {
    return _getList('/api/watch', WatchItem.fromJson);
  }

  Stream<CachedList<WatchItem>> watchStream() {
    return _getListCached('watch', '/api/watch', WatchItem.fromJson);
  }

  Future<List<CrossEvent>> getMaCrosses() {
    return _getList('/api/crosses/ma', CrossEvent.fromJson);
  }

  Stream<CachedList<CrossEvent>> maCrossesStream() {
    return _getListCached('crosses_ma', '/api/crosses/ma', CrossEvent.fromJson);
  }

  Future<List<CrossEvent>> getStochCrosses() {
    return _getList('/api/crosses/stoch', CrossEvent.fromJson);
  }

  Stream<CachedList<CrossEvent>> stochCrossesStream() {
    return _getListCached('crosses_stoch', '/api/crosses/stoch', CrossEvent.fromJson);
  }

  Future<List<PriceAlert>> getAlerts() {
    return _getList('/api/alerts', PriceAlert.fromJson);
  }

  Future<void> upsertAlert(String symbol, double threshold) async {
    final res = await _client.post(
      _u('/api/alerts'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'symbol': symbol, 'threshold': threshold}),
    );
    if (res.statusCode != 200) {
      throw Exception('POST /api/alerts failed: ${res.statusCode} ${res.body}');
    }
  }

  Future<void> deleteAlert(String symbol) async {
    final res = await _client.delete(_u('/api/alerts/$symbol'));
    if (res.statusCode != 200) {
      throw Exception('DELETE /api/alerts/$symbol failed: ${res.statusCode} ${res.body}');
    }
  }
}
