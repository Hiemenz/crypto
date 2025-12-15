
import React, { useState, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell, ComposedChart, Line } from 'recharts';
import { CandlestickChart, LineChart as LineChartIcon, Maximize2 } from 'lucide-react';

// Custom Candle Shape
const CandleStick = (props) => {
    const { x, y, width, height, low, high, open, close } = props;
    const isUp = close >= open;
    const color = isUp ? 'var(--trade-up)' : 'var(--trade-down)';
    const ratio = Math.abs(height / (open - close));

    // Calculate strict pixel positions
    // This is tricky in Recharts custom shapes as 'y' and 'height' are pre-calculated for the 'value' (often close or max)
    // A robust way often involves passing the scale, but standard composed chart might be easier if we format data as [min, max]
    // SIMPLIFIED APPROACH: Use built-in ErrorBar or ReferenceLine? 
    // BETTER: Draw SVG manually based on passed scaled values if available, OR use a library designed for it. 
    // RECHARTS doesn't have native Candlestick. 
    // We will use a composed chart where the 'bar' is the body (open-close) and an error bar is the wick? 
    // actually, let's use the 'shape' prop on a Bar to draw the whole candle.
    return (
        <g stroke={color} fill={color} strokeWidth="2">
            <path d={`
          M ${x + width / 2}, ${props.yHigh}
          L ${x + width / 2}, ${props.yLow}
        `} />
            <rect
                x={x}
                y={props.yBodyTop}
                width={width}
                height={props.bodyHeight < 1 ? 1 : props.bodyHeight}
                fill={color}
                stroke="none"
            />
        </g>
    );
};

// Recharts doesn't pass scaled High/Low natively to Bar shape easily without custom data keys.
// A common workaround is to use ErrorBars or prepare data specifically.
// Given the constraints and speed, implementing a robust custom shape might be error prone without trial.
// ALTERNATIVE: Use a simple composed chart with a Bar for the body and ErrorBar for wicks, OR just 
// accept that pure Recharts candlesticks are hard. 
// Let's use a simpler "OHLC" visualization or stick to the requested toggle but implementation might need care.
// Plan B: Use a standard implementation pattern for Recharts Candlesticks.
// Data needs: { high, low, open, close }

const prepareCandleData = (data) => {
    return data.map(d => ({
        ...d,
        // For the body (Bar), we need [min(Open, Close), max(Open, Close)]
        // Recharts Bar can take [min, max]
        body: [Math.min(d.Open, d.Close), Math.max(d.Open, d.Close)],
        // For wicks, we might need separate lines or use the custom shape approach passing pure values
    }))
}

const ChartSection = ({ data, symbol, range, onRangeChange, currentSignal }) => {
    // Process data to ensure numbers
    const processedData = useMemo(() => {
        if (!data) return [];
        return data.map(d => ({
            ...d,
            dateStr: new Date(d.date).toLocaleDateString(),
            Open: parseFloat(d.Open),
            High: parseFloat(d.High),
            Low: parseFloat(d.Low),
            Close: parseFloat(d.Close),
        }));
    }, [data]);

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            const d = payload[0].payload;
            return (
                <div className="bg-panel border border-border-subtle p-3 rounded-lg shadow-xl backdrop-blur-md bg-opacity-90">
                    <p className="text-muted text-xs font-semibold mb-2">{label}</p>
                    <div className="space-y-1 text-sm font-mono">
                        <div className="flex justify-between gap-4"><span className="text-muted">C:</span> <span className="text-white font-bold">{d.Close?.toFixed(2)}</span></div>
                        {/* Removed OHLC values for simpler tooltip if just Area, but keeping them is fine too if data exists */}
                    </div>
                </div>
            );
        }
        return null;
    };

    return (
        <div className="flex flex-col h-full bg-app relative">
            {/* Chart Header */}
            <div className="flex items-start justify-between p-6">
                <div>
                    <h2 className="text-3xl font-display font-bold text-primary flex items-center gap-3">
                        {symbol}
                        {currentSignal && (
                            <span className={`text-xs px-2 py-1 rounded-full border ${currentSignal.side === 'buy' ? 'border-trade-up/30 text-trade-up bg-trade-up/10' :
                                currentSignal.side === 'sell' ? 'border-trade-down/30 text-trade-down bg-trade-down/10' :
                                    'border-trade-accent/30 text-trade-accent bg-trade-accent/10'
                                }`}>
                                {currentSignal.side.toUpperCase()}
                            </span>
                        )}
                    </h2>
                    <div className="flex items-center gap-4 mt-2">
                        <span className="text-2xl font-mono font-medium text-white">
                            ${currentSignal ? currentSignal.Close?.toLocaleString() : '---'}
                        </span>
                    </div>
                </div>

                {/* Controls */}
                <div className="flex flex-col items-end gap-3">
                    {/* Range Selector */}
                    <div className="flex bg-panel border border-border-subtle rounded-lg p-1">
                        {['1M', '3M', '1Y', '3Y', '5Y', 'ALL'].map(r => (
                            <button
                                key={r}
                                onClick={() => onRangeChange(r)}
                                className={`px-3 py-1 text-xs font-bold rounded-md transition-all ${range === r ? 'bg-white text-black' : 'text-muted hover:text-white'
                                    }`}
                            >
                                {r}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Chart Area */}
            <div className="flex-1 w-full min-h-[300px] px-2 pb-4">
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={processedData}>
                        <defs>
                            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="var(--trade-accent)" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="var(--trade-accent)" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <XAxis
                            dataKey="date"
                            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                            tickFormatter={(str) => str.substring(5, 10)}
                            axisLine={false}
                            tickLine={false}
                            dy={10}
                            minTickGap={30}
                        />
                        <YAxis
                            orientation="right"
                            domain={['auto', 'auto']}
                            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            width={50}
                        />
                        <Tooltip content={<CustomTooltip />} />

                        <Area
                            type="monotone"
                            dataKey="Close"
                            stroke="var(--trade-accent)"
                            strokeWidth={2}
                            fillOpacity={1}
                            fill="url(#colorPrice)"
                        />

                        {/* Signal Markers */}
                        <Line
                            dataKey="Close"
                            stroke="none"
                            dot={(props) => {
                                const { cx, cy, payload } = props;
                                if (!payload.signalType) return null;
                                const isBuy = payload.signalType === 'buy';
                                const color = isBuy ? 'var(--trade-up)' : 'var(--trade-down)';
                                return (
                                    <circle cx={cx} cy={cy} r={4} fill={color} stroke="#0B0F14" strokeWidth={2} />
                                );
                            }}
                            activeDot={false}
                            legendType="none"
                            isAnimationActive={false}
                        />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};

export default ChartSection;
