import React from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, Brain, Shield, Zap } from 'lucide-react';

const Home = () => {
    return (
        <div className="min-h-screen w-full relative overflow-hidden bg-[#0a0a0a] text-white font-sans selection:bg-cyan-500/30">

            {/* Sophisticated Ambient Background */}
            <div className="absolute inset-0 z-0">
                {/* Deep, subtle mesh gradients */}
                <div className="absolute top-[-20%] left-[-10%] w-[80vw] h-[80vw] bg-[#1a103c] rounded-full blur-[180px] opacity-40 animate-pulse duration-[10s]"></div>
                <div className="absolute bottom-[-20%] right-[-10%] w-[60vw] h-[60vw] bg-[#0f2e2e] rounded-full blur-[140px] opacity-30 animate-pulse duration-[12s] delay-1000"></div>
                <div className="absolute top-[40%] left-[30%] w-[40vw] h-[40vw] bg-[#101015] rounded-full blur-[100px] opacity-80"></div>

                {/* Fine grain noise for texture */}
                <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-[0.03] mix-blend-overlay"></div>
            </div>

            <div className="relative z-10 flex flex-col items-center justify-center min-h-screen p-4 md:p-8">

                {/* Hero Section */}
                <div className="w-full max-w-5xl mx-auto text-center mb-12">

                    {/* Logo/Brand */}
                    <div className="mb-8">
                        <h1 className="text-6xl md:text-8xl font-bold mb-4 tracking-tight bg-gradient-to-br from-white via-gray-200 to-gray-500 bg-clip-text text-transparent">
                            SignalStack
                        </h1>
                        <p className="text-xl md:text-2xl text-gray-400 font-light tracking-wide">
                            Professional Trading Signals
                        </p>
                    </div>

                    {/* Main Value Proposition */}
                    <div className="backdrop-blur-3xl bg-[#121212]/60 border border-white/[0.06] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.6)] rounded-3xl p-8 md:p-12 mb-8 relative overflow-hidden">

                        {/* Subtle top sheen */}
                        <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>

                        <div className="relative z-20">
                            <h2 className="text-3xl md:text-5xl font-bold mb-6 tracking-tight leading-tight">
                                Trade Against the Herd.<br />
                                <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                                    Remove Emotion.
                                </span>
                            </h2>

                            <p className="text-lg md:text-xl text-gray-300 leading-relaxed mb-6 max-w-3xl mx-auto">
                                Our proprietary strategy is built on a sophisticated combination of technical indicators
                                specifically designed to position you <span className="text-white font-semibold">against the herd</span>.
                            </p>

                            <p className="text-base md:text-lg text-gray-400 leading-relaxed max-w-2xl mx-auto">
                                While others chase trends driven by fear and greed, our system identifies
                                contrarian opportunities with mathematical precision. No emotion. No guesswork.
                                Just data-driven signals that give you an edge.
                            </p>
                        </div>
                    </div>

                    {/* Feature Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-12">

                        {/* Feature 1 */}
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.04] rounded-xl p-6 hover:border-white/[0.08] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Brain className="text-cyan-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Multi-Indicator System</h3>
                            <p className="text-sm text-gray-400">
                                Advanced combination of technical indicators working in harmony
                            </p>
                        </div>

                        {/* Feature 2 */}
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.04] rounded-xl p-6 hover:border-white/[0.08] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <TrendingUp className="text-purple-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Contrarian Edge</h3>
                            <p className="text-sm text-gray-400">
                                Identify opportunities when the crowd is wrong
                            </p>
                        </div>

                        {/* Feature 3 */}
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.04] rounded-xl p-6 hover:border-white/[0.08] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-green-500/20 to-emerald-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Shield className="text-green-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Emotion-Free Trading</h3>
                            <p className="text-sm text-gray-400">
                                Remove fear and greed from your decision-making
                            </p>
                        </div>

                        {/* Feature 4 */}
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.04] rounded-xl p-6 hover:border-white/[0.08] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-orange-500/20 to-red-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Zap className="text-orange-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Real-Time Signals</h3>
                            <p className="text-sm text-gray-400">
                                Get actionable insights when opportunities emerge
                            </p>
                        </div>
                    </div>

                    {/* CTA Buttons */}
                    <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
                        <Link
                            to="/signup"
                            className="w-full sm:w-auto bg-white text-black hover:bg-gray-100 font-bold text-base px-8 py-4 rounded-lg transition-all duration-200 shadow-lg shadow-white/10 hover:shadow-white/20 hover:scale-105"
                        >
                            Get Started
                        </Link>
                        <Link
                            to="/login"
                            className="w-full sm:w-auto bg-transparent border border-white/20 hover:border-white/40 text-white font-semibold text-base px-8 py-4 rounded-lg transition-all duration-200 hover:bg-white/5"
                        >
                            Sign In
                        </Link>
                    </div>
                </div>

                {/* Footer */}
                <div className="mt-8 text-xs text-gray-600 font-medium tracking-widest uppercase opacity-60">
                    SignalStack PRO
                </div>
            </div>
        </div>
    );
};

export default Home;
