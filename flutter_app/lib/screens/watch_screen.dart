import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/signal.dart';
import '../services/api_client.dart';
import '../services/cache_service.dart';
import '../widgets/cache_banner.dart';
import 'symbol_detail_screen.dart';

class WatchScreen extends StatefulWidget {
  final ApiClient? apiClient;

  const WatchScreen({super.key, this.apiClient});

  @override
  State<WatchScreen> createState() => _WatchScreenState();
}

class _WatchScreenState extends State<WatchScreen> {
  late final ApiClient _api = widget.apiClient ?? ApiClient();
  late Stream<CachedList<WatchItem>> _stream;

  @override
  void initState() {
    super.initState();
    _stream = _api.watchStream();
  }

  void _refresh() => setState(() { _stream = _api.watchStream(); });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Near a Signal')),
      body: RefreshIndicator(
        onRefresh: () async {
          HapticFeedback.lightImpact();
          _refresh();
        },
        child: StreamBuilder<CachedList<WatchItem>>(
          stream: _stream,
          builder: (context, snap) {
            if (!snap.hasData && !snap.hasError) {
              return const Center(child: CircularProgressIndicator());
            }
            if (!snap.hasData && snap.hasError) {
              return Center(child: Text('Error: ${snap.error}'));
            }
            final result = snap.data!;
            final items = result.items;
            return Column(
              children: [
                if (result.isStale) CacheBanner(fetchedAt: result.fetchedAt),
                Expanded(
                  child: items.isEmpty
                      ? const Center(child: Text('Nothing near a signal right now.'))
                      : ListView.builder(
                          itemCount: items.length,
                          itemBuilder: (context, i) {
                            final item = items[i];
                            return Card(
                              margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              child: ListTile(
                                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                                  builder: (_) => SymbolDetailScreen(
                                    symbol: item.symbol,
                                    category: item.category,
                                    timeframe: item.timeframe,
                                  ),
                                )),
                                leading: Icon(
                                  item.isNearBuy ? Icons.trending_up : Icons.trending_down,
                                  color: item.isNearBuy ? const Color(0xFF4ADE80) : const Color(0xFFF87171),
                                ),
                                title: Text('${item.symbol} · ${item.type}'),
                                subtitle: Text(
                                    '${item.timeframe} · \$${item.price.toStringAsFixed(2)} · ${item.reasons.join(', ')}'),
                                trailing: Text(item.market,
                                    style: TextStyle(color: Colors.grey.shade400)),
                              ),
                            );
                          },
                        ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
