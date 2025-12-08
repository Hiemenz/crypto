import React from 'react';

const AuthLayout = ({ children, title, subtitle }) => {
    return (
        <div className="min-h-screen w-full relative overflow-hidden bg-[#0a0a0a] text-white font-sans selection:bg-cyan-500/30">

            {/* Sophisticated Ambient Background */}
            <div className="absolute inset-0 z-0">
                {/* Deep, subtle mesh gradients - much darker and smoother */}
                <div className="absolute top-[-20%] left-[-10%] w-[80vw] h-[80vw] bg-[#1a103c] rounded-full blur-[180px] opacity-40 animate-pulse duration-[10s]"></div>
                <div className="absolute bottom-[-20%] right-[-10%] w-[60vw] h-[60vw] bg-[#0f2e2e] rounded-full blur-[140px] opacity-30 animate-pulse duration-[12s] delay-1000"></div>
                <div className="absolute top-[40%] left-[30%] w-[40vw] h-[40vw] bg-[#101015] rounded-full blur-[100px] opacity-80"></div>

                {/* Fine grain noise for texture */}
                <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-[0.03] mix-blend-overlay"></div>
            </div>

            <div className="relative z-10 flex flex-col items-center justify-center min-h-screen p-4">
                {/* Premium Glass Card */}
                <div className="w-full max-w-[440px] backdrop-blur-3xl bg-[#121212]/60 border border-white/[0.06] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.6)] rounded-2xl p-8 md:p-10 relative overflow-hidden transition-all duration-500 hover:border-white/[0.08]">

                    {/* Subtle top sheen */}
                    <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>

                    <div className="relative z-20">
                        <div className="mb-10 text-center">
                            <h1 className="text-3xl md:text-4xl font-bold mb-3 tracking-tight font-display text-white">
                                {title}
                            </h1>
                            {subtitle && (
                                <p className="text-gray-400 text-base font-light tracking-wide">
                                    {subtitle}
                                </p>
                            )}
                        </div>

                        {children}
                    </div>
                </div>

                {/* Footer copyright or minimalist branding could go here */}
                <div className="mt-8 text-xs text-gray-600 font-medium tracking-widest uppercase opacity-60">
                    SignalStack PRO
                </div>
            </div>
        </div>
    );
};

export default AuthLayout;
