import 'package:flutter/material.dart';

import '../models/signal.dart';
import '../services/api_client.dart';
import '../services/api_config.dart';
import '../services/notification_service.dart';
import '../services/ntfy_config.dart';
import '../services/ntfy_service.dart';

class SettingsScreen extends StatefulWidget {
  final ApiClient? apiClient;

  const SettingsScreen({super.key, this.apiClient});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final ApiClient _api = widget.apiClient ?? ApiClient();
  late final TextEditingController _apiUrlController;
  late final TextEditingController _ntfyServerController;
  late final TextEditingController _ntfyTopicController;

  bool _ntfyEnabled = false;
  String _notifPermission = 'default';

  @override
  void initState() {
    super.initState();
    _apiUrlController = TextEditingController(text: ApiConfig.baseUrl);
    _ntfyServerController = TextEditingController();
    _ntfyTopicController = TextEditingController();
    _loadNtfySettings();
    _notifPermission = NotificationService.permission;
  }

  Future<void> _loadNtfySettings() async {
    final server = await NtfyConfig.getServer();
    final topic = await NtfyConfig.getTopic();
    final enabled = await NtfyConfig.getEnabled();
    if (!mounted) return;
    setState(() {
      _ntfyServerController.text = server;
      _ntfyTopicController.text = topic;
      _ntfyEnabled = enabled;
    });
  }

  @override
  void dispose() {
    _apiUrlController.dispose();
    _ntfyServerController.dispose();
    _ntfyTopicController.dispose();
    super.dispose();
  }

  Future<void> _saveApiUrl() async {
    await ApiConfig.setBaseUrl(_apiUrlController.text.trim());
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Saved. Restart the app for it to fully take effect.')),
      );
    }
  }

  Future<void> _requestNotifPermission() async {
    final granted = await NotificationService.requestPermission();
    setState(() => _notifPermission = NotificationService.permission);
    if (!granted && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Notifications blocked -- enable them in your browser\'s site settings.')),
      );
    }
  }

  Future<void> _saveNtfySettings() async {
    final server = _ntfyServerController.text.trim();
    final topic = _ntfyTopicController.text.trim();
    await NtfyConfig.save(server: server, topic: topic, enabled: _ntfyEnabled);
    if (_ntfyEnabled && topic.isNotEmpty) {
      NtfyService.connect(server: server, topic: topic);
    } else {
      NtfyService.stop();
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_ntfyEnabled ? 'Connected to $topic' : 'Live notifications disabled')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _SectionHeader('API'),
          const Text('API base URL', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          TextField(
            controller: _apiUrlController,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'http://localhost:8000',
            ),
          ),
          const SizedBox(height: 12),
          FilledButton(onPressed: _saveApiUrl, child: const Text('Save')),
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              'Point this at wherever api.py is running: local dev, your LAN IP for '
              'testing on a phone, or a deployed URL.',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 12.5),
            ),
          ),

          _SectionHeader('Live Notifications (ntfy.sh)'),
          Text(
            'Uses the same ntfy topic you configure in cryptos.yml\'s notify: '
            'section on the backend. Signal changes and price alerts posted '
            'there show up here as browser notifications while this tab is open.',
            style: TextStyle(color: Colors.grey.shade400, fontSize: 12.5),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Text('Browser permission: $_notifPermission'),
              ),
              if (_notifPermission != 'granted')
                TextButton(onPressed: _requestNotifPermission, child: const Text('Allow')),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _ntfyServerController,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              labelText: 'ntfy server',
              hintText: 'https://ntfy.sh',
            ),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _ntfyTopicController,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              labelText: 'Topic (must match cryptos.yml notify.ntfy_topic)',
            ),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Enable live notifications'),
            value: _ntfyEnabled,
            onChanged: (v) => setState(() => _ntfyEnabled = v),
          ),
          FilledButton(onPressed: _saveNtfySettings, child: const Text('Save')),

          _SectionHeader('Price Alerts'),
          Text(
            'Managed on the backend (price_alerts: in cryptos.yml) and checked '
            'every pipeline refresh -- these fire even when the app is closed.',
            style: TextStyle(color: Colors.grey.shade400, fontSize: 12.5),
          ),
          const SizedBox(height: 12),
          _PriceAlertsSection(api: _api),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader(this.title);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 8),
      child: Text(
        title,
        style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
      ),
    );
  }
}

class _PriceAlertsSection extends StatefulWidget {
  final ApiClient api;
  const _PriceAlertsSection({required this.api});

  @override
  State<_PriceAlertsSection> createState() => _PriceAlertsSectionState();
}

class _PriceAlertsSectionState extends State<_PriceAlertsSection> {
  late Future<List<PriceAlert>> _future;
  final _symbolController = TextEditingController();
  final _thresholdController = TextEditingController();
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _future = widget.api.getAlerts();
  }

  void _refresh() => setState(() { _future = widget.api.getAlerts(); });

  Future<void> _add() async {
    final symbol = _symbolController.text.trim().toUpperCase();
    final threshold = double.tryParse(_thresholdController.text.trim());
    if (symbol.isEmpty || threshold == null) return;
    setState(() => _saving = true);
    try {
      await widget.api.upsertAlert(symbol, threshold);
      _symbolController.clear();
      _thresholdController.clear();
      _refresh();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _delete(String symbol) async {
    try {
      await widget.api.deleteAlert(symbol);
      _refresh();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
      }
    }
  }

  @override
  void dispose() {
    _symbolController.dispose();
    _thresholdController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FutureBuilder<List<PriceAlert>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: LinearProgressIndicator(),
              );
            }
            if (snap.hasError) {
              return Text('Could not load alerts: ${snap.error}');
            }
            final alerts = snap.data ?? [];
            if (alerts.isEmpty) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text('No price alerts configured.'),
              );
            }
            return Column(
              children: alerts.map((a) {
                return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(a.symbol),
                  subtitle: Text('Alert at \$${a.threshold.toStringAsFixed(2)}'),
                  trailing: IconButton(
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () => _delete(a.symbol),
                  ),
                );
              }).toList(),
            );
          },
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _symbolController,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  labelText: 'Symbol',
                  hintText: 'BTC-USD',
                ),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 120,
              child: TextField(
                controller: _thresholdController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  labelText: 'Price',
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: _saving ? null : _add,
              icon: const Icon(Icons.add),
            ),
          ],
        ),
      ],
    );
  }
}
