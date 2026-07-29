import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/signal.dart';
import '../services/api_client.dart';
import '../services/cache_service.dart';
import '../widgets/cache_banner.dart';
import 'symbol_detail_screen.dart';

class CrossesScreen extends StatefulWidget {
  final ApiClient? apiClient;

  const CrossesScreen({super.key, this.apiClient});

  @override
  State<CrossesScreen> createState() => _CrossesScreenState();
}

class _CrossesScreenState extends State<CrossesScreen> with SingleTickerProviderStateMixin {
  late final ApiClient _api = widget.apiClient ?? ApiClient();
  late TabController _tabController;
  late Stream<CachedList<CrossEvent>> _maStream;
  late Stream<CachedList<CrossEvent>> _stochStream;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _maStream = _api.maCrossesStream();
    _stochStream = _api.stochCrossesStream();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Crosses'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: 'MA 50/200'),
            Tab(text: 'StochRSI'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _CrossList(
            stream: _maStream,
            onRefresh: () => setState(() { _maStream = _api.maCrossesStream(); }),
          ),
          _CrossList(
            stream: _stochStream,
            onRefresh: () => setState(() { _stochStream = _api.stochCrossesStream(); }),
          ),
        ],
      ),
    );
  }
}

class _CrossList extends StatelessWidget {
  final Stream<CachedList<CrossEvent>> stream;
  final VoidCallback onRefresh;

  const _CrossList({required this.stream, required this.onRefresh});

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async {
        HapticFeedback.lightImpact();
        onRefresh();
      },
      child: StreamBuilder<CachedList<CrossEvent>>(
        stream: stream,
        builder: (context, snap) {
          if (!snap.hasData && !snap.hasError) {
            return const Center(child: CircularProgressIndicator());
          }
          if (!snap.hasData && snap.hasError) {
            return Center(child: Text('Error: ${snap.error}'));
          }
          final result = snap.data!;
          final events = result.items;
          return Column(
            children: [
              if (result.isStale) CacheBanner(fetchedAt: result.fetchedAt),
              Expanded(
                child: events.isEmpty
                    ? const Center(child: Text('No crosses found.'))
                    : ListView.builder(
                        itemCount: events.length,
                        itemBuilder: (context, i) {
                          final e = events[i];
                          return ListTile(
                            onTap: () => Navigator.of(context).push(MaterialPageRoute(
                              builder: (_) => SymbolDetailScreen(
                                symbol: e.symbol,
                                category: e.category,
                                timeframe: e.k != null ? '1wk' : '1d',
                              ),
                            )),
                            leading: Icon(
                              e.isBullish ? Icons.trending_up : Icons.trending_down,
                              color: e.isBullish ? const Color(0xFF4ADE80) : const Color(0xFFF87171),
                            ),
                            title: Text('${e.symbol} · ${e.type}'),
                            subtitle: Text('${e.date} · \$${e.price.toStringAsFixed(2)}'),
                          );
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}
