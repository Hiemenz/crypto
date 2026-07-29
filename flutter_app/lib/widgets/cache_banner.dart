import 'package:flutter/material.dart';

/// Shown above a list when it's displaying a cached copy while a fresh
/// fetch is still in flight (or the fresh fetch failed and this is all
/// that's available, e.g. offline).
class CacheBanner extends StatelessWidget {
  final DateTime? fetchedAt;

  const CacheBanner({super.key, this.fetchedAt});

  String _age() {
    if (fetchedAt == null) return '';
    final diff = DateTime.now().difference(fetchedAt!);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: const Color(0xFF33301A),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, size: 14, color: Color(0xFFFACC15)),
          const SizedBox(width: 8),
          Text(
            'Showing cached data${fetchedAt != null ? ' from ${_age()}' : ''} -- refreshing...',
            style: const TextStyle(color: Color(0xFFFACC15), fontSize: 12),
          ),
        ],
      ),
    );
  }
}
