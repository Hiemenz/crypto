import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:crypto_signal_app/services/api_client.dart';

class _ScriptedClient extends http.BaseClient {
  final List<http.StreamedResponse Function()> _responses;
  int _calls = 0;

  _ScriptedClient(this._responses);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final response = _responses[_calls.clamp(0, _responses.length - 1)]();
    _calls++;
    return response;
  }
}

http.StreamedResponse _ok(String body) =>
    http.StreamedResponse(Stream.value(utf8.encode(body)), 200);

http.StreamedResponse _fail() =>
    http.StreamedResponse(const Stream.empty(), 500);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('feedStream caches a successful response and serves it if the network later fails', () async {
    final signalJson = jsonEncode([
      {
        'symbol': 'BTC-USD',
        'category': 'crypto',
        'timeframe': '1d',
        'date': '2026-01-01',
        'close': 50000.0,
        'is_bull': true,
        'signal': 'Buy',
      }
    ]);

    // First app run: network succeeds, response gets cached.
    final firstClient = _ScriptedClient([() => _ok(signalJson)]);
    final firstApi = ApiClient(client: firstClient);
    final firstResults = await firstApi.feedStream(timeframe: '1d').toList();

    // No cache existed yet, so only one (fresh) emission.
    expect(firstResults, hasLength(1));
    expect(firstResults.single.isStale, isFalse);
    expect(firstResults.single.items.single.symbol, 'BTC-USD');

    // Second app run ("cold start" with the same on-device storage): network
    // is down, but the cached copy from the first run should still be served.
    final secondClient = _ScriptedClient([() => _fail()]);
    final secondApi = ApiClient(client: secondClient);
    final secondResults = await secondApi.feedStream(timeframe: '1d').toList();

    expect(secondResults, hasLength(1));
    expect(secondResults.single.isStale, isTrue);
    expect(secondResults.single.items.single.symbol, 'BTC-USD');
  });
}
