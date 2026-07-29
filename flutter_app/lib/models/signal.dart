class Signal {
  final String symbol;
  final String category;
  final String timeframe;
  final String date;
  final double? open, high, low, close, volume;
  final double? rsi, mfi, stochRsi, stochRsiK, stochRsiD;
  final double? bbUpper, bbLower, bbPband;
  final double? macd, macdSignal, macdHist;
  final double? ma50, ma200;
  final bool isBull;
  final String signal;

  Signal({
    required this.symbol,
    required this.category,
    required this.timeframe,
    required this.date,
    this.open,
    this.high,
    this.low,
    this.close,
    this.volume,
    this.rsi,
    this.mfi,
    this.stochRsi,
    this.stochRsiK,
    this.stochRsiD,
    this.bbUpper,
    this.bbLower,
    this.bbPband,
    this.macd,
    this.macdSignal,
    this.macdHist,
    this.ma50,
    this.ma200,
    required this.isBull,
    required this.signal,
  });

  static double? _d(dynamic v) => v == null ? null : (v as num).toDouble();

  factory Signal.fromJson(Map<String, dynamic> json) => Signal(
        symbol: json['symbol'],
        category: json['category'],
        timeframe: json['timeframe'],
        date: json['date'],
        open: _d(json['open']),
        high: _d(json['high']),
        low: _d(json['low']),
        close: _d(json['close']),
        volume: _d(json['volume']),
        rsi: _d(json['rsi']),
        mfi: _d(json['mfi']),
        stochRsi: _d(json['stoch_rsi']),
        stochRsiK: _d(json['stoch_rsi_k']),
        stochRsiD: _d(json['stoch_rsi_d']),
        bbUpper: _d(json['bb_upper']),
        bbLower: _d(json['bb_lower']),
        bbPband: _d(json['bb_pband']),
        macd: _d(json['macd']),
        macdSignal: _d(json['macd_signal']),
        macdHist: _d(json['macd_hist']),
        ma50: _d(json['ma_50']),
        ma200: _d(json['ma_200']),
        isBull: json['is_bull'] ?? false,
        signal: json['signal'] ?? 'Hold',
      );

  bool get isBuy => signal.toLowerCase().contains('buy');
  bool get isSell => signal.toLowerCase().contains('sell');
}

class WatchItem {
  final String symbol;
  final String category;
  final String timeframe;
  final String type;
  final double price;
  final List<String> reasons;
  final String market;

  WatchItem({
    required this.symbol,
    required this.category,
    required this.timeframe,
    required this.type,
    required this.price,
    required this.reasons,
    required this.market,
  });

  factory WatchItem.fromJson(Map<String, dynamic> json) => WatchItem(
        symbol: json['symbol'],
        category: json['category'],
        timeframe: json['timeframe'],
        type: json['type'],
        price: (json['price'] as num).toDouble(),
        reasons: List<String>.from(json['reasons'] ?? []),
        market: json['market'],
      );

  bool get isNearBuy => type == 'Near Buy';
}

class PriceAlert {
  final String symbol;
  final double threshold;

  PriceAlert({required this.symbol, required this.threshold});

  factory PriceAlert.fromJson(Map<String, dynamic> json) => PriceAlert(
        symbol: json['symbol'],
        threshold: (json['threshold'] as num).toDouble(),
      );
}

class CrossEvent {
  final String symbol;
  final String category;
  final String type;
  final double price;
  final String date;
  final double? k;
  final double? d;

  CrossEvent({
    required this.symbol,
    required this.category,
    required this.type,
    required this.price,
    required this.date,
    this.k,
    this.d,
  });

  factory CrossEvent.fromJson(Map<String, dynamic> json) => CrossEvent(
        symbol: json['symbol'],
        category: json['category'],
        type: json['type'],
        price: (json['price'] as num).toDouble(),
        date: json['date'],
        k: json['k'] == null ? null : (json['k'] as num).toDouble(),
        d: json['d'] == null ? null : (json['d'] as num).toDouble(),
      );

  bool get isBullish => type.toLowerCase().contains('golden');
}
