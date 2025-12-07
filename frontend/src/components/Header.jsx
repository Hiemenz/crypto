import React from 'react';
import { TrendingUp, Zap, Menu, X, ChevronLeft } from 'lucide-react';

const Header = ({
    activeTab,
    setActiveTab,
    signals = [],
    sidebarOpen,
    setSidebarOpen,
    mobileView, // New prop
    onBack      // New prop
}) => {

    // Helper to get counts
    const getCount = (category) => {
        if (!signals.length) return null;
        const catSignals = signals.filter(s => s.category === category && s.side !== 'hold');
        const buyCount = catSignals.filter(s => s.side === 'buy').length;
        const sellCount = catSignals.filter(s => s.side === 'sell').length;
        if (buyCount > 0 && sellCount > 0) return `${buyCount}↑ ${sellCount}↓`;
        if (buyCount > 0) return `${buyCount} Buy`;
        if (sellCount > 0) return `${sellCount} Sell`;
        return null;
    };

    return (
        <header className="sticky top-0 z-50 bg-[#000000]/80 backdrop-blur-xl border-b border-white/5 px-4 lg:px-6 py-3 supports-[backdrop-filter]:bg-black/60">
            <div className="flex items-center justify-between gap-4">

                {/* Left Side: Logo & Mobile Menu */}
                <div className="flex items-center gap-2 lg:gap-4 shrink-0">
                    <div className="lg:hidden">
                        {mobileView === 'detail' ? (
                            <button
                                onClick={onBack}
                                className="p-2 -ml-2 text-[#9CA3AF] hover:text-[#E4E8EC] transition-colors focus:outline-none focus:ring-2 focus:ring-[#00E5FF]/50 rounded-full hover:bg-[#1E2228]"
                                aria-label="Go Back"
                            >
                                <ChevronLeft size={24} />
                            </button>
                        ) : null}
                    </div>

                    <div className="flex items-center gap-2 lg:gap-3">
                        <div className="w-8 h-8 lg:w-9 lg:h-9 bg-gradient-to-br from-[#2c2c2e] to-[#1c1c1e] rounded-[10px] flex items-center justify-center border border-white/10 shadow-sm">
                            <TrendingUp size={18} className="text-[#0A84FF] lg:w-5 lg:h-5" />
                        </div>
                        <h1 className="hidden sm:block text-lg lg:text-xl font-semibold text-white tracking-tight font-display">Signal Pro</h1>
                    </div>
                </div>

                {/* Center: Toggle (iOS Segmented Control Style) */}
                <div className="flex-1 max-w-[280px] sm:max-w-[320px] mx-auto">
                    <div className="relative flex items-center bg-[#767680]/20 rounded-lg p-[2px]">
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
                            className={`relative z-10 flex-1 py-1.5 text-[13px] font-medium transition-colors duration-200 flex items-center justify-center gap-1.5 rounded-[6px] ${activeTab === 'stocks' ? 'text-white' : 'text-[#86868b] hover:text-white'
                                }`}
                        >
                            <TrendingUp size={13} strokeWidth={2.5} className={activeTab === 'stocks' ? 'text-white' : 'text-[#86868b]'} />
                            <span>Stocks</span>
                            {getCount('stocks') && (
                                <span className={`text-[10px] px-1.5 py-[1px] rounded-full font-semibold ml-1 ${activeTab === 'stocks' ? 'bg-white/20 text-white' : 'bg-black/20 text-[#86868b]'
                                    }`}>
                                    {getCount('stocks')}
                                </span>
                            )}
                        </button>

                        {/* Crypto Button */}
                        <button
                            onClick={() => setActiveTab('crypto')}
                            className={`relative z-10 flex-1 py-1.5 text-[13px] font-medium transition-colors duration-200 flex items-center justify-center gap-1.5 rounded-[6px] ${activeTab === 'crypto' ? 'text-white' : 'text-[#86868b] hover:text-white'
                                }`}
                        >
                            <Zap size={13} strokeWidth={2.5} className={activeTab === 'crypto' ? 'text-white' : 'text-[#86868b]'} />
                            <span>Crypto</span>
                            {getCount('crypto') && (
                                <span className={`text-[10px] px-1.5 py-[1px] rounded-full font-semibold ml-1 ${activeTab === 'crypto' ? 'bg-white/20 text-white' : 'bg-black/20 text-[#86868b]'
                                    }`}>
                                    {getCount('crypto')}
                                </span>
                            )}
                        </button>
                    </div>
                </div>

                {/* Right Side - Status (Hidden on very small screens to save space) */}
                <div className="hidden sm:flex items-center gap-4">
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#1E2228]/50 border border-[#1E2228]">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#00E5FF] shadow-[0_0_8px_#00E5FF]"></div>
                        <span className="text-xs font-medium text-[#E4E8EC]">Live</span>
                    </div>
                </div>
            </div>
        </header>
    );
};

export default Header;
