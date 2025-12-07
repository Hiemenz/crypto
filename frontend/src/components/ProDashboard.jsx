import React, { useState, useEffect, useMemo } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Scatter
} from 'recharts';
import { Search, ArrowUp, ArrowDown, ExternalLink, Menu, X, Zap, TrendingUp, Activity } from 'lucide-react';

const formatPrice = (p) => p < 1 ? p?.toFixed(5) : p?.toLocaleString(undefined, { maximumFractionDigits: 2 });

const SignalMarker = ({ cx, cy, payload }) => {
    if (!payload.signalType) return null;
    const isBuy = payload.signalType === 'buy';
    const color = isBuy ? '#10b981' : '#ef4444';
    return (
        <path
            d={isBuy ? `M${cx},${cy + 12} L${cx + 6},${cy} L${cx - 6},${cy} Z` : `M${cx},${cy - 12} L${cx + 6},${cy} L${cx - 6},${cy} Z`}
            fill={color}
        />
    );
};

const ProDashboard = () => {
    const [latestSignals, setLatestSignals] = useState([]);
    const [crossesData, setCrossesData] = useState([]);
    const [historyData, setHistoryData] = useState(null);
    const [activeTab, setActiveTab] = useState('crypto');
    const [selectedSymbol, setSelectedSymbol] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [loading, setLoading] = useState(true);
    const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 1024);
    const [chartRange, setChartRange] = useState('ALL');

    useEffect(() => {
        Promise.all([
            fetch('/data/latest_signals.json').then(res => res.json()),
            fetch('/data/crosses.json').then(res => res.json())
        ]).then(([signalsRes, crossesRes]) => {
            setLatestSignals(signalsRes.signals);
            setCrossesData(crossesRes.crosses);
            const defaultSym = signalsRes.signals.find(s => s.category === 'crypto')?.symbol;
            if (defaultSym) setSelectedSymbol(defaultSym);
            setLoading(false);
        }).catch(err => {
            console.error("Data load failed:", err);
            setLoading(false);
        });
    }, []);

    useEffect(() => {
        if (!selectedSymbol) return;
        if (window.innerWidth < 1024) setSidebarOpen(false);

        setHistoryData(null);
        fetch(`/data/history/${selectedSymbol}.json`)
            .then(res => res.json())
            .then(data => {
                const processed = data.data.map(item => ({
                    ...item,
                    time: new Date(item.Date).getTime(),
                    dateStr: item.Date,
                    Close: parseFloat(item.Close),
                    rsi: item.rsi,
                    mfi: item.mfi,
                    stoch_rsi: item.stoch_rsi,
                    Volume: item.Volume,
                    signalType: (item.signal && item.signal.includes('Buy')) ? 'buy' : (item.signal && item.signal.includes('Sell')) ? 'sell' : null
                }));
                setHistoryData(processed);
            })
            .catch(err => console.error("History fetch failed:", err));
    }, [selectedSymbol]);

    const assetList = useMemo(() => {
        return latestSignals
            .filter(s => s.category === activeTab)
            .filter(s => s.symbol.toLowerCase().includes(searchTerm.toLowerCase()))
            .sort((a, b) => b.score - a.score);
    }, [latestSignals, activeTab, searchTerm]);

    const currentAssetSignal = useMemo(() => latestSignals.find(s => s.symbol === selectedSymbol), [latestSignals, selectedSymbol]);

    const currentAssetCrosses = useMemo(() => {
        if (!selectedSymbol) return [];
        return crossesData
            .filter(c => c.symbol === selectedSymbol)
            .sort((a, b) => new Date(b.date) - new Date(a.date))
            .slice(0, 10);
    }, [crossesData, selectedSymbol]);

    const signalHistory = useMemo(() => {
        if (!historyData) return [];
        return historyData
            .filter(row => row.signal && row.signal !== 'Hold' && row.signal !== 'None')
            .slice().reverse();
    }, [historyData]);

    const chartData = useMemo(() => {
        if (!historyData) return [];
        if (chartRange === 'ALL') return historyData;
        const cutoff = new Date();
        if (chartRange === '1Y') cutoff.setFullYear(cutoff.getFullYear() - 1);
        if (chartRange === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
        return historyData.filter(d => new Date(d.dateStr) >= cutoff);
    }, [historyData, chartRange]);

    const signalPoints = useMemo(() => chartData.filter(d => d.signalType !== null), [chartData]);

    // Get latest metrics
    const latestMetrics = useMemo(() => {
        if (!historyData || historyData.length === 0) return null;
        const latest = historyData[historyData.length - 1];
        return {
            rsi: latest.rsi,
            mfi: latest.mfi,
            stochRsi: latest.stoch_rsi,
            volume: latest.Volume
        };
    }, [historyData]);

    if (loading) return <div className="h-screen flex items-center justify-center bg-[var(--bg-main)] text-[var(--text-secondary)]">Initializing Pro Terminal...</div>;

    return (
        <div className="flex h-screen overflow-hidden bg-[var(--bg-main)] text-[var(--text-primary)] font-sans relative fade-in">

            {/* MOBILE HEADER */}
            <div className="lg:hidden absolute top-0 left-0 right-0 h-16 bg-[var(--bg-surface)] border-b border-[var(--border-subtle)] flex items-center justify-between px-4 z-50 shadow-md">
                <div className="flex items-center gap-3">
                    <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 text-[var(--text-secondary)] hover:text-white transition-colors glow-on-hover">
                        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>
                    <span className="font-bold text-lg tracking-tight">{selectedSymbol}</span>
                </div>
                <span className="text-sm font-bold text-[var(--accent-primary)] font-mono">${formatPrice(currentAssetSignal?.Close)}</span>
            </div>

            {/* LEFT SIDEBAR */}
            <div className={`
          absolute lg:relative z-10 h-full w-80 bg-[var(--bg-surface)] border-r border-[var(--border-subtle)] flex flex-col transition-transform duration-300 shadow-2xl lg:shadow-none
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
                {/* Tabs with Icons */}
                <div className="flex border-b border-[var(--border-subtle)] pt-16 lg:pt-0 bg-[var(--bg-surface)]">
                    <button
                        onClick={() => setActiveTab('crypto')}
                        className={`flex-1 py-6 text-xs font-bold tracking-widest uppercase transition-all flex items-center justify-center gap-2 ${activeTab === 'crypto' ? 'text-[var(--accent-primary)] border-b-2 border-[var(--accent-primary)]' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}`}
                    >
                        <Zap size={14} />
                        Crypto
                    </button>
                    <button
                        onClick={() => setActiveTab('stocks')}
                        className={`flex-1 py-6 text-xs font-bold tracking-widest uppercase transition-all flex items-center justify-center gap-2 ${activeTab === 'stocks' ? 'text-[var(--accent-primary)] border-b-2 border-[var(--accent-primary)]' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'}`}
                    >
                        <TrendingUp size={14} />
                        Stocks
                    </button>
                </div>
                {/* Search */}
                <div className="p-6 border-b border-[var(--border-subtle)]">
                    <div className="relative bg-[var(--bg-main)] rounded-lg border border-[var(--border-subtle)] focus-within:border-[var(--accent-primary)] transition-all">
                        <Search className="absolute left-4 top-3.5 w-4 h-4 text-[var(--text-tertiary)]" />
                        <input
                            type="text"
                            placeholder="Search assets..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full bg-transparent border-none py-3 pl-12 pr-4 text-sm text-[var(--text-primary)] focus:ring-0 placeholder-[var(--text-tertiary)]"
                        />
                    </div>
                </div>

                {/* Asset List */}
                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 custom-scrollbar">
                    {assetList.map(item => (
                        <div
                            key={item.symbol}
                            onClick={() => setSelectedSymbol(item.symbol)}
                            className={`p-4 rounded-xl cursor-pointer transition-all border glow-on-hover ${selectedSymbol === item.symbol ? 'bg-[var(--bg-elevated)] border-[var(--accent-primary)] shadow-lg shadow-cyan-500/10' : 'border-transparent hover:bg-[var(--bg-hover)] hover:border-[var(--border-subtle)]'}`}
                        >
                            <div className="flex justify-between items-center mb-2">
                                <span className={`font-bold text-base ${selectedSymbol === item.symbol ? 'text-[var(--accent-primary)]' : 'text-[var(--text-secondary)]'}`}>{item.symbol}</span>
                                {item.side ? (
                                    <span className={`text-[10px] font-bold px-2 py-1 rounded-md uppercase tracking-wider ${item.side === 'buy' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : item.side === 'sell' ? 'bg-red-500/10 text-red-400 border border-red-500/20' : 'badge-hold'}`}>
                                        {item.side}
                                    </span>
                                ) : (
                                    <span className="badge-pill badge-hold">HOLD</span>
                                )}
                            </div>
                            <div className="flex justify-between items-center">
                                <span className="text-sm font-mono text-[var(--text-muted)]">${formatPrice(item.Close)}</span>
                                <div className="flex items-center gap-2">
                                    <div className="w-16 h-1.5 bg-[var(--bg-main)] rounded-full overflow-hidden">
                                        <div className="h-full bg-gradient-to-r from-cyan-500 to-blue-500" style={{ width: `${item.score}%` }}></div>
                                    </div>
                                    <span className="text-xs font-bold text-[var(--accent-primary)]">{item.score}</span>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* MAIN CONTENT */}
            <div className="flex-1 flex flex-col min-w-0 bg-[var(--bg-main)] pt-16 lg:pt-0">

                {/* Top Banner */}
                <div className="hidden lg:flex h-24 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] items-center justify-between px-10 shadow-sm z-10 relative">
                    <div className="flex items-center gap-8">
                        <h1 className="text-4xl font-bold tracking-tight text-white">{selectedSymbol}</h1>
                        <span className="text-3xl font-light text-[var(--text-secondary)] font-mono tracking-tight">${formatPrice(currentAssetSignal?.Close)}</span>
                    </div>

                    <div className="flex items-center gap-12">
                        <div className="text-right">
                            <div className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-widest font-bold mb-1">Recommendation</div>
                            <div className={`text-xl font-bold flex items-center justify-end gap-2 uppercase tracking-wide ${currentAssetSignal?.side === 'buy' ? 'text-emerald-400' : currentAssetSignal?.side === 'sell' ? 'text-red-400' : 'text-[var(--text-secondary)]'}`}>
                                {currentAssetSignal?.side === 'buy' && <ArrowUp className="w-5 h-5" />}
                                {currentAssetSignal?.side === 'sell' && <ArrowDown className="w-5 h-5" />}
                                {currentAssetSignal?.signal || "NEUTRAL"}
                            </div>
                        </div>

                        <div className="text-right">
                            <div className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-widest font-bold mb-1">Confidence</div>
                            <div className="text-3xl font-bold text-[var(--accent-primary)]">{currentAssetSignal?.score || 0}</div>
                        </div>

                        <button className="btn-accent px-6 py-2.5 text-sm shadow-lg shadow-cyan-500/10">Trade Now</button>
                    </div>
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-y-auto p-4 lg:p-8 space-y-8 custom-scrollbar">

                    {/* Metrics Panel */}
                    {latestMetrics && (
                        <div className="pro-card p-6 fade-in">
                            <div className="flex items-center gap-2 mb-4">
                                <Activity className="w-4 h-4 text-[var(--accent-primary)]" />
                                <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">Key Indicators</h3>
                            </div>
                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                                <div className="bg-[var(--bg-elevated)] p-4 rounded-lg border border-[var(--border-subtle)]">
                                    <div className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide mb-1">RSI</div>
                                    <div className="text-2xl font-bold text-[var(--accent-primary)]">{latestMetrics.rsi?.toFixed(1) || 'N/A'}</div>
                                </div>
                                <div className="bg-[var(--bg-elevated)] p-4 rounded-lg border border-[var(--border-subtle)]">
                                    <div className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide mb-1">MFI</div>
                                    <div className="text-2xl font-bold text-[var(--accent-primary)]">{latestMetrics.mfi?.toFixed(1) || 'N/A'}</div>
                                </div>
                                <div className="bg-[var(--bg-elevated)] p-4 rounded-lg border border-[var(--border-subtle)]">
                                    <div className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide mb-1">Stoch RSI</div>
                                    <div className="text-2xl font-bold text-[var(--accent-primary)]">{latestMetrics.stochRsi?.toFixed(2) || 'N/A'}</div>
                                </div>
                                <div className="bg-[var(--bg-elevated)] p-4 rounded-lg border border-[var(--border-subtle)]">
                                    <div className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide mb-1">Sentiment</div>
                                    <div className={`text-lg font-bold uppercase ${currentAssetSignal?.signal?.includes('Excellent') ? 'text-emerald-400' : currentAssetSignal?.signal?.includes('Great') ? 'text-cyan-400' : 'text-[var(--text-secondary)]'}`}>
                                        {currentAssetSignal?.signal?.includes('Excellent') ? 'EXCELLENT' : currentAssetSignal?.signal?.includes('Great') ? 'GREAT' : 'GOOD'}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Chart */}
                    <div className="pro-card p-8 flex flex-col relative h-[550px] fade-in">
                        <div className="flex flex-wrap justify-between items-center mb-8">
                            <div>
                                <h3 className="text-base font-bold text-[var(--text-primary)] uppercase tracking-wider mb-2">Market Performance</h3>
                                <p className="text-sm text-[var(--text-tertiary)]">{selectedSymbol} • {chartRange} • Daily Timeframe</p>
                            </div>

                            <div className="flex bg-[var(--bg-main)] rounded-lg p-1.5 border border-[var(--border-subtle)]">
                                {['3M', '1Y', 'ALL'].map(r => (
                                    <button
                                        key={r}
                                        onClick={() => setChartRange(r)}
                                        className={`px-5 py-2 text-xs font-bold rounded-md transition-all ${chartRange === r ? 'bg-[var(--accent-primary)] text-black shadow-lg' : 'text-[var(--text-secondary)] hover:text-white'}`}
                                    >
                                        {r}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="flex-1 w-full min-h-0">
                            {!historyData ? (
                                <div className="h-full flex items-center justify-center text-[var(--text-tertiary)]">
                                    <span className="animate-pulse">Loading Chart Data...</span>
                                </div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                                        <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" vertical={false} opacity={0.3} />
                                        <XAxis
                                            dataKey="dateStr"
                                            stroke="var(--text-tertiary)"
                                            tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }}
                                            tickFormatter={(val) => val.substring(0, 4) === new Date().getFullYear().toString() ? val.substring(5) : val.substring(2, 7)}
                                            minTickGap={50}
                                            axisLine={false}
                                            tickLine={false}
                                            dy={10}
                                        />
                                        <YAxis
                                            domain={['dataMin - dataMin * 0.05', 'dataMax + dataMax * 0.05']}
                                            stroke="var(--text-tertiary)"
                                            tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }}
                                            tickFormatter={(val) => val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(2)}
                                            orientation="right"
                                            axisLine={false}
                                            tickLine={false}
                                            dx={10}
                                            width={60}
                                        />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border-accent)', color: 'var(--text-primary)', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.3)' }}
                                            itemStyle={{ color: 'var(--text-secondary)' }}
                                            labelStyle={{ color: 'var(--accent-primary)', fontWeight: 'bold', marginBottom: '4px' }}
                                            labelFormatter={(l) => new Date(l).toLocaleDateString()}
                                        />
                                        <Line
                                            type="monotone"
                                            dataKey="Close"
                                            stroke="var(--accent-primary)"
                                            strokeWidth={2.5}
                                            dot={false}
                                            activeDot={{ r: 6, strokeWidth: 0, fill: '#fff' }}
                                        />
                                        <Scatter
                                            data={signalPoints}
                                            shape={<SignalMarker />}
                                            legendType="none"
                                            tooltipType="none"
                                        />
                                    </LineChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </div>

                    {/* Tables */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pb-8">

                        <div className="pro-card flex flex-col overflow-hidden h-96 fade-in">
                            <div className="p-4 border-b border-[var(--border-subtle)] flex justify-between items-center bg-[var(--bg-elevated)]">
                                <h3 className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">Algorithmic Crosses</h3>
                                <ExternalLink className="w-4 h-4 text-[var(--text-tertiary)] hover:text-white transition-colors cursor-pointer" />
                            </div>
                            <div className="overflow-y-auto flex-1">
                                <table className="pro-table">
                                    <thead className="sticky top-0 z-10 w-full">
                                        <tr>
                                            <th>Date</th>
                                            <th>Event</th>
                                            <th className="text-right">Price Level</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {currentAssetCrosses.length === 0 ? (
                                            <tr><td colSpan="3" className="p-8 text-center text-[var(--text-tertiary)] text-xs">No recent crosses found.</td></tr>
                                        ) : (
                                            currentAssetCrosses.map((cross, idx) => (
                                                <tr key={idx}>
                                                    <td className="font-mono">{cross.date.substring(0, 10)}</td>
                                                    <td>
                                                        <span className={`text-[10px] font-bold px-3 py-1.5 rounded-md uppercase tracking-wide border ${cross.type.includes('Golden') ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : 'text-red-400 border-red-500/30 bg-red-500/10'}`}>
                                                            {cross.type.replace('Confirmed ', '')}
                                                        </span>
                                                    </td>
                                                    <td className="text-right font-mono text-[var(--text-muted)]">${formatPrice(cross.price)}</td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div className="pro-card flex flex-col overflow-hidden h-96 fade-in">
                            <div className="p-4 border-b border-[var(--border-subtle)] flex justify-between items-center bg-[var(--bg-elevated)]">
                                <h3 className="text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">Signal Log</h3>
                            </div>
                            <div className="overflow-y-auto flex-1">
                                <table className="pro-table">
                                    <thead className="sticky top-0 z-10">
                                        <tr>
                                            <th>Date</th>
                                            <th>Action</th>
                                            <th className="text-right">Price</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {signalHistory.length === 0 ? (
                                            <tr><td colSpan="3" className="p-8 text-center text-[var(--text-tertiary)] text-xs">No signals generated yet.</td></tr>
                                        ) : (
                                            signalHistory.map((row, idx) => (
                                                <tr key={idx}>
                                                    <td className="font-mono">{row.Date.substring(0, 10)}</td>
                                                    <td>
                                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wide ${row.signal.includes('Buy') ? 'text-emerald-400' : 'text-red-400'}`}>
                                                            {row.signal}
                                                        </span>
                                                    </td>
                                                    <td className="text-right font-mono text-[var(--text-muted)]">${formatPrice(row.Close)}</td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>

                    </div>
                </div>

            </div>
        </div>
    );
};

export default ProDashboard;
