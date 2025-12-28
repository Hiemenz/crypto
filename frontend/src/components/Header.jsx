import React from 'react';
import { TrendingUp, Zap, Menu, X, ChevronLeft } from 'lucide-react';

const Header = ({
    mobileView, // New prop
    onBack,      // New prop
    onLogout    // New prop
}) => {

    return (
        <header className="sticky top-0 z-50 glass-blur-strong bg-[#000000]/70 border-b border-white/10 px-4 lg:px-6 py-3 supports-[backdrop-filter]:bg-black/50 transition-all duration-300">
            <div className="flex items-center justify-between gap-4">

                {/* Left Side: Logo & Mobile Menu */}
                <div className="flex items-center gap-2 lg:gap-4 shrink-0">
                    <div className="lg:hidden">
                        {mobileView === 'detail' ? (
                            <button
                                onClick={onBack}
                                className="p-2 -ml-2 text-[#9CA3AF] hover:text-[#E4E8EC] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#00E5FF]/50 rounded-full hover:bg-[#1E2228]"
                                aria-label="Go Back"
                            >
                                <ChevronLeft size={24} />
                            </button>
                        ) : null}
                    </div>

                    <div className="flex items-center gap-2 lg:gap-3">
                        <div className="w-8 h-8 lg:w-9 lg:h-9 bg-gradient-to-br from-cyan-500/20 to-blue-500/20 rounded-xl flex items-center justify-center border border-white/10 shadow-lg transition-all duration-300 hover:scale-110">
                            <TrendingUp size={18} className="text-[#00E5FF] lg:w-5 lg:h-5" />
                        </div>
                        <h1 className="text-lg lg:text-xl font-semibold text-white tracking-tight font-display">SignalStack</h1>
                    </div>
                </div>

                {/* Right Side - Status (Hidden on very small screens to save space) */}
                <div className="flex items-center gap-4">
                    <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#1E2228]/50 border border-[#00E5FF]/20 animate-glow-pulse">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#00E5FF] shadow-[0_0_8px_#00E5FF] animate-pulse"></div>
                        <span className="text-xs font-semibold text-[#00E5FF]">Live</span>
                    </div>

                    <button
                        onClick={onLogout}
                        className="btn-ghost text-sm py-2 px-4 font-medium"
                    >
                        Sign Out
                    </button>
                </div>
            </div>
        </header>
    );
};

export default Header;
