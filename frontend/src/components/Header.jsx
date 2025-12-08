import React from 'react';
import { TrendingUp, Zap, Menu, X, ChevronLeft } from 'lucide-react';

const Header = ({
    sidebarOpen,
    setSidebarOpen,
    mobileView, // New prop
    onBack,      // New prop
    onLogout    // New prop
}) => {

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
                        <h1 className="text-lg lg:text-xl font-semibold text-white tracking-tight font-display">SignalStack</h1>
                    </div>
                </div>

                {/* Right Side - Status (Hidden on very small screens to save space) */}
                <div className="flex items-center gap-4">
                    <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#1E2228]/50 border border-[#1E2228]">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#00E5FF] shadow-[0_0_8px_#00E5FF]"></div>
                        <span className="text-xs font-medium text-[#E4E8EC]">Live</span>
                    </div>

                    <button
                        onClick={onLogout}
                        className="text-[#9CA3AF] hover:text-[#E4E8EC] text-sm font-medium transition-colors"
                    >
                        Sign Out
                    </button>
                </div>
            </div>
        </header>
    );
};

export default Header;
