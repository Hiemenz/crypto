import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:crypto_signal_app/main.dart';
import 'package:crypto_signal_app/services/api_client.dart';

/// Returns an empty JSON list for every request, so widgets render their
/// "empty" state instead of hitting the network (flutter test fakes
/// HttpClient with a 400 response for real requests).
class _EmptyListClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final body = utf8.encode('[]');
    return http.StreamedResponse(Stream.value(body), 200);
  }
}

void main() {
  testWidgets('App renders the Feed tab with a bottom nav bar', (WidgetTester tester) async {
    final apiClient = ApiClient(client: _EmptyListClient());
    await tester.pumpWidget(CryptoSignalApp(apiClient: apiClient));
    // Not pumpAndSettle: several screens show an indeterminate
    // CircularProgressIndicator/LinearProgressIndicator, which animate
    // forever and would make pumpAndSettle time out.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('Signal Feed'), findsOneWidget);
    expect(find.byType(NavigationBar), findsOneWidget);
  });
}
