import React, { useState, useEffect, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Search, TrendingUp, Menu, X, Zap } from 'lucide-react';

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

    const currentCrosses = useMemo(() =>
        crosses.filter(c => c.symbol === selectedSymbol).slice(0, 15),
        [crosses, selectedSymbol]
    );

    const chartData = useMemo(() => {
        if (!historyData) return [];
        if (chartRange === 'ALL') return historyData;
        const cutoff = new Date();
        if (chartRange === '1Y') cutoff.setFullYear(cutoff.getFullYear() - 1);
        if (chartRange === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
        return historyData.filter(d => new Date(d.date) >= cutoff);
    }, [historyData, chartRange]);

    if (loading) return <div className="h-screen flex items-center justify-center bg-[#0B0D10] text-white">Loading...</div>;

    return (
        <div className="flex h-screen overflow-hidden bg-[#0B0D10] text-[#E4E8EC]">

            {/* Mobile Header */}
            <div className="lg:hidden fixed top-0 left-0 right-0 h-14 bg-[#13161B] border-b border-[#1E2228] flex items-center px-4 z-50">
                <button onClick={() => setSidebarOpen(!sidebarOpen)}>
                    {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
                </button>
                <div className="flex-1 text-center">
                    <div className="text-xs text-[#9CA3AF]">{selectedSymbol}</div>
                    <div className="text-sm font-bold text-[#00E5FF]">${formatPrice(currentSignal?.Close)}</div>
                </div>
            </div>

            {/* Sidebar */}
            <div className={`fixed lg:relative z-40 h-full w-80 bg-[#13161B] border-r border-[#1E2228] flex flex-col transition-transform ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>

                {/* Tabs */}
                <div className="flex border-b border-[#1E2228] mt-14 lg:mt-0">
                    {['crypto', 'stocks'].map(tab => (
                        <button key={tab} onClick={() => setActiveTab(tab)}
                            className={`flex-1 py-6 text-xs font-bold uppercase flex items-center justify-center gap-2 ${activeTab === tab ? 'text-[#00E5FF] border-b-2 border-[#00E5FF]' : 'text-[#5F6670]'}`}>
                            {tab === 'crypto' ? <Zap size={14} /> : <TrendingUp size={14} />}
                            {tab}
                        </button>
                    ))}
                </div>

                {/* Search */}
                <div className="p-5 border-b border-[#1E2228]">
                    <div className="relative bg-[#0B0D10] rounded-lg">
                        <Search className="absolute left-3 top-3 w-4 h-4 text-[#5F6670]" />
                        <input value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
                            placeholder="Search..." className="w-full bg-transparent border-none py-3 pl-10 pr-4 text-sm" />
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
                                {item.side !== 'hold' && (
                                    <span className={`text-[9px] font-bold px-2.5 py-1 rounded-full uppercase ${item.side === 'buy' ? 'bg-[#32D74B]/10 text-[#32D74B]' : 'bg-[#FF453A]/10 text-[#FF453A]'}`}>
                                        {item.side}
                                    </span>
                                )}
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
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <div className="flex-1 overflow-y-auto pt-14 lg:pt-0 p-6 space-y-6">

                    {/* Chart */}
                    <div className="bg-[#13161B] rounded-2xl p-6">
                        <div className="flex justify-between items-center mb-4">
                            <div>
                                <div className="text-lg font-bold">{selectedSymbol}</div>
                                <div className="text-sm text-[#9CA3AF]">{chartData.length} data points</div>
                            </div>
                            <div className="flex gap-2">
                                {['3M', '1Y', 'ALL'].map(r => (
                                    <button key={r} onClick={() => setChartRange(r)}
                                        className={`px-4 py-1.5 text-xs font-bold rounded-lg ${chartRange === r ? 'bg-[#00E5FF] text-black' : 'text-[#9CA3AF]'}`}>
                                        {r}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="h-[400px]">
                            {!historyData ? (
                                <div className="h-full flex items-center justify-center text-[#5F6670]">Loading chart...</div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={chartData} margin={{ top: 20, right: 20, left: 20, bottom: 20 }}>
                                        <XAxis dataKey="date" stroke="#5F6670" tick={{ fontSize: 10 }} tickFormatter={v => v.substring(5, 10)} />
                                        <YAxis dataKey="price" stroke="#5F6670" tick={{ fontSize: 10 }} orientation="right" width={60} domain={['auto', 'auto']} />
                                        <Tooltip contentStyle={{ backgroundColor: '#13161B', borderColor: '#1E2228', borderRadius: '12px' }} />
                                        <Line type="monotone" dataKey="price" stroke="#00E5FF" strokeWidth={3} dot={<CustomDot />} isAnimationActive={false} />
                                    </LineChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </div>

                    {/* Crosses */}
                    <div className="bg-[#13161B] rounded-2xl p-6">
                        <div className="font-bold mb-4">Recent Crosses ({currentCrosses.length})</div>
                        <div className="space-y-3">
                            {currentCrosses.map((c, i) => (
                                <div key={i} className="flex justify-between items-center py-2 border-b border-[#1E2228]">
                                    <span className={`text-xs font-bold px-3 py-1 rounded-full ${c.type.includes('Golden') ? 'bg-[#32D74B]/10 text-[#32D74B]' : 'bg-[#FF453A]/10 text-[#FF453A]'}`}>
                                        {c.type.replace('Confirmed ', '')}
                                    </span>
                                    <span className="text-sm text-[#9CA3AF]">{c.date.substring(0, 10)}</span>
                                    <span className="text-sm">${formatPrice(c.price)}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ProDashboard;
