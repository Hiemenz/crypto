import 'package:flutter/material.dart';

class SignalBadge extends StatelessWidget {
  final String label;
  final bool isBuy;
  final bool isSell;

  const SignalBadge({
    super.key,
    required this.label,
    required this.isBuy,
    required this.isSell,
  });

  @override
  Widget build(BuildContext context) {
    final Color bg;
    final Color fg;
    if (isBuy) {
      bg = const Color(0xFF163B2E);
      fg = const Color(0xFF4ADE80);
    } else if (isSell) {
      bg = const Color(0xFF3B1620);
      fg = const Color(0xFFF87171);
    } else {
      bg = const Color(0xFF33301A);
      fg = const Color(0xFFFACC15);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: fg,
          fontWeight: FontWeight.w600,
          fontSize: 12,
        ),
      ),
    );
  }
}
