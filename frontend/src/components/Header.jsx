import React from 'react';
import { TrendingUp, Zap, Menu, X } from 'lucide-react';

const Header = ({
    activeTab,
    setActiveTab,
    signals = [],
    sidebarOpen,
    setSidebarOpen
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
        <header className="sticky top-0 z-50 bg-[#13161B]/95 backdrop-blur-md border-b border-[#1E2228] px-4 lg:px-6 py-3">
            <div className="flex items-center justify-between gap-4">

                {/* Left Side: Logo & Mobile Menu */}
                <div className="flex items-center gap-2 lg:gap-4 shrink-0">
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="lg:hidden p-2 -ml-2 text-[#9CA3AF] hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-[#00E5FF]/50 rounded-md"
                        aria-label="Toggle Navigation Menu"
                    >
                        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>

                    <div className="flex items-center gap-2 lg:gap-3">
                        <div className="w-8 h-8 lg:w-10 lg:h-10 bg-gradient-to-br from-[#00E5FF] to-[#0077FF] rounded-lg flex items-center justify-center shadow-[0_0_15px_rgba(0,229,255,0.3)]">
                            <TrendingUp size={18} className="text-black lg:w-5 lg:h-5" />
                        </div>
                        <h1 className="hidden sm:block text-lg lg:text-xl font-bold text-white tracking-tight">Signal Pro</h1>
                    </div>
                </div>

                {/* Center: Toggle (Responsive width) */}
                <div className="flex-1 max-w-[280px] sm:max-w-md mx-auto">
                    <div className="relative flex items-center bg-[#0B0D10]/50 rounded-lg p-1 border border-[#1E2228]/50">
                        {/* Animated Background */}
                        <div
                            className="absolute top-1 bottom-1 rounded-md transition-all duration-300 ease-out bg-[#1E2228] border border-[#323842]"
                            style={{
                                left: '4px',
                                width: 'calc(50% - 4px)',
                                transform: activeTab === 'stocks' ? 'translateX(0)' : 'translateX(100%)'
                            }}
                        />

                        {/* Stocks Button */}
                        <button
                            onClick={() => setActiveTab('stocks')}
                            aria-label="Filter by Stocks"
                            className={`relative z-10 flex-1 py-1.5 lg:py-2 text-xs lg:text-sm font-medium transition-colors duration-200 flex items-center justify-center gap-2 bg-transparent focus:outline-none focus:ring-2 focus:ring-[#00E5FF]/50 rounded-md ${activeTab === 'stocks' ? 'text-white' : 'text-[#5F6670] hover:text-[#E4E8EC]'
                                }`}
                        >
                            <TrendingUp size={14} className={activeTab === 'stocks' ? 'text-[#00E5FF]' : ''} />
                            <span className="hidden sm:inline">Stocks</span>
                            {getCount('stocks') && (
                                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${activeTab === 'stocks' ? 'bg-[#00E5FF]/10 text-[#00E5FF]' : 'bg-[#1E2228] text-[#5F6670]'
                                    }`}>
                                    {getCount('stocks')}
                                </span>
                            )}
                        </button>

                        {/* Crypto Button */}
                        <button
                            onClick={() => setActiveTab('crypto')}
                            aria-label="Filter by Crypto"
                            className={`relative z-10 flex-1 py-1.5 lg:py-2 text-xs lg:text-sm font-medium transition-colors duration-200 flex items-center justify-center gap-2 bg-transparent focus:outline-none focus:ring-2 focus:ring-[#FFD60A]/50 rounded-md ${activeTab === 'crypto' ? 'text-white' : 'text-[#5F6670] hover:text-[#E4E8EC]'
                                }`}
                        >
                            <Zap size={14} className={activeTab === 'crypto' ? 'text-[#FFD60A]' : ''} />
                            <span className="hidden sm:inline">Crypto</span>
                            {getCount('crypto') && (
                                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${activeTab === 'crypto' ? 'bg-[#FFD60A]/10 text-[#FFD60A]' : 'bg-[#1E2228] text-[#5F6670]'
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
        </header >
    );
};

export default Header;
