import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/signal.dart';
import '../services/api_client.dart';
import '../services/watchlist_service.dart';
import '../widgets/signal_card.dart';
import 'symbol_detail_screen.dart';

class WatchlistScreen extends StatefulWidget {
  final ApiClient? apiClient;

  const WatchlistScreen({super.key, this.apiClient});

  @override
  State<WatchlistScreen> createState() => _WatchlistScreenState();
}

class _WatchlistScreenState extends State<WatchlistScreen> {
  late final ApiClient _api = widget.apiClient ?? ApiClient();
  String _timeframe = '1d';
  late Future<List<Signal>> _future;

  static const _timeframes = ['1d', '2d', '3d', '1wk', '2wk'];

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Signal>> _load() async {
    final watched = await WatchlistService.all();
    if (watched.isEmpty) return [];
    final all = await _api.getFeed(timeframe: _timeframe);
    return all
        .where((s) => watched.contains('${s.category}|${s.symbol}'))
        .toList();
  }

  void _refresh() => setState(() { _future = _load(); });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Watchlist'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Center(
              child: DropdownButton<String>(
                value: _timeframe,
                underline: const SizedBox(),
                items: _timeframes
                    .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                    .toList(),
                onChanged: (v) {
                  if (v == null) return;
                  setState(() { _timeframe = v; _refresh(); });
                },
              ),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          HapticFeedback.lightImpact();
          _refresh();
        },
        child: FutureBuilder<List<Signal>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return Center(child: Text('Error: ${snap.error}'));
            }
            final items = snap.data ?? [];
            if (items.isEmpty) {
              return ListView(
                children: const [
                  SizedBox(height: 80),
                  Icon(Icons.star_border, size: 48, color: Colors.grey),
                  SizedBox(height: 12),
                  Center(
                    child: Text(
                      'No symbols saved yet.\nStar a signal from the Feed to add it here.',
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              );
            }
            return ListView.builder(
              itemCount: items.length,
              itemBuilder: (context, i) {
                final s = items[i];
                return SignalCard(
                  signal: s,
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => SymbolDetailScreen(
                      symbol: s.symbol,
                      category: s.category,
                      timeframe: s.timeframe,
                    ),
                  )),
                  onWatchlistChanged: (_) => _refresh(),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
