import React, { useState, useEffect, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Search, TrendingUp, Menu, X, Zap } from 'lucide-react';
import Header from './Header';

const formatPrice = (p) => p < 1 ? p?.toFixed(5) : p?.toLocaleString(undefined, { maximumFractionDigits: 2 });

const CustomDot = (props) => {
    const { cx, cy, payload } = props;
    if (!payload.signalType) return null;
    const isBuy = payload.signalType === 'buy';
    const color = isBuy ? '#32D74B' : '#FF453A';
    return <circle cx={cx} cy={cy} r={5} fill={color} stroke="#fff" strokeWidth={2} />;
};

const ProDashboard = () => {
    const [signals, setSignals] = useState([]);
    const [crosses, setCrosses] = useState([]);
    const [historyData, setHistoryData] = useState(null);
    const [activeTab, setActiveTab] = useState('crypto');
    const [contentTab, setContentTab] = useState('token'); // 'token' or 'market'
    const [selectedSymbol, setSelectedSymbol] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [loading, setLoading] = useState(true);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [chartRange, setChartRange] = useState('ALL');

    useEffect(() => {
        Promise.all([
            fetch('/data/latest_signals.json').then(r => r.json()),
            fetch('/data/crosses.json').then(r => r.json())
        ]).then(([sig, cr]) => {
            setSignals(sig.signals);
            setCrosses(cr.crosses);
            const first = sig.signals.find(s => s.category === 'crypto');
            if (first) setSelectedSymbol(first.symbol);
            setLoading(false);
        }).catch(err => console.error('Load error:', err));
    }, []);

    useEffect(() => {
        if (!selectedSymbol) return;
        setHistoryData(null);
        fetch(`/data/history/${selectedSymbol}.json`)
            .then(r => r.json())
            .then(json => {
                const processed = json.data.map(d => ({
                    date: d.Date,
                    price: parseFloat(d.Close),
                    signalType: (d.signal && d.signal.includes('Buy')) ? 'buy' : (d.signal && d.signal.includes('Sell')) ? 'sell' : null
                }));
                setHistoryData(processed);
            })
            .catch(err => console.error('History error:', err));
    }, [selectedSymbol]);

    const assetList = useMemo(() =>
        signals.filter(s => s.category === activeTab)
            .filter(s => s.symbol.toLowerCase().includes(searchTerm.toLowerCase()))
            .sort((a, b) => b.score - a.score),
        [signals, activeTab, searchTerm]
    );

    const currentSignal = useMemo(() => signals.find(s => s.symbol === selectedSymbol), [signals, selectedSymbol]);

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
        if (chartRange === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
        return historyData.filter(d => new Date(d.date) >= cutoff);
    }, [historyData, chartRange]);

    if (loading) return (
        <div className="h-screen flex flex-col items-center justify-center bg-[#0B0D10] text-[#E4E8EC] gap-4">
            <div className="w-8 h-8 rounded-full border-2 border-[#1E2228] border-t-[#00E5FF] animate-spin"></div>
            <div className="text-sm font-medium text-[#5F6670] animate-pulse">Initializing Signal Pro...</div>
        </div>
    );

    return (
        <div className="flex flex-col h-screen overflow-hidden bg-[#0B0D10] text-[#E4E8EC]">
            {/* Header with Slider */}
            <Header
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                signals={signals}
                sidebarOpen={sidebarOpen}
                setSidebarOpen={setSidebarOpen}
            />

            <div className="flex flex-1 overflow-hidden relative">

                {/* Sidebar Overlay (Mobile) */}
                {sidebarOpen && (
                    <div
                        className="fixed inset-0 bg-black/60 z-30 lg:hidden backdrop-blur-sm transition-opacity"
                        onClick={() => setSidebarOpen(false)}
                    />
                )}

                {/* Sidebar */}
                <div className={`fixed inset-y-0 left-0 z-40 w-72 lg:w-80 bg-[#13161B] border-r border-[#1E2228] flex flex-col transition-transform duration-300 ease-in-out lg:relative lg:translate-x-0 h-full pt-[72px] lg:pt-0 ${sidebarOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'
                    }`}>

                    {/* Search */}
                    <div className="p-5 border-b border-[#1E2228]">
                        <div className="relative bg-[#0B0D10] rounded-lg">
                            <Search className="absolute left-3 top-3 w-4 h-4 text-[#5F6670]" />
                            <input
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                placeholder="Search assets..."
                                aria-label="Search assets"
                                className="w-full bg-transparent border-none py-3 pl-10 pr-4 text-sm text-[#E4E8EC] placeholder-[#5F6670] focus:outline-none focus:ring-1 focus:ring-[#00E5FF]/30 rounded-lg transition-all"
                            />
                        </div>
                        <div className="mt-2 text-xs text-[#5F6670]">{assetList.length} assets</div>
                    </div>

                    {/* Asset List */}
                    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
                        {assetList.map(item => (
                            <div key={item.symbol} onClick={() => setSelectedSymbol(item.symbol)}
                                className={`p-4 rounded-xl cursor-pointer border ${selectedSymbol === item.symbol ? 'bg-[#1E2228] border-[#00E5FF]' : 'border-transparent hover:bg-[#1E2228]'}`}>
                                <div className="flex justify-between items-center mb-2">
                                    <span className={`font-bold ${selectedSymbol === item.symbol ? 'text-[#00E5FF]' : 'text-[#E4E8EC]'}`}>{item.symbol}</span>
                                    <span className={`text-[9px] font-bold px-2.5 py-1 rounded-full uppercase ${item.side === 'buy' ? 'bg-[#32D74B]/10 text-[#32D74B]' :
                                        item.side === 'sell' ? 'bg-[#FF453A]/10 text-[#FF453A]' :
                                            'bg-[#5F6670]/10 text-[#5F6670]' // styling for Hold
                                        }`}>
                                        {item.side}
                                    </span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-[#9CA3AF]">${formatPrice(item.Close)}</span>
                                    <span className="font-bold text-[#00E5FF]">{item.score}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Main Content */}
                <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                    <div className="flex-1 overflow-y-auto pt-4 lg:pt-0 p-4 lg:p-8 space-y-6 lg:space-y-8">

                        {/* Chart */}
                        <div className="bg-[#13161B] rounded-2xl p-6">
                            <div className="flex justify-between items-center mb-4">
                                <div>
                                    <div className="text-lg font-bold">{selectedSymbol}</div>
                                    <div className="text-sm text-[#9CA3AF]">{chartData.length} data points</div>
                                </div>
                                <div className="flex gap-2">
                                    {['3M', '1Y', 'ALL'].map(r => (
                                        <button
                                            key={r}
                                            onClick={() => setChartRange(r)}
                                            aria-label={`Set chart range to ${r}`}
                                            className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-colors ${chartRange === r ? 'bg-[#00E5FF] text-black' : 'text-[#9CA3AF] hover:text-[#E4E8EC] hover:bg-[#1E2228]'}`}>
                                            {r}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="h-[300px] lg:h-[450px] w-full">
                                {!historyData ? (
                                    <div className="h-full flex flex-col items-center justify-center text-[#5F6670] gap-2">
                                        <div className="w-5 h-5 rounded-full border-2 border-[#1E2228] border-t-[#00E5FF] animate-spin" />
                                        <span className="text-xs">Loading chart data...</span>
                                    </div>
                                ) : (
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                            <XAxis
                                                dataKey="date"
                                                stroke="#5F6670"
                                                tick={{ fontSize: 10, fill: '#9CA3AF' }}
                                                tickFormatter={v => v.substring(5, 10)}
                                                axisLine={false}
                                                tickLine={false}
                                                dy={10}
                                            />
                                            <YAxis
                                                dataKey="price"
                                                stroke="#5F6670"
                                                tick={{ fontSize: 10, fill: '#9CA3AF' }}
                                                orientation="right"
                                                width={50}
                                                domain={['auto', 'auto']}
                                                axisLine={false}
                                                tickLine={false}
                                            />
                                            <Tooltip
                                                contentStyle={{ backgroundColor: 'rgba(19, 22, 27, 0.9)', borderColor: '#1E2228', borderRadius: '12px', backdropFilter: 'blur(8px)', boxShadow: '0 4px 12px rgba(0,0,0,0.5)' }}
                                                itemStyle={{ color: '#E4E8EC', fontSize: '12px' }}
                                                labelStyle={{ color: '#9CA3AF', fontSize: '10px', marginBottom: '4px' }}
                                            />
                                            <Line
                                                type="monotone"
                                                dataKey="price"
                                                stroke="#00E5FF"
                                                strokeWidth={2}
                                                dot={<CustomDot />}
                                                activeDot={{ r: 6, strokeWidth: 0, fill: '#FFFFFF' }}
                                                isAnimationActive={false}
                                            />
                                        </LineChart>
                                    </ResponsiveContainer>
                                )}
                            </div>
                        </div>

                        {/* Content Toggle: Token vs Market */}
                        <div className="bg-[#13161B] rounded-2xl p-6 min-h-[400px]">
                            <div className="flex items-center gap-6 mb-6 border-b border-[#1E2228]">
                                <button
                                    onClick={() => setContentTab('token')}
                                    className={`text-sm lg:text-base font-bold pb-4 border-b-2 transition-colors ${contentTab === 'token'
                                        ? 'text-[#00E5FF] border-[#00E5FF]'
                                        : 'text-[#5F6670] border-transparent hover:text-[#E4E8EC]'
                                        }`}
                                >
                                    {selectedSymbol} Events
                                </button>
                                <button
                                    onClick={() => setContentTab('market')}
                                    className={`text-sm lg:text-base font-bold pb-4 border-b-2 transition-colors ${contentTab === 'market'
                                        ? 'text-[#00E5FF] border-[#00E5FF]'
                                        : 'text-[#5F6670] border-transparent hover:text-[#E4E8EC]'
                                        }`}
                                >
                                    Market Pulse
                                </button>
                            </div>

                            <div className="space-y-4">
                                {contentTab === 'token' ? (
                                    <>
                                        {/* Token Specific View */}
                                        <div className="grid lg:grid-cols-2 gap-6">
                                            {/* Token Crosses */}
                                            <div>
                                                <h3 className="text-xs font-bold text-[#9CA3AF] uppercase mb-3">Latest Crosses</h3>
                                                {tokenCrosses.length > 0 ? (
                                                    <div className="space-y-2">
                                                        {tokenCrosses.slice(0, 10).map((c, i) => (
                                                            <div key={i} className="flex justify-between items-center py-2 border-b border-[#1E2228]/50">
                                                                <span className={`text-xs font-bold px-2 py-1 rounded-full ${c.type.includes('Golden') ? 'bg-[#32D74B]/10 text-[#32D74B]' : 'bg-[#FF453A]/10 text-[#FF453A]'}`}>
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
                                                                <span className={`text-xs font-bold px-2 py-1 rounded-full uppercase ${s.signalType === 'buy' ? 'bg-[#32D74B]/10 text-[#32D74B]' :
                                                                    s.signalType === 'sell' ? 'bg-[#FF453A]/10 text-[#FF453A]' :
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
                                        <div className="grid lg:grid-cols-2 gap-6">
                                            <div>
                                                <h3 className="text-xs font-bold text-[#9CA3AF] uppercase mb-3">Latest Market Crosses</h3>
                                                <div className="space-y-2">
                                                    {marketCrosses.slice(0, 15).map((c, i) => (
                                                        <div key={i} onClick={() => { setSelectedSymbol(c.symbol); setContentTab('token'); }} className="flex justify-between items-center py-2 border-b border-[#1E2228]/50 cursor-pointer hover:bg-[#1E2228] px-2 rounded -mx-2">
                                                            <span className="font-bold text-sm w-16">{c.symbol}</span>
                                                            <span className={`text-xs font-bold px-2 py-1 rounded-full ${c.type.includes('Golden') ? 'bg-[#32D74B]/10 text-[#32D74B]' : 'bg-[#FF453A]/10 text-[#FF453A]'}`}>
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
                                                            <span className={`text-xs font-bold px-2 py-1 rounded-full uppercase ${s.side === 'buy' ? 'bg-[#32D74B]/10 text-[#32D74B]' :
                                                                s.side === 'sell' ? 'bg-[#FF453A]/10 text-[#FF453A]' :
                                                                    'bg-[#5F6670]/10 text-[#5F6670]'
                                                                }`}>
                                                                {s.side}
                                                            </span>
                                                            <span className="text-xs font-bold text-[#00E5FF]">{s.score}</span>
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
