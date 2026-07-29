import 'package:flutter/material.dart';

import '../services/api_client.dart';
import 'crosses_screen.dart';
import 'feed_screen.dart';
import 'settings_screen.dart';
import 'watch_screen.dart';
import 'watchlist_screen.dart';

class HomeShell extends StatefulWidget {
  final ApiClient? apiClient;

  const HomeShell({super.key, this.apiClient});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  late final _screens = [
    FeedScreen(apiClient: widget.apiClient),
    WatchlistScreen(apiClient: widget.apiClient),
    WatchScreen(apiClient: widget.apiClient),
    CrossesScreen(apiClient: widget.apiClient),
    SettingsScreen(apiClient: widget.apiClient),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dynamic_feed), label: 'Feed'),
          NavigationDestination(icon: Icon(Icons.star), label: 'Watchlist'),
          NavigationDestination(icon: Icon(Icons.visibility), label: 'Near'),
          NavigationDestination(icon: Icon(Icons.compare_arrows), label: 'Crosses'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}
