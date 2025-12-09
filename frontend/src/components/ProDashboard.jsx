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
                    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
                        {assetList.map(item => (
                            <div key={item.symbol}
                                id={`asset-${item.symbol}`}
                                onClick={() => {
                                    setSelectedSymbol(item.symbol);
                                    setMobileView('detail'); // Switch to detail view on mobile
                                }}
                                className={`p-4 rounded-[14px] cursor-pointer transition-colors ${selectedSymbol === item.symbol ? 'bg-[#0A84FF] text-white' : 'hover:bg-[#2c2c2e] text-white'}`}>
                                <div className="flex justify-between items-center mb-1">
                                    <span className="font-semibold text-[17px]">{item.symbol}</span>
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide ${selectedSymbol === item.symbol ? 'bg-white/20 text-white' :
                                        item.side === 'buy' ? 'bg-[#30d158]/10 text-[#30d158]' :
                                            item.side === 'sell' ? 'bg-[#ff453a]/10 text-[#ff453a]' :
                                                'bg-[#86868b]/10 text-[#86868b]' // styling for Hold
                                        }`}>
                                        {item.side}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center text-[13px]">
                                    <span className={selectedSymbol === item.symbol ? 'text-white/80' : 'text-[#86868b]'}>${formatPrice(item.Close)}</span>
                                    <span className={`font-medium ${selectedSymbol === item.symbol ? 'text-white' : 'text-[#0A84FF]'}`}>{item.score}</span>
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

                        {/* Chart */}
                        <div className="bg-[#1c1c1e] rounded-[18px] p-6 md:p-8">
                            <div className="flex justify-between items-center mb-6">
                                <div>
                                    <div className="text-[22px] font-bold text-white tracking-tight">{selectedSymbol}</div>
                                    <div className="text-[13px] font-medium text-[#86868b]">{chartData.length} data points</div>
                                </div>
                                <div className="flex bg-[#2c2c2e] p-0.5 rounded-[9px]">
                                    {['3M', '1Y', 'ALL'].map(r => (
                                        <button
                                            key={r}
                                            onClick={() => setChartRange(r)}
                                            aria-label={`Set chart range to ${r}`}
                                            className={`px-3 py-1 text-[11px] font-semibold rounded-[7px] transition-all min-w-[40px] ${chartRange === r
                                                ? 'bg-[#636366] text-white shadow-sm'
                                                : 'text-[#86868b] hover:text-white'
                                                }`}>
                                            {r}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="h-[300px] md:h-[450px] w-full relative">
                                {!historyData ? (
                                    <div className="h-full flex flex-col items-center justify-center text-[#86868b] gap-2">
                                        <div className="w-5 h-5 rounded-full border-2 border-[#2c2c2e] border-t-[#0A84FF] animate-spin" />
                                        <span className="text-[13px]">Loading chart data...</span>
                                    </div>
                                ) : (
                                    <div style={{ width: '100%', height: '100%' }}>
                                        <ResponsiveContainer width="99%" height="100%" key={selectedSymbol}>
                                            <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                                <XAxis
                                                    dataKey="date"
                                                    stroke="#48484a"
                                                    tick={{ fontSize: 11, fill: '#86868b', fontWeight: 500 }}
                                                    tickFormatter={v => v.substring(5, 10)}
                                                    axisLine={false}
                                                    tickLine={false}
                                                    dy={10}
                                                />
                                                <YAxis
                                                    dataKey="price"
                                                    stroke="#48484a"
                                                    tick={{ fontSize: 11, fill: '#86868b', fontWeight: 500 }}
                                                    orientation="right"
                                                    width={50}
                                                    domain={['auto', 'auto']}
                                                    axisLine={false}
                                                    tickLine={false}
                                                />
                                                <Tooltip
                                                    contentStyle={{ backgroundColor: 'rgba(28, 28, 30, 0.8)', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '12px', backdropFilter: 'blur(16px)', boxShadow: '0 4px 20px rgba(0,0,0,0.4)', padding: '12px' }}
                                                    itemStyle={{ color: '#fff', fontSize: '13px', fontWeight: 500 }}
                                                    labelStyle={{ color: '#86868b', fontSize: '11px', marginBottom: '4px', fontWeight: 600 }}
                                                />
                                                <Line
                                                    type="monotone"
                                                    dataKey="price"
                                                    stroke="#0A84FF"
                                                    strokeWidth={2}
                                                    dot={<CustomDot />}
                                                    activeDot={{ r: 6, strokeWidth: 0, fill: '#FFFFFF' }}
                                                    isAnimationActive={false}
                                                />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Content Toggle: Token vs Market */}
                        <div className="bg-[#1c1c1e] rounded-[18px] p-6 md:p-8 min-h-[400px]">
                            <div className="flex items-center gap-6 mb-6 border-b border-[#1E2228]">
                                <button
                                    onClick={() => setContentTab('token')}
                                    className={`text-sm md:text-base font-bold pb-4 border-b-2 transition-colors ${contentTab === 'token'
                                        ? 'text-[#00E5FF] border-[#00E5FF]'
                                        : 'text-[#5F6670] border-transparent hover:text-[#E4E8EC]'
                                        }`}
                                >
                                    {selectedSymbol} Events
                                </button>
                                <button
                                    onClick={() => setContentTab('market')}
                                    className={`text-sm md:text-base font-bold pb-4 border-b-2 transition-colors ${contentTab === 'market'
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
                                        <div className="grid md:grid-cols-2 gap-6">
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
                                        <div className="grid md:grid-cols-2 gap-6">
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
        </div >
    );
};

export default ProDashboard;
