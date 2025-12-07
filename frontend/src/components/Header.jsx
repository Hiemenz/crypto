import React from 'react';
import { TrendingUp } from 'lucide-react';

const Header = () => {
    return (
        <header className="bg-[#13161B] border-b border-[#1E2228] px-6 py-4">
            <div className="flex items-center justify-between">
                {/* Logo/Brand */}
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gradient-to-br from-[#00E5FF] to-[#0077FF] rounded-lg flex items-center justify-center">
                        <TrendingUp size={20} className="text-black" />
                    </div>
                    <h1 className="text-xl font-bold text-white">Signal Pro</h1>
                </div>

                {/* Right Side - Status */}
                <div className="flex items-center gap-4">
                    <div className="text-xs text-[#9CA3AF]">
                        <span className="text-[#00E5FF] font-bold">●</span> Live
                    </div>
                </div>
            </div>
        </header>
    );
};

export default Header;
