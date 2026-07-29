import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../models/signal.dart';
import '../services/api_client.dart';
import '../widgets/signal_badge.dart';

class SymbolDetailScreen extends StatefulWidget {
  final String symbol;
  final String category;
  final String timeframe;

  const SymbolDetailScreen({
    super.key,
    required this.symbol,
    required this.category,
    required this.timeframe,
  });

  @override
  State<SymbolDetailScreen> createState() => _SymbolDetailScreenState();
}

class _SymbolDetailScreenState extends State<SymbolDetailScreen> {
  final _api = ApiClient();
  late Future<List<Signal>> _future;
  Signal? _latestForShare;

  @override
  void initState() {
    super.initState();
    _future = _api.getHistory(widget.symbol, category: widget.category, timeframe: widget.timeframe);
    _future.then((history) {
      if (history.isNotEmpty && mounted) {
        setState(() => _latestForShare = history.last);
      }
    });
  }

  void _share() {
    final s = _latestForShare;
    if (s == null) return;
    HapticFeedback.selectionClick();
    final price = s.close != null ? '\$${s.close!.toStringAsFixed(2)}' : 'unknown price';
    Share.share(
      '${s.symbol} (${s.timeframe}): ${s.signal} at $price as of ${s.date} '
      '-- via Crypto Signal Station',
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.symbol),
        actions: [
          if (_latestForShare != null)
            IconButton(icon: const Icon(Icons.share), onPressed: _share),
        ],
      ),
      body: FutureBuilder<List<Signal>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('Error: ${snap.error}'));
          }
          final history = snap.data ?? [];
          if (history.isEmpty) {
            return const Center(child: Text('No history available.'));
          }
          final latest = history.last;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    '\$${latest.close?.toStringAsFixed(2) ?? '--'}',
                    style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                  ),
                  SignalBadge(label: latest.signal, isBuy: latest.isBuy, isSell: latest.isSell),
                ],
              ),
              const SizedBox(height: 4),
              Text('${widget.timeframe} · ${latest.date}', style: TextStyle(color: Colors.grey.shade400)),
              const SizedBox(height: 24),
              Text('Price', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              SizedBox(height: 220, child: _PriceChart(history: history)),
              const SizedBox(height: 24),
              Text('RSI', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              SizedBox(
                height: 120,
                child: _IndicatorChart(
                  history: history,
                  valueOf: (s) => s.rsi,
                  bands: const [30, 70],
                  min: 0,
                  max: 100,
                  color: const Color(0xFF60A5FA),
                ),
              ),
              const SizedBox(height: 24),
              Text('StochRSI K/D', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              SizedBox(
                height: 120,
                child: _StochChart(history: history),
              ),
              const SizedBox(height: 24),
              _IndicatorGrid(signal: latest),
            ],
          );
        },
      ),
    );
  }
}

class _PriceChart extends StatelessWidget {
  final List<Signal> history;
  const _PriceChart({required this.history});

  @override
  Widget build(BuildContext context) {
    final spots = <FlSpot>[];
    for (var i = 0; i < history.length; i++) {
      final c = history[i].close;
      if (c != null) spots.add(FlSpot(i.toDouble(), c));
    }
    return LineChart(
      LineChartData(
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipItems: (spots) => spots
                .map((s) => LineTooltipItem('\$${s.y.toStringAsFixed(2)}',
                    const TextStyle(color: Colors.white)))
                .toList(),
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: const Color(0xFF4ADE80),
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: const Color(0xFF4ADE80).withValues(alpha: 0.12),
            ),
          ),
        ],
      ),
    );
  }
}

class _IndicatorChart extends StatelessWidget {
  final List<Signal> history;
  final double? Function(Signal) valueOf;
  final List<double> bands;
  final double min;
  final double max;
  final Color color;

  const _IndicatorChart({
    required this.history,
    required this.valueOf,
    required this.bands,
    required this.min,
    required this.max,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final spots = <FlSpot>[];
    for (var i = 0; i < history.length; i++) {
      final v = valueOf(history[i]);
      if (v != null) spots.add(FlSpot(i.toDouble(), v));
    }
    return LineChart(
      LineChartData(
        minY: min,
        maxY: max,
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        extraLinesData: ExtraLinesData(
          horizontalLines: bands
              .map((b) => HorizontalLine(y: b, color: Colors.grey.shade700, strokeWidth: 1, dashArray: [4, 4]))
              .toList(),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: color,
            barWidth: 2,
            dotData: const FlDotData(show: false),
          ),
        ],
      ),
    );
  }
}

class _StochChart extends StatelessWidget {
  final List<Signal> history;
  const _StochChart({required this.history});

  @override
  Widget build(BuildContext context) {
    final kSpots = <FlSpot>[];
    final dSpots = <FlSpot>[];
    for (var i = 0; i < history.length; i++) {
      final k = history[i].stochRsiK;
      final d = history[i].stochRsiD;
      if (k != null) kSpots.add(FlSpot(i.toDouble(), k));
      if (d != null) dSpots.add(FlSpot(i.toDouble(), d));
    }
    return LineChart(
      LineChartData(
        minY: 0,
        maxY: 1,
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineBarsData: [
          LineChartBarData(spots: kSpots, isCurved: true, color: const Color(0xFF60A5FA), barWidth: 2, dotData: const FlDotData(show: false)),
          LineChartBarData(spots: dSpots, isCurved: true, color: const Color(0xFFFACC15), barWidth: 2, dotData: const FlDotData(show: false)),
        ],
      ),
    );
  }
}

class _IndicatorGrid extends StatelessWidget {
  final Signal signal;
  const _IndicatorGrid({required this.signal});

  @override
  Widget build(BuildContext context) {
    final entries = <String, String>{
      'RSI': signal.rsi?.toStringAsFixed(1) ?? '--',
      'MFI': signal.mfi?.toStringAsFixed(1) ?? '--',
      'MACD': signal.macd?.toStringAsFixed(2) ?? '--',
      'MA 50': signal.ma50?.toStringAsFixed(2) ?? '--',
      'MA 200': signal.ma200?.toStringAsFixed(2) ?? '--',
      'Market': signal.isBull ? 'Bull' : 'Bear',
    };
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: entries.entries.map((e) {
        return Container(
          width: 100,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(e.key, style: TextStyle(color: Colors.grey.shade400, fontSize: 11)),
              const SizedBox(height: 4),
              Text(e.value, style: const TextStyle(fontWeight: FontWeight.bold)),
            ],
          ),
        );
      }).toList(),
    );
  }
}
