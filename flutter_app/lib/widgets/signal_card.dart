import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../models/signal.dart';
import '../services/watchlist_service.dart';
import 'signal_badge.dart';

final _priceFmt = NumberFormat.currency(symbol: '\$', decimalDigits: 2);

class SignalCard extends StatefulWidget {
  final Signal signal;
  final VoidCallback onTap;
  final ValueChanged<bool>? onWatchlistChanged;

  const SignalCard({
    super.key,
    required this.signal,
    required this.onTap,
    this.onWatchlistChanged,
  });

  @override
  State<SignalCard> createState() => _SignalCardState();
}

class _SignalCardState extends State<SignalCard> {
  bool _watched = false;

  @override
  void initState() {
    super.initState();
    WatchlistService.isWatched(widget.signal.category, widget.signal.symbol)
        .then((w) {
      if (mounted) setState(() => _watched = w);
    });
  }

  Future<void> _toggleWatchlist() async {
    HapticFeedback.mediumImpact();
    final nowWatched = await WatchlistService.toggle(
        widget.signal.category, widget.signal.symbol);
    if (mounted) setState(() => _watched = nowWatched);
    widget.onWatchlistChanged?.call(nowWatched);
  }

  @override
  Widget build(BuildContext context) {
    final signal = widget.signal;
    final close = signal.close ?? 0;

    return Dismissible(
      key: ValueKey('${signal.category}-${signal.symbol}-${signal.timeframe}'),
      background: _swipeBackground(alignment: Alignment.centerLeft),
      secondaryBackground: _swipeBackground(alignment: Alignment.centerRight),
      confirmDismiss: (_) async {
        await _toggleWatchlist();
        return false; // snap back -- items shouldn't vanish from a live feed
      },
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () {
            HapticFeedback.selectionClick();
            widget.onTap();
          },
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                CircleAvatar(
                  backgroundColor: signal.isBull
                      ? const Color(0xFF163B2E)
                      : const Color(0xFF3B1620),
                  child: Text(
                    signal.symbol.characters.first,
                    style: TextStyle(
                      color: signal.isBull
                          ? const Color(0xFF4ADE80)
                          : const Color(0xFFF87171),
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        signal.symbol,
                        style: const TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 16),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${close > 0 ? _priceFmt.format(close) : '--'}  ·  RSI ${signal.rsi?.toStringAsFixed(1) ?? '--'}',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 12.5),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: Icon(
                    _watched ? Icons.star : Icons.star_border,
                    color: _watched ? const Color(0xFFFACC15) : Colors.grey.shade600,
                  ),
                  onPressed: _toggleWatchlist,
                  tooltip: _watched ? 'Remove from watchlist' : 'Add to watchlist',
                ),
                SignalBadge(
                  label: signal.signal,
                  isBuy: signal.isBuy,
                  isSell: signal.isSell,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _swipeBackground({required Alignment alignment}) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      padding: const EdgeInsets.symmetric(horizontal: 20),
      alignment: alignment,
      decoration: BoxDecoration(
        color: const Color(0xFF33301A),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(
        _watched ? Icons.star_border : Icons.star,
        color: const Color(0xFFFACC15),
      ),
    );
  }
}
