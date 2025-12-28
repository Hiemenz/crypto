import React, { useState, useEffect, useMemo } from 'react';
import { ComposedChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Scatter } from 'recharts';
import { Calculator, TrendingUp, DollarSign, Calendar, Info, RefreshCw } from 'lucide-react';

const ASSETS = [
    { symbol: 'BTC-USD', name: 'Bitcoin' },
    { symbol: 'ETH-USD', name: 'Ethereum' },
    { symbol: 'SOL-USD', name: 'Solana' }
];

const TIME_RANGES = [
    { label: '1 Year', days: 365 },
    { label: '3 Years', days: 365 * 3 },
    { label: '5 Years', days: 365 * 5 },
    { label: 'All Time', days: 3650 } // Approx 10 years
];

const StrategySimulator = ({ mode = 'demo' }) => {
    // State
    const [selectedAsset, setSelectedAsset] = useState(ASSETS[0]);
    const [timeRange, setTimeRange] = useState(TIME_RANGES[0]); // Default 1 Year
    const [investmentAmount, setInvestmentAmount] = useState(10000); // Initial Capital

    // Trade Logic State
    const [buyStrength, setBuyStrength] = useState(100); // % of CASH to spend per buy signal
    const [sellPercentage, setSellPercentage] = useState(50); // % of holdings to sell per signal

    // Date State
    const [startDate, setStartDate] = useState(''); // Custom start date string YYYY-MM-DD
    const [useCustomDate, setUseCustomDate] = useState(false);

    const [feeRate, setFeeRate] = useState(0.1); // Pro feature: fee percentage
    const [availableAssets, setAvailableAssets] = useState(ASSETS);
    const [loadingAssets, setLoadingAssets] = useState(false);

    // Data State
    const [historyData, setHistoryData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Fetch available assets
    useEffect(() => {
        const fetchAssets = async () => {
            setLoadingAssets(true);
            try {
                const response = await fetch('/data/latest_signals.json');
                if (response.ok) {
                    const json = await response.json();
                    // Extract unique symbols.
                    // Assuming json.signals is an array of objects with a 'symbol' property.
                    const uniqueSymbols = [...new Set(json.signals.map(s => s.symbol))].sort();

                    // Create asset objects
                    const newAssets = uniqueSymbols.map(s => ({
                        symbol: s,
                        name: s // Use symbol as name for now
                    }));

                    if (newAssets.length > 0) {
                        setAvailableAssets(newAssets);
                        // Optional: ensure currently selected asset is still valid or switch to first
                        // But if we start with defaults, we might want to keep the current selection if it exists in new list
                    }
                }
            } catch (e) {
                console.error("Failed to load asset list", e);
            } finally {
                setLoadingAssets(false);
            }
        };
        fetchAssets();
    }, []);

    // Fetch Data for selected asset
    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const response = await fetch(`/data/history/${selectedAsset.symbol}.json`);
                if (!response.ok) throw new Error('Failed to load data');
                const json = await response.json();
                setHistoryData(json.data);
            } catch (err) {
                console.error("Simulation load error:", err);
                setError("Could not load historical data for this asset.");
            } finally {
                setLoading(false);
            }
        };

        if (selectedAsset?.symbol) {
            fetchData();
        }
    }, [selectedAsset]);

    // Simulation Logic
    const fullSimulation = useMemo(() => {
        if (!historyData || historyData.length === 0) return null;

        // Filter by date range
        let filterDate;

        if (useCustomDate && startDate) {
            filterDate = new Date(startDate);
        } else {
            const endDate = new Date(historyData[historyData.length - 1].Date);
            filterDate = new Date(endDate);
            filterDate.setDate(filterDate.getDate() - timeRange.days);
        }

        const filteredData = historyData.filter(item => new Date(item.Date) >= filterDate);

        if (filteredData.length === 0) return null;

        // Run Simulation
        let cash = investmentAmount;
        let cryptoUnits = 0;
        let avgEntryPrice = 0; // Weighted average entry price for Win Rate calc

        let tradeCount = 0;
        let profitableTrades = 0;

        const results = filteredData.map((day) => {
            const price = day.Close;
            const signal = (day.signal || "").toLowerCase();

            // Trading Logic
            let action = 'hold';

            // Fee Multiplier
            const feeMultiplier = 1 - (feeRate / 100);

            if (signal.includes('buy')) {
                // Buy Logic: Spend PERCENTAGE of available cash
                let cashToSpend = cash * (buyStrength / 100);

                // Minimum trade threshold (e.g. $10)
                if (cashToSpend > 10) {
                    const unitsBought = (cashToSpend * feeMultiplier) / price;

                    // Update Weighted Average Entry Price
                    const currentVal = cryptoUnits * avgEntryPrice;
                    const newVal = unitsBought * price;
                    avgEntryPrice = (currentVal + newVal) / (cryptoUnits + unitsBought);

                    cryptoUnits += unitsBought;
                    cash -= cashToSpend;
                    action = 'buy';
                    tradeCount++;
                }

            } else if (signal.includes('sell')) {
                // Sell Logic: Sell a PERCENTAGE of held units
                const unitsToSell = cryptoUnits * (sellPercentage / 100);

                // Minimum value threshold
                const valueOfSell = unitsToSell * price;
                if (valueOfSell > 10) {
                    const cashGained = (unitsToSell * price) * feeMultiplier;

                    // Win Rate Logic: Did we sell higher than our average entry?
                    if (price > avgEntryPrice) {
                        profitableTrades++;
                    }

                    cash += cashGained;
                    cryptoUnits -= unitsToSell;
                    action = 'sell';
                    tradeCount++;
                }
            }

            // Calculate Portfolio Value
            // Total value = Cash + (Crypto Units * Current Price)
            const strategyValue = cash + (cryptoUnits * price);
            return {
                date: day.Date,
                price: price,
                strategy: Math.round(strategyValue),
                action: action,
                signal: day.signal,
                // Scatter plot points (only present when trade occurs)
                buyPoint: action === 'buy' ? Math.round(strategyValue) : null,
                sellPoint: action === 'sell' ? Math.round(strategyValue) : null
            };
        });

        const finalResult = results[results.length - 1];
        const initialValue = investmentAmount;
        const finalStrategy = finalResult.strategy;
        const netProfit = finalStrategy - initialValue;

        return {
            chartData: results,
            finalStrategy: finalStrategy,
            netProfit: netProfit,
            strategyROI: ((finalStrategy - initialValue) / initialValue) * 100,
            tradeCount,
            winRate: tradeCount > 0 ? (profitableTrades / tradeCount) * 100 : 0
        };

    }, [historyData, timeRange, investmentAmount, feeRate, buyStrength, sellPercentage, startDate, useCustomDate]);


    // Formatting
    const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val);

    if (loading) return <div className="p-8 text-center text-gray-500 animate-pulse">Loading simulation data...</div>;
    if (error) return <div className="p-8 text-center text-red-400">{error}</div>;
    if (!fullSimulation) {
        return <div className="p-8 text-center text-gray-500">Not enough data for this range.</div>;
    }

    const { chartData, finalStrategy, netProfit, strategyROI, tradeCount, winRate } = fullSimulation;

    const isProfitable = finalStrategy > investmentAmount;

    return (
        <div className={`w-full max-w-5xl mx-auto rounded-3xl overflow-hidden border border-white/10 ${mode === 'demo' ? 'bg-[#121212]/80 backdrop-blur-xl shadow-2xl' : 'bg-[#1E2228]'} transition-all duration-300`}>

            {/* Header / Controls */}
            <div className="p-6 md:p-8 border-b border-white/5">
                <div className="flex flex-col md:flex-row justify-between items-center gap-6 mb-8 start-header">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center">
                            <Calculator className="text-cyan-400" size={20} />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-white">Profit Explorer</h2>
                            <p className="text-xs text-gray-400">Backtest our signals to see potential returns</p>
                        </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                        {/* Asset Selector */}
                        {/* Asset Selector */}
                        <select
                            value={selectedAsset.symbol}
                            onChange={(e) => {
                                const found = availableAssets.find(a => a.symbol === e.target.value);
                                if (found) setSelectedAsset(found);
                            }}
                            disabled={loadingAssets}
                            className="bg-black/30 border border-white/10 rounded-lg px-4 py-2 text-sm text-white focus:outline-none focus:border-cyan-500/50 max-w-[140px] truncate"
                        >
                            {loadingAssets ? (
                                <option>Loading...</option>
                            ) : (
                                availableAssets.map(asset => (
                                    <option key={asset.symbol} value={asset.symbol}>{asset.name}</option>
                                ))
                            )}
                        </select>

                        {/* Time Range / Date Picker */}
                        <div className="flex flex-col items-end gap-2">
                            <div className="flex bg-black/30 rounded-lg p-1 border border-white/10">
                                {TIME_RANGES.map(range => (
                                    <button
                                        key={range.label}
                                        onClick={() => {
                                            setTimeRange(range);
                                            setUseCustomDate(false);
                                        }}
                                        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${!useCustomDate && timeRange.label === range.label
                                            ? 'bg-blue-600 text-white shadow-lg'
                                            : 'text-gray-400 hover:text-white hover:bg-white/5'
                                            }`}
                                    >
                                        {range.label}
                                    </button>
                                ))}
                                <button
                                    onClick={() => setUseCustomDate(true)}
                                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${useCustomDate
                                        ? 'bg-blue-600 text-white shadow-lg'
                                        : 'text-gray-400 hover:text-white hover:bg-white/5'
                                        }`}
                                >
                                    Custom
                                </button>
                            </div>

                            {useCustomDate && (
                                <div className="flex items-center gap-2 animate-in fade-in slide-in-from-top-1">
                                    <label className="text-xs text-gray-500 font-bold uppercase">Start:</label>
                                    <input
                                        type="date"
                                        value={startDate}
                                        onChange={(e) => setStartDate(e.target.value)}
                                        className="bg-black/30 border border-white/10 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-cyan-500/50"
                                    />
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Investment Input */}
                <div className="flex flex-col sm:flex-row gap-6 items-center justify-center p-4 bg-black/20 rounded-2xl border border-white/5">
                    <div className="w-full sm:w-auto">
                        <label className="text-xs text-gray-500 uppercase font-bold tracking-wider mb-2 block">Investment Amount</label>
                        <div className="flex items-center gap-2">
                            <span className="text-2xl text-gray-400">$</span>
                            <input
                                type="number"
                                value={investmentAmount}
                                onChange={(e) => setInvestmentAmount(Number(e.target.value))}
                                className="bg-transparent text-3xl font-bold text-white w-40 focus:outline-none"
                            />
                        </div>
                    </div>

                    <div className="hidden sm:block w-px h-12 bg-white/10"></div>

                    <div className="w-full sm:flex-1">
                        <label className="text-xs text-gray-500 uppercase font-bold tracking-wider mb-2 block">Initial Amount</label>
                        <input
                            type="range"
                            min="1000"
                            max="100000"
                            step="1000"
                            value={investmentAmount}
                            onChange={(e) => setInvestmentAmount(Number(e.target.value))}
                            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-cyan-500 hover:accent-cyan-400 transition-all mb-4"
                        />

                        {/* Buy Control */}
                        <div className="mb-4">
                            <div className="flex justify-between items-center mb-1">
                                <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">Buy Strength (%)</label>
                                <span className="text-xs font-bold text-green-400">{buyStrength}%</span>
                            </div>
                            <input
                                type="range"
                                min="1"
                                max="100"
                                step="1"
                                value={buyStrength}
                                onChange={(e) => setBuyStrength(Number(e.target.value))}
                                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-green-500 hover:accent-green-400 transition-all"
                            />
                            <p className="text-[10px] text-gray-500 mt-1">% of available cash to spend per BUY signal.</p>
                        </div>

                        {/* Sell Control */}
                        <div>
                            <div className="flex justify-between items-center mb-1">
                                <label className="text-xs text-gray-500 uppercase font-bold tracking-wider">Sell Percentage (%)</label>
                                <span className="text-xs font-bold text-red-400">{sellPercentage}%</span>
                            </div>
                            <input
                                type="range"
                                min="1"
                                max="100"
                                step="1"
                                value={sellPercentage}
                                onChange={(e) => setSellPercentage(Number(e.target.value))}
                                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-red-500 hover:accent-red-400 transition-all"
                            />
                            <p className="text-[10px] text-gray-500 mt-1">% of holdings to sell per SELL signal.</p>
                        </div>

                    </div>
                </div>

                {/* Pro Feature: Fees */}
                {mode === 'pro' && (
                    <div className="mt-4 flex items-center justify-end gap-3">
                        <label className="text-xs text-gray-400">Trading Fee %</label>
                        <input
                            type="number"
                            step="0.01"
                            value={feeRate}
                            onChange={(e) => setFeeRate(Number(e.target.value))}
                            className="w-16 bg-black/30 border border-white/10 rounded px-2 py-1 text-xs text-right focus:outline-none focus:border-cyan-500/50"
                        />
                    </div>
                )}
            </div>

            {/* Results Grid */}
            {/* Results Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-white/10 border-b border-white/10 bg-black/20">
                {/* Result 1: Net Profit */}
                <div className="p-6 text-center">
                    <p className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-1">Total Net Profit</p>
                    <h3 className={`text-4xl font-bold mb-1 ${isProfitable ? 'text-green-400' : 'text-red-400'}`}>
                        {netProfit >= 0 ? '+' : ''}{formatCurrency(netProfit)}
                    </h3>
                    <div className="text-xs text-gray-500 font-medium">
                        Ending Value: <span className="text-white">{formatCurrency(finalStrategy)}</span>
                    </div>
                </div>

                {/* Result 2: ROI */}
                <div className="p-6 text-center">
                    <p className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-1">Total ROI</p>
                    <h3 className={`text-4xl font-bold mb-1 ${strategyROI >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {strategyROI >= 0 ? '+' : ''}{strategyROI.toFixed(1)}%
                    </h3>
                    <div className="text-xs text-gray-500">
                        Return on Investment
                    </div>
                </div>

                {/* Result 3: Win Rate / Trades */}
                <div className="p-6 text-center">
                    <p className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-1">Win Rate</p>
                    <h3 className="text-4xl font-bold mb-1 text-cyan-400">
                        {winRate.toFixed(0)}%
                    </h3>
                    <p className="text-xs text-gray-500">
                        {tradeCount} Total Trades Executed
                    </p>
                </div>
            </div>

            {/* Chart */}
            <div className="h-[300px] w-full p-4 relative">
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorStrategy" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <XAxis
                            dataKey="date"
                            stroke="#4b5563"
                            tick={{ fontSize: 10, fill: '#9ca3af' }}
                            tickFormatter={(val) => new Date(val).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                            minTickGap={30}
                        />
                        <YAxis
                            stroke="#4b5563"
                            tick={{ fontSize: 10, fill: '#9ca3af' }}
                            tickFormatter={(val) => `$${val / 1000}k`}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '0.5rem' }}
                            itemStyle={{ color: '#fff' }}
                            formatter={(val, name) => {
                                if (name === 'buyPoint') return [`$${val.toLocaleString()}`, 'Buy Executed'];
                                if (name === 'sellPoint') return [`$${val.toLocaleString()}`, 'Sell Executed'];
                                return [`$${val.toLocaleString()}`, name];
                            }}
                            labelFormatter={(label) => new Date(label).toLocaleDateString()}
                        />
                        <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                        <Area
                            type="monotone"
                            dataKey="strategy"
                            name="Strategy"
                            stroke="#06b6d4"
                            fillOpacity={1}
                            fill="url(#colorStrategy)"
                            strokeWidth={3}
                        />
                        {/* Scatter for Buys (Green Dots) */}
                        <Scatter
                            dataKey="buyPoint"
                            fill="#10b981"
                            shape="circle"
                            r={4}
                            name="Buy Executed" // For Legend
                            legendType="none" // Hide generic scatter icon, we just want it on chart or specific custom legend behavior
                        />
                        {/* Scatter for Sells (Red Dots) */}
                        <Scatter
                            dataKey="sellPoint"
                            fill="#ef4444"
                            shape="circle"
                            r={4}
                            name="Sell Executed"
                            legendType="none"
                        />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>

            {/* Disclaimer */}
            <div className="bg-black/40 p-4 border-t border-white/5 flex items-start gap-3">
                <Info className="flex-shrink-0 text-gray-600 mt-0.5" size={14} />
                <p className="text-[10px] text-gray-500 leading-relaxed">
                    <strong>Historical Simulation Disclaimer:</strong> Results are based on historical data including open/close prices and generated signals.
                    Calculations assume buys occur at the closing price of the signal candle. Past performance is not indicative of future results.
                    {mode === 'demo' && " This demo assumes 0% trading fees."}
                    {mode === 'pro' && ` Includes a simulated ${feeRate}% trading fee per transaction.`}
                </p>
            </div>
        </div>
    );
};

export default StrategySimulator;
