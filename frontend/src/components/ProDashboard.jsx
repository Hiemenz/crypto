import React, { useState, useEffect, useMemo } from 'react';
import DashboardLayout from './dashboard/DashboardLayout';
import AssetList from './dashboard/AssetList';
import ChartSection from './dashboard/ChartSection';
import StrategySimulator from './StrategySimulator';
import HeatMapView from './HeatMapView';
import { Search, BarChart3, Calculator, Grid3X3 } from 'lucide-react';
import { dataUrl } from '../utils/storage';

const ProDashboard = ({ onLogout }) => {
    const [signals, setSignals] = useState([]);
    // eslint-disable-next-line no-unused-vars
    const [crosses, setCrosses] = useState([]);
    const [historyData, setHistoryData] = useState(null);
    const [forecastData, setForecastData] = useState(null);
    const [heatmapData, setHeatmapData] = useState(null);
    const [activeTab, setActiveTab] = useState('crypto'); // 'crypto' | 'stocks'
    const [selectedSymbol, setSelectedSymbol] = useState('BTC-USD');
    const [searchTerm, setSearchTerm] = useState('');
    const [loading, setLoading] = useState(true);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [chartRange, setChartRange] = useState('ALL');
    const [currentView, setCurrentView] = useState('market'); // 'market' | 'lab' | 'heatmap'

    // Initial Data Load
    useEffect(() => {
        Promise.all([
            fetch(dataUrl('latest_signals.json')).then(r => r.json()),
            fetch(dataUrl('crosses.json')).then(r => r.json()),
            fetch(dataUrl('heatmap.json')).then(r => r.json()).catch(() => null),
        ]).then(([sig, cr, hm]) => {
            setSignals(sig.signals);
            setCrosses(cr.crosses);
            if (hm) setHeatmapData(hm);

            // Default selection logic
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
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // History + Forecast Data Fetch
    useEffect(() => {
        if (!selectedSymbol) return;
        setHistoryData(null);
        setForecastData(null);

        fetch(dataUrl(`history/${selectedSymbol}.json`))
            .then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            })
            .then(json => {
                if (!json.data || !Array.isArray(json.data)) throw new Error('Invalid data format');
                const processed = json.data.map(d => ({
                    date: d.Date,
                    price: parseFloat(d.Close),
                    Open: parseFloat(d.Open),
                    High: parseFloat(d.High),
                    Low: parseFloat(d.Low),
                    Close: parseFloat(d.Close),
                    Volume: parseFloat(d.Volume),
                    signalType: (d.signal && d.signal.includes('Buy')) ? 'buy' : (d.signal && d.signal.includes('Sell')) ? 'sell' : null
                }));
                setHistoryData(processed);
            })
            .catch(err => console.error('History error:', err));

        // Forecast is best-effort: generated nightly, may not exist for all symbols
        fetch(dataUrl(`forecasts/${selectedSymbol}.json`))
            .then(res => res.ok ? res.json() : null)
            .then(json => json?.forecast ? setForecastData(json.forecast) : null)
            .catch(() => null);
    }, [selectedSymbol]);

    // Computed Lists
    const assetList = useMemo(() =>
        signals.filter(s => s.category === activeTab)
            .filter(s => s.symbol.toLowerCase().includes(searchTerm.toLowerCase()))
            .sort((a, b) => b.score - a.score),
        [signals, activeTab, searchTerm]
    );

    const currentSignal = useMemo(() => signals.find(s => s.symbol === selectedSymbol), [signals, selectedSymbol]);

    const chartData = useMemo(() => {
        if (!historyData) return [];
        if (chartRange === 'ALL') return historyData;
        const cutoff = new Date();
        if (chartRange === '1Y') cutoff.setFullYear(cutoff.getFullYear() - 1);
        if (chartRange === '3Y') cutoff.setFullYear(cutoff.getFullYear() - 3);
        if (chartRange === '5Y') cutoff.setFullYear(cutoff.getFullYear() - 5);
        if (chartRange === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
        if (chartRange === '1M') cutoff.setMonth(cutoff.getMonth() - 1);
        return historyData.filter(d => new Date(d.date) >= cutoff);
    }, [historyData, chartRange]);

    if (loading) return (
        <div className="h-screen flex items-center justify-center bg-app text-primary">
            <div className="animate-pulse">Loading SignalStack...</div>
        </div>
    );

    const SidebarContent = (
        <div className="flex flex-col h-full">
            {/* View Switching */}
            <div className="px-4 pt-4">
                <div className="flex bg-panel border border-border-subtle rounded-lg p-1 gap-0.5">
                    <button
                        onClick={() => setCurrentView('market')}
                        className={`flex-1 flex items-center justify-center gap-1.5 text-xs font-bold py-1.5 rounded-md transition-all ${currentView === 'market' ? 'bg-white text-black shadow-sm' : 'text-muted hover:text-white'}`}
                    >
                        <BarChart3 size={13} />
                        <span>Market</span>
                    </button>
                    <button
                        onClick={() => setCurrentView('heatmap')}
                        className={`flex-1 flex items-center justify-center gap-1.5 text-xs font-bold py-1.5 rounded-md transition-all ${currentView === 'heatmap' ? 'bg-white text-black shadow-sm' : 'text-muted hover:text-white'}`}
                    >
                        <Grid3X3 size={13} />
                        <span>Heat</span>
                    </button>
                    <button
                        onClick={() => setCurrentView('lab')}
                        className={`flex-1 flex items-center justify-center gap-1.5 text-xs font-bold py-1.5 rounded-md transition-all ${currentView === 'lab' ? 'bg-white text-black shadow-sm' : 'text-muted hover:text-white'}`}
                    >
                        <Calculator size={13} />
                        <span>Lab</span>
                    </button>
                </div>
            </div>

            <div className="h-px bg-border-subtle mx-4 my-4"></div>

            {/* Tabs & Search */}
            <div className="px-4 space-y-4">
                {/* Type Toggle */}
                <div className="flex bg-panel border border-border-subtle rounded-lg p-1">
                    <button
                        onClick={() => setActiveTab('stocks')}
                        className={`flex-1 text-sm font-bold py-1.5 rounded-md transition-all ${activeTab === 'stocks' ? 'bg-white text-black shadow-sm' : 'text-muted hover:text-white'
                            }`}
                    >
                        Stocks
                    </button>
                    <button
                        onClick={() => setActiveTab('crypto')}
                        className={`flex-1 text-sm font-bold py-1.5 rounded-md transition-all ${activeTab === 'crypto' ? 'bg-white text-black shadow-sm' : 'text-muted hover:text-white'
                            }`}
                    >
                        Crypto
                    </button>
                </div>

                {/* Search */}
                <div className="relative">
                    <Search className="absolute left-3 top-2.5 w-4 h-4 text-muted" />
                    <input
                        value={searchTerm}
                        onChange={e => setSearchTerm(e.target.value)}
                        placeholder="Search assets..."
                        className="w-full bg-bg-input border border-border-subtle rounded-lg py-2 pl-10 pr-4 text-sm text-primary focus:border-trade-accent focus:outline-none focus:ring-1 focus:ring-trade-accent transition-all"
                    />
                </div>
            </div>

            {/* List */}
            {/* We keep the list visible even in Lab mode, though it primarily affects the 'Market' view selection. 
                 Ideally, clicking an asset here could switch the lab asset too, but for now we keep them decoupled or 'Market' focused. 
             */}
            <div className="flex-1 overflow-hidden mt-4 flex flex-col min-h-0">
                <AssetList
                    assets={assetList}
                    selectedSymbol={selectedSymbol}
                    onSelect={(item) => {
                        setSelectedSymbol(item.symbol);
                        setSidebarOpen(false); // Close mobile drawer on select
                        if (currentView === 'lab') {
                            // Optional: switch back to market or just select it?
                            // Let's stay in lab, but maybe the lab should listen to selectedSymbol?
                            // For this iteration, Lab is independent.
                        }
                    }}
                />
            </div>
        </div>
    );

    return (
        <DashboardLayout
            sidebarContent={SidebarContent}
            sidebarOpen={sidebarOpen}
            setSidebarOpen={setSidebarOpen}
            onLogout={onLogout}
        >
            <div className="relative flex-1 h-full flex flex-col bg-app">
                {currentView === 'market' ? (
                    <ChartSection
                        data={chartData}
                        symbol={selectedSymbol}
                        range={chartRange}
                        onRangeChange={setChartRange}
                        currentSignal={currentSignal}
                        forecastData={forecastData}
                    />
                ) : currentView === 'heatmap' ? (
                    <div className="flex-1 overflow-y-auto">
                        <HeatMapView
                            heatmapData={heatmapData}
                            activeTab={activeTab}
                            onSelectSymbol={(sym) => {
                                setSelectedSymbol(sym);
                                setCurrentView('market');
                                setSidebarOpen(false);
                            }}
                        />
                    </div>
                ) : (
                    <div className="flex-1 overflow-y-auto p-4 md:p-8">
                        <StrategySimulator mode="pro" />
                    </div>
                )}
            </div>
        </DashboardLayout>
    );
};

export default ProDashboard;
