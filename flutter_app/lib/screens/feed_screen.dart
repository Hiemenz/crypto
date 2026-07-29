import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/signal.dart';
import '../services/api_client.dart';
import '../services/cache_service.dart';
import '../widgets/cache_banner.dart';
import '../widgets/signal_card.dart';
import 'symbol_detail_screen.dart';

class FeedScreen extends StatefulWidget {
  final ApiClient? apiClient;

  const FeedScreen({super.key, this.apiClient});

  @override
  State<FeedScreen> createState() => _FeedScreenState();
}

class _FeedScreenState extends State<FeedScreen> {
  late final ApiClient _api = widget.apiClient ?? ApiClient();
  String? _category; // null = all
  String _timeframe = '1d';
  String _filter = 'All';
  late Stream<CachedList<Signal>> _stream;

  static const _timeframes = ['1d', '2d', '3d', '1wk', '2wk'];
  static const _filters = ['All', 'Buy', 'Sell', 'Hold'];

  @override
  void initState() {
    super.initState();
    _stream = _load();
  }

  Stream<CachedList<Signal>> _load() =>
      _api.feedStream(category: _category, timeframe: _timeframe);

  void _refresh() => setState(() { _stream = _load(); });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Signal Feed')),
      body: Column(
        children: [
          _buildFilterBar(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                HapticFeedback.lightImpact();
                _refresh();
              },
              child: StreamBuilder<CachedList<Signal>>(
                stream: _stream,
                builder: (context, snap) {
                  if (!snap.hasData && !snap.hasError) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (!snap.hasData && snap.hasError) {
                    return _ErrorView(error: snap.error.toString(), onRetry: _refresh);
                  }
                  final result = snap.data!;
                  var items = result.items;
                  if (_filter != 'All') {
                    items = items
                        .where((s) => s.signal.toLowerCase().contains(_filter.toLowerCase()))
                        .toList();
                  }
                  return Column(
                    children: [
                      if (result.isStale) CacheBanner(fetchedAt: result.fetchedAt),
                      Expanded(
                        child: items.isEmpty
                            ? const Center(child: Text('No signals match this filter.'))
                            : ListView.builder(
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
                                  );
                                },
                              ),
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _CategoryChip(label: 'All', selected: _category == null, onTap: () {
                HapticFeedback.selectionClick();
                setState(() { _category = null; _refresh(); });
              }),
              const SizedBox(width: 8),
              _CategoryChip(label: 'Crypto', selected: _category == 'crypto', onTap: () {
                HapticFeedback.selectionClick();
                setState(() { _category = 'crypto'; _refresh(); });
              }),
              const SizedBox(width: 8),
              _CategoryChip(label: 'Stocks', selected: _category == 'stocks', onTap: () {
                HapticFeedback.selectionClick();
                setState(() { _category = 'stocks'; _refresh(); });
              }),
              const Spacer(),
              DropdownButton<String>(
                value: _timeframe,
                underline: const SizedBox(),
                items: _timeframes
                    .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                    .toList(),
                onChanged: (v) {
                  if (v == null) return;
                  HapticFeedback.selectionClick();
                  setState(() { _timeframe = v; _refresh(); });
                },
              ),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            height: 34,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: _filters.map((f) {
                final selected = _filter == f;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(f),
                    selected: selected,
                    onSelected: (_) {
                      HapticFeedback.selectionClick();
                      setState(() => _filter = f);
                    },
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _CategoryChip({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(label: Text(label), selected: selected, onSelected: (_) => onTap());
  }
}

class _ErrorView extends StatelessWidget {
  final String error;
  final VoidCallback onRetry;

  const _ErrorView({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 40, color: Colors.grey),
            const SizedBox(height: 12),
            Text('Could not reach the API.\n$error', textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
