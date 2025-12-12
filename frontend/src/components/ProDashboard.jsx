import React, { useState, useEffect, useMemo } from 'react';
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Search, TrendingUp, Menu, X, Zap } from 'lucide-react';
import Header from './Header';

const formatPrice = (p) => p < 1 ? p?.toFixed(5) : p?.toLocaleString(undefined, { maximumFractionDigits: 2 });

const CustomDot = (props) => {
    const { cx, cy, payload } = props;
    if (!payload.signalType) return null;
    const isBuy = payload.signalType === 'buy';
    const color = isBuy ? '#10B981' : '#F59E0B';

    return (
        <g className="signal-dot">
            {/* Outer glow */}
            <circle cx={cx} cy={cy} r={8} fill={color} opacity={0.1} className="animate-pulse-slow" />
            {/* Middle ring */}
            <circle cx={cx} cy={cy} r={5} fill={color} opacity={0.25} />
            {/* Inner ring with border */}
            <circle cx={cx} cy={cy} r={4} fill="#0B0D10" stroke={color} strokeWidth={1.5} />
            {/* Center dot */}
            <circle cx={cx} cy={cy} r={2} fill={color} />
        </g>
    );
};

const ProDashboard = ({ onLogout }) => {
    const [signals, setSignals] = useState([]);
    const [crosses, setCrosses] = useState([]);
    const [historyData, setHistoryData] = useState(null);
    const [activeTab, setActiveTab] = useState('crypto');
    const [contentTab, setContentTab] = useState('token'); // 'token' or 'market'
    const [selectedSymbol, setSelectedSymbol] = useState('BTC-USD');
    const [searchTerm, setSearchTerm] = useState('');
    const [loading, setLoading] = useState(true);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [chartRange, setChartRange] = useState('ALL');



    // Mobile Master-Detail State
    const [mobileView, setMobileView] = useState('detail'); // 'list' | 'detail'

    useEffect(() => {
        Promise.all([
            fetch('/data/latest_signals.json').then(r => r.json()),
            fetch('/data/crosses.json').then(r => r.json())
        ]).then(([sig, cr]) => {
            setSignals(sig.signals);
            setCrosses(cr.crosses);

            // Default to BTC-USD
            // We already initialized state to BTC-USD, so only override if BTC is missing
            const btc = sig.signals.find(s => s.symbol === 'BTC-USD');
            if (btc) {
                if (selectedSymbol !== 'BTC-USD') setSelectedSymbol('BTC-USD');
                if (btc.category) setActiveTab(btc.category);
            } else {
                const firstCrypto = sig.signals.find(s => s.category === 'crypto');
                if (firstCrypto) {
                    setSelectedSymbol(firstCrypto.symbol);
                    setActiveTab('crypto');
                }
            }
            setLoading(false);
        }).catch(err => console.error('Load error:', err));
    }, []);

    useEffect(() => {
        if (!selectedSymbol) return;
        setHistoryData(null);
        console.log(`Fetching history for ${selectedSymbol}...`);

        console.log(`[DEBUG] Fetching /data/history/${selectedSymbol}.json`);
        fetch(`/data/history/${selectedSymbol}.json`)
            .then(res => {
                console.log('[DEBUG] Response status:', res.status);
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            })
            .then(json => {
                if (!json.data || !Array.isArray(json.data)) throw new Error('Invalid data format');
                const processed = json.data.map(d => ({
                    date: d.Date,
                    price: parseFloat(d.Close),
                    signalType: (d.signal && d.signal.includes('Buy')) ? 'buy' : (d.signal && d.signal.includes('Sell')) ? 'sell' : null
                }));
                console.log(`Loaded ${processed.length} points for ${selectedSymbol}`);
                setHistoryData(processed);
            })
            .catch(err => {
                console.error('History error:', err);
                // Optional: setHistoryError(err.message);
            });
    }, [selectedSymbol]);

    const assetList = useMemo(() =>
        signals.filter(s => s.category === activeTab)
            .filter(s => s.symbol.toLowerCase().includes(searchTerm.toLowerCase()))
            .sort((a, b) => b.score - a.score),
        [signals, activeTab, searchTerm]
    );

    const currentSignal = useMemo(() => signals.find(s => s.symbol === selectedSymbol), [signals, selectedSymbol]);

    // Auto-scroll to selected item
    useEffect(() => {
        if (!loading && selectedSymbol) {
            const el = document.getElementById(`asset-${selectedSymbol}`);
            if (el) {
                el.scrollIntoView({ block: 'center', behavior: 'smooth' });
            }
        }
    }, [loading, selectedSymbol, activeTab]);

    // TOKEN SPECIFIC DATA
    const tokenCrosses = useMemo(() =>
        crosses.filter(c => c.symbol === selectedSymbol).sort((a, b) => new Date(b.date) - new Date(a.date)),
        [crosses, selectedSymbol]
    );

    const tokenRecommendations = useMemo(() =>
        // We can get history from 'historyData' but that is for chart. 
        // For recommendations list, we might only have 'signals' which is ONE per token (latest).
        // The user asked for "all the current recomendation for each token".
        // If they want HISTORY of recommendations for ONE token, we need that from historyData.
        historyData ? historyData.filter(d => d.signalType).sort((a, b) => new Date(b.date) - new Date(a.date)) : [],
        [historyData]
    );

    // MARKET AGGREGATE DATA
    const marketCrosses = useMemo(() =>
        [...crosses].sort((a, b) => new Date(b.date) - new Date(a.date)),
        [crosses]
    );

    const marketRecommendations = useMemo(() =>
        signals
            .sort((a, b) => new Date(b.Date) - new Date(a.Date)),
        [signals]
    );

    const chartData = useMemo(() => {
        if (!historyData) return [];
        if (chartRange === 'ALL') return historyData;
        const cutoff = new Date();
        if (chartRange === '1Y') cutoff.setFullYear(cutoff.getFullYear() - 1);
        if (chartRange === '3Y') cutoff.setFullYear(cutoff.getFullYear() - 3);
        if (chartRange === '5Y') cutoff.setFullYear(cutoff.getFullYear() - 5);
        if (chartRange === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
        return historyData.filter(d => new Date(d.date) >= cutoff);
    }, [historyData, chartRange]);

    if (loading) return (
        <div className="h-screen flex flex-col items-center justify-center bg-[#0B0D10] text-[#E4E8EC] gap-4">
            <div className="w-10 h-10 rounded-full border-3 border-[#1E2228] border-t-[#00E5FF] animate-spin"></div>
            <div className="text-sm font-semibold text-[#5F6670] animate-pulse">Initializing SignalStack...</div>
        </div>
    );


    return (
        <div className="flex flex-col h-screen overflow-hidden bg-[#0B0D10] text-[#E4E8EC]">
            {/* Header with Slider */}
            {/* Header with Slider */}
            <Header
                sidebarOpen={sidebarOpen}
                setSidebarOpen={setSidebarOpen}
                mobileView={mobileView}
                onBack={() => setMobileView('list')}
                onLogout={onLogout}
            />

            <div className="flex flex-1 overflow-hidden relative">

                {/* Sidebar Overlay (Mobile) */}
                {sidebarOpen && (
                    <div
                        className="fixed inset-0 bg-black/60 z-30 md:hidden backdrop-blur-sm transition-opacity"
                        onClick={() => setSidebarOpen(false)}
                    />
                )}

                {/* Sidebar (Desktop: Block | Mobile: Conditional) */}
                <div className={`
                    fixed inset-y-0 inset-x-0 z-40 bg-[#1c1c1e] border-r border-white/5 flex flex-col transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] h-full pt-[72px] md:pt-0
                    md:relative md:translate-x-0 md:w-80 md:inset-auto
                ${mobileView === 'list' ? 'translate-x-0' : '-translate-x-full md:translate-x-0 invisible md:visible'}
                ${sidebarOpen ? 'translate-x-0 shadow-2xl' : ''} 
                `}>

                    {/* Sidebar Toggle */}
                    <div className="px-5 pt-5 pb-1">
                        <div className="relative flex items-center bg-[#767680]/20 rounded-lg p-[2px] w-full h-[40px]">
                            {/* Animated Background (Thumb) */}
                            <div
                                className="absolute top-[2px] bottom-[2px] rounded-[6px] transition-all duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] bg-[#636366] shadow-[0_2px_4px_rgba(0,0,0,0.2)]"
                                style={{
                                    left: '2px',
                                    width: 'calc(50% - 2px)',
                                    transform: activeTab === 'stocks' ? 'translateX(0)' : 'translateX(100%)'
                                }}
                            />

                            {/* Stocks Button */}
                            <button
                                onClick={() => setActiveTab('stocks')}
                                className={`relative z-10 flex-1 h-full text-[13px] font-medium transition-colors duration-200 flex items-center justify-center rounded-[6px] ${activeTab === 'stocks' ? 'text-white' : 'text-[#86868b] hover:text-white'
                                    }`}
                            >
                                <span>Stocks</span>
                            </button>

                            {/* Crypto Button */}
                            <button
                                onClick={() => setActiveTab('crypto')}
                                className={`relative z-10 flex-1 h-full text-[13px] font-medium transition-colors duration-200 flex items-center justify-center rounded-[6px] ${activeTab === 'crypto' ? 'text-white' : 'text-[#86868b] hover:text-white'
                                    }`}
                            >
                                <span>Crypto</span>
                            </button>
                        </div>
                    </div>

                    {/* Search */}
                    <div className="p-5 border-b border-white/5 pt-2">
                        <div className="relative bg-[#2c2c2e] rounded-[10px]">
                            <Search className="absolute left-3 top-3 w-4 h-4 text-[#86868b]" />
                            <input
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                placeholder="Search assets"
                                aria-label="Search assets"
                                className="w-full bg-transparent border-none py-2.5 pl-10 pr-4 text-[15px] text-white placeholder-[#86868b] focus:outline-none focus:ring-0 rounded-[10px]"
                            />
                        </div>
                        <div className="mt-3 text-[11px] font-medium text-[#86868b] uppercase tracking-wide px-1">{assetList.length} assets</div>
                    </div>

                    {/* Asset List */}
                    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
                        {assetList.map((item, index) => (
                            <div key={item.symbol}
                                id={`asset-${item.symbol}`}
                                onClick={() => {
                                    setSelectedSymbol(item.symbol);
                                    setMobileView('detail'); // Switch to detail view on mobile
                                }}
                                className={`p-4 rounded-2xl cursor-pointer transition-all duration-300 fade-in ${selectedSymbol === item.symbol
                                    ? 'bg-gradient-to-r from-[#8B5CF6] to-[#06B6D4] text-white shadow-lg scale-[1.02]'
                                    : 'hover:bg-[#2c2c2e] text-white hover:scale-[1.01]'
                                    }`}
                                style={{ animationDelay: `${index * 0.02}s` }}
                            >
                                <div className="flex justify-between items-center mb-1">
                                    <span className="font-semibold text-[17px]">{item.symbol}</span>
                                    <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wide ${selectedSymbol === item.symbol ? 'bg-white/20 text-white' :
                                        item.side === 'buy' ? 'bg-[#30d158]/10 text-[#30d158]' :
                                            item.side === 'sell' ? 'bg-[#ff453a]/10 text-[#ff453a]' :
                                                'bg-[#86868b]/10 text-[#86868b]'
                                        }`}>
                                        {item.side}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center text-[13px]">
                                    <span className={selectedSymbol === item.symbol ? 'text-white/90' : 'text-[#86868b]'}>${formatPrice(item.Close)}</span>
                                    <span className={`font-semibold ${selectedSymbol === item.symbol ? 'text-white' : 'text-[#8B5CF6]'}`}>{item.score}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Main Content (Desktop: Block | Mobile: Conditional) */}
                <div className={`
                    flex-1 flex flex-col min-w-0 overflow-hidden relative bg-[#0B0D10]
                    absolute md:static inset-0 z-50 md:z-auto
                    transition-transform duration-300 ease-in-out
                    ${mobileView === 'detail' ? 'translate-x-0' : 'translate-x-full md:translate-x-0'}
                `}>
                    <div className="flex-1 overflow-y-auto pt-4 md:pt-0 p-4 md:p-8 space-y-6 md:space-y-8">

                        {/* Chart - Meta-Inspired Premium Design */}
                        <div className="relative rounded-3xl overflow-hidden border border-white/10 shadow-2xl transition-all duration-500 hover:border-white/15 group">
                            {/* Multi-layer gradient overlays for depth */}
                            <div className="absolute inset-0 bg-gradient-to-br from-[#0f1318] via-[#0d1015] to-[#0a0c0f] opacity-95"></div>
                            <div className="absolute inset-0 bg-gradient-to-tr from-purple-500/5 via-transparent to-teal-500/5"></div>
                            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(139,92,246,0.08),transparent_50%)]"></div>

                            {/* Noise texture for premium feel */}
                            <div className="chart-noise"></div>

                            {/* Content */}
                            <div className="relative z-10 p-6 md:p-10">
                                {/* Enhanced Header */}
                                <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-6 mb-8">
                                    <div className="space-y-3">
                                        <div className="flex items-baseline gap-3">
                                            <h2 className="text-3xl md:text-4xl font-bold text-white tracking-tight font-display">
                                                {selectedSymbol}
                                            </h2>
                                            {currentSignal && (
                                                <span className={`text-sm font-semibold px-3 py-1 rounded-full ${currentSignal.side === 'buy'
                                                    ? 'bg-[#10B981]/15 text-[#10B981] border border-[#10B981]/30'
                                                    : currentSignal.side === 'sell'
                                                        ? 'bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/30'
                                                        : 'bg-[#8B5CF6]/15 text-[#8B5CF6] border border-[#8B5CF6]/30'
                                                    }`}>
                                                    {currentSignal.side.toUpperCase()}
                                                </span>
                                            )}
                                        </div>
                                        {currentSignal && (
                                            <div className="flex items-baseline gap-3">
                                                <span className="text-2xl md:text-3xl font-bold text-white">
                                                    ${formatPrice(currentSignal.Close)}
                                                </span>
                                                <span className={`text-sm font-semibold ${currentSignal.change >= 0 ? 'text-[#10B981]' : 'text-[#F59E0B]'
                                                    }`}>
                                                    {currentSignal.change >= 0 ? '+' : ''}{currentSignal.change?.toFixed(2)}%
                                                </span>
                                            </div>
                                        )}
                                        <p className="text-sm text-[#86868b] font-medium">
                                            {chartData.length.toLocaleString()} data points • {chartRange === 'ALL' ? 'All time' : chartRange}
                                        </p>
                                    </div>

                                    {/* Modern Range Selector */}
                                    <div className="flex gap-2 bg-white/5 backdrop-blur-xl p-1.5 rounded-2xl border border-white/10 shadow-lg">
                                        {['3M', '1Y', '3Y', '5Y', 'ALL'].map(r => (
                                            <button
                                                key={r}
                                                onClick={() => setChartRange(r)}
                                                aria-label={`Set chart range to ${r}`}
                                                className={`px-4 py-2.5 text-xs font-bold rounded-xl transition-all duration-300 min-w-[50px] ${chartRange === r
                                                    ? 'bg-gradient-to-r from-[#8B5CF6] to-[#06B6D4] text-white shadow-lg shadow-purple-500/30 scale-105'
                                                    : 'text-[#86868b] hover:text-white hover:bg-white/10'
                                                    }`}
                                            >
                                                {r}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Chart Area */}
                                <div className="h-[320px] md:h-[480px] w-full relative">
                                    {!historyData ? (
                                        <div className="h-full flex flex-col items-center justify-center text-[#86868b] gap-2">
                                            <div className="w-5 h-5 rounded-full border-2 border-[#2c2c2e] border-t-[#0A84FF] animate-spin" />
                                            <span className="text-[13px]">Loading chart data...</span>
                                        </div>
                                    ) : (
                                        <div style={{ width: '100%', height: '100%' }}>
                                            <ResponsiveContainer width="99%" height="100%" key={selectedSymbol}>
                                                <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                                    {/* Enhanced gradients for premium look */}
                                                    <defs>
                                                        <linearGradient id="chartLineGradient" x1="0" y1="0" x2="1" y2="0">
                                                            <stop offset="0%" stopColor="#06B6D4" stopOpacity={1} />
                                                            <stop offset="30%" stopColor="#14B8A6" stopOpacity={1} />
                                                            <stop offset="60%" stopColor="#8B5CF6" stopOpacity={1} />
                                                            <stop offset="100%" stopColor="#A78BFA" stopOpacity={0.9} />
                                                        </linearGradient>
                                                        <linearGradient id="chartAreaGradient" x1="0" y1="0" x2="0" y2="1">
                                                            <stop offset="0%" stopColor="#8B5CF6" stopOpacity={0.25} />
                                                            <stop offset="40%" stopColor="#06B6D4" stopOpacity={0.12} />
                                                            <stop offset="100%" stopColor="#06B6D4" stopOpacity={0} />
                                                        </linearGradient>
                                                        {/* Glow filter for line */}
                                                        <filter id="lineGlow" x="-50%" y="-50%" width="200%" height="200%">
                                                            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
                                                            <feMerge>
                                                                <feMergeNode in="coloredBlur" />
                                                                <feMergeNode in="SourceGraphic" />
                                                            </feMerge>
                                                        </filter>
                                                    </defs>

                                                    <XAxis
                                                        dataKey="date"
                                                        stroke="#2c2c2e"
                                                        tick={{ fontSize: 11, fill: '#5F6670', fontWeight: 600 }}
                                                        tickFormatter={v => v.substring(5, 10)}
                                                        axisLine={false}
                                                        tickLine={false}
                                                        dy={10}
                                                    />
                                                    <YAxis
                                                        dataKey="price"
                                                        stroke="#2c2c2e"
                                                        tick={{ fontSize: 11, fill: '#5F6670', fontWeight: 600 }}
                                                        orientation="right"
                                                        width={60}
                                                        domain={['auto', 'auto']}
                                                        axisLine={false}
                                                        tickLine={false}
                                                    />
                                                    <Tooltip
                                                        wrapperClassName="chart-tooltip-glass"
                                                        contentStyle={{
                                                            backgroundColor: 'rgba(28, 28, 30, 0.85)',
                                                            borderColor: 'rgba(255,255,255,0.1)',
                                                            borderRadius: '12px',
                                                            padding: '12px',
                                                            backdropFilter: 'blur(20px)'
                                                        }}
                                                        itemStyle={{ color: '#fff', fontSize: '13px', fontWeight: 600 }}
                                                        labelStyle={{ color: '#86868b', fontSize: '11px', marginBottom: '6px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}
                                                    />

                                                    <Area
                                                        type="monotone"
                                                        dataKey="price"
                                                        stroke="none"
                                                        fill="url(#chartAreaGradient)"
                                                        isAnimationActive={true}
                                                        animationDuration={1000}
                                                    />

                                                    {/* Line with enhanced gradient and glow */}
                                                    <Line
                                                        type="monotone"
                                                        dataKey="price"
                                                        stroke="url(#chartLineGradient)"
                                                        strokeWidth={3}
                                                        dot={<CustomDot />}
                                                        activeDot={{ r: 8, fill: '#8B5CF6', stroke: '#fff', strokeWidth: 2, strokeOpacity: 0.3 }}
                                                        isAnimationActive={true}
                                                        animationDuration={1200}
                                                        animationEasing="ease-in-out"
                                                        filter="url(#lineGlow)"
                                                    />
                                                </LineChart>
                                            </ResponsiveContainer>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Content Toggle: Token vs Market */}
                        <div className="bg-[#1c1c1e] rounded-2xl p-6 md:p-8 min-h-[400px] border border-white/5 shadow-xl transition-all duration-300 hover:border-white/10 fade-in">
                            <div className="flex items-center gap-6 mb-6 border-b border-[#2c2c2e]">
                                <button
                                    onClick={() => setContentTab('token')}
                                    className={`text-sm md:text-base font-bold pb-4 border-b-2 transition-all duration-300 ${contentTab === 'token'
                                        ? 'text-[#8B5CF6] border-[#8B5CF6] scale-105'
                                        : 'text-[#5F6670] border-transparent hover:text-[#E4E8EC] hover:border-[#5F6670]'
                                        }`}
                                >
                                    {selectedSymbol} Events
                                </button>
                                <button
                                    onClick={() => setContentTab('market')}
                                    className={`text-sm md:text-base font-bold pb-4 border-b-2 transition-all duration-300 ${contentTab === 'market'
                                        ? 'text-[#8B5CF6] border-[#8B5CF6] scale-105'
                                        : 'text-[#5F6670] border-transparent hover:text-[#E4E8EC] hover:border-[#5F6670]'
                                        }`}
                                >
                                    Market Pulse
                                </button>
                            </div>

                            <div className="space-y-4">
                                {contentTab === 'token' ? (
                                    <>
                                        {/* Token Specific View */}
                                        <div className="grid md:grid-cols-2 gap-6">
                                            {/* Token Crosses */}
                                            <div>
                                                <h3 className="text-xs font-bold text-[#9CA3AF] uppercase mb-3">Latest Crosses</h3>
                                                {tokenCrosses.length > 0 ? (
                                                    <div className="space-y-2">
                                                        {tokenCrosses.slice(0, 10).map((c, i) => (
                                                            <div key={i} className="flex justify-between items-center py-2 border-b border-[#1E2228]/50">
                                                                <span className={`text-xs font-bold px-2 py-1 rounded-full ${c.type.includes('Golden') ? 'bg-[#10B981]/10 text-[#10B981]' : 'bg-[#F59E0B]/10 text-[#F59E0B]'}`}>
                                                                    {c.type.replace('Confirmed ', '')}
                                                                </span>
                                                                <span className="text-xs text-[#5F6670]">{c.date?.substring(0, 10)}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : <div className="text-sm text-[#5F6670] italic">No recent crosses.</div>}
                                            </div>

                                            {/* Token Signals History */}
                                            <div>
                                                <h3 className="text-xs font-bold text-[#9CA3AF] uppercase mb-3">Signal History</h3>
                                                {tokenRecommendations.length > 0 ? (
                                                    <div className="space-y-2">
                                                        {tokenRecommendations.slice(0, 10).map((s, i) => (
                                                            <div key={i} className="flex justify-between items-center py-2 border-b border-[#1E2228]/50">
                                                                <span className={`text-xs font-bold px-2 py-1 rounded-full uppercase ${s.signalType === 'buy' ? 'bg-[#10B981]/10 text-[#10B981]' :
                                                                    s.signalType === 'sell' ? 'bg-[#F59E0B]/10 text-[#F59E0B]' :
                                                                        'bg-[#5F6670]/10 text-[#5F6670]'
                                                                    }`}>
                                                                    {s.signalType}
                                                                </span>
                                                                <span className="text-xs text-[#5F6670]">{s.date?.substring(0, 10)}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : <div className="text-sm text-[#5F6670] italic">No signal history available.</div>}
                                            </div>
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        {/* Market Pulse View */}
                                        <div className="grid md:grid-cols-2 gap-6">
                                            <div>
                                                <h3 className="text-xs font-bold text-[#9CA3AF] uppercase mb-3">Latest Market Crosses</h3>
                                                <div className="space-y-2">
                                                    {marketCrosses.slice(0, 15).map((c, i) => (
                                                        <div key={i} onClick={() => { setSelectedSymbol(c.symbol); setContentTab('token'); }} className="flex justify-between items-center py-2 border-b border-[#1E2228]/50 cursor-pointer hover:bg-[#1E2228] px-2 rounded -mx-2">
                                                            <span className="font-bold text-sm w-16">{c.symbol}</span>
                                                            <span className={`text-xs font-bold px-2 py-1 rounded-full ${c.type.includes('Golden') ? 'bg-[#10B981]/10 text-[#10B981]' : 'bg-[#F59E0B]/10 text-[#F59E0B]'}`}>
                                                                {c.type.replace('Confirmed ', '')}
                                                            </span>
                                                            <span className="text-xs text-[#5F6670]">{c.date?.substring(0, 10)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>

                                            <div>
                                                <h3 className="text-xs font-bold text-[#9CA3AF] uppercase mb-3">Top Recommendations</h3>
                                                <div className="space-y-2">
                                                    {marketRecommendations.slice(0, 15).map((s, i) => (
                                                        <div key={i} onClick={() => { setSelectedSymbol(s.symbol); setContentTab('token'); }} className="flex justify-between items-center py-2 border-b border-[#1E2228]/50 cursor-pointer hover:bg-[#1E2228] px-2 rounded -mx-2">
                                                            <span className="font-bold text-sm w-16">{s.symbol}</span>
                                                            <span className={`text-xs font-bold px-2 py-1 rounded-full uppercase ${s.side === 'buy' ? 'bg-[#10B981]/10 text-[#10B981]' :
                                                                s.side === 'sell' ? 'bg-[#F59E0B]/10 text-[#F59E0B]' :
                                                                    'bg-[#5F6670]/10 text-[#5F6670]'
                                                                }`}>
                                                                {s.side}
                                                            </span>
                                                            <span className="text-xs font-bold text-[#8B5CF6]">{s.score}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ProDashboard;
