import 'package:flutter/material.dart';

import 'screens/home_shell.dart';
import 'services/api_client.dart';
import 'services/api_config.dart';
import 'services/ntfy_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ApiConfig.load();
  await NtfyService.startIfEnabled();
  runApp(const CryptoSignalApp());
}

class CryptoSignalApp extends StatelessWidget {
  final ApiClient? apiClient;

  const CryptoSignalApp({super.key, this.apiClient});

  @override
  Widget build(BuildContext context) {
    final darkScheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF4ADE80),
      brightness: Brightness.dark,
    );
    return MaterialApp(
      title: 'Crypto Signal Station',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: darkScheme,
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFF0F1115),
        cardTheme: const CardThemeData(
          color: Color(0xFF181B21),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(12)),
          ),
        ),
        navigationBarTheme: const NavigationBarThemeData(
          backgroundColor: Color(0xFF14171C),
        ),
      ),
      home: HomeShell(apiClient: apiClient),
    );
  }
}
