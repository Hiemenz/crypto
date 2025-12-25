import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, Brain, Shield, Zap, ArrowRight, Sparkles, CheckCircle2, Target, BarChart3 } from 'lucide-react';
import StrategySimulator from './StrategySimulator';

const Home = () => {
    return (
        <div className="min-h-screen w-full relative overflow-hidden bg-[#0a0a0a] text-white font-sans selection:bg-cyan-500/30">

            {/* Enhanced Ambient Background */}
            <div className="absolute inset-0 z-0">
                <div className="absolute top-[-20%] left-[-10%] w-[80vw] h-[80vw] bg-gradient-to-br from-[#1a103c] via-[#0f1a3c] to-transparent rounded-full blur-[180px] opacity-50 animate-pulse-slow"></div>
                <div className="absolute bottom-[-20%] right-[-10%] w-[60vw] h-[60vw] bg-gradient-to-tl from-[#0f2e2e] via-[#0a1f2e] to-transparent rounded-full blur-[140px] opacity-40 animate-pulse-slow" style={{ animationDelay: '1s' }}></div>
                <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:100px_100px] opacity-20"></div>
            </div>

            <div className="relative z-10 flex flex-col items-center justify-center min-h-screen p-4 md:p-8">

                {/* Hero Section */}
                <div className="w-full max-w-6xl mx-auto text-center mb-12 fade-in">
                    <div className="mb-8">
                        <div className="inline-flex items-center gap-3 mb-6 px-4 py-2 rounded-full bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-purple-500/10 border border-white/10">
                            <Sparkles className="w-4 h-4 text-cyan-400" />
                            <span className="text-sm font-semibold text-gray-300 tracking-wide">AI-Powered Trading Signals</span>
                        </div>
                        <h1 className="text-5xl md:text-7xl font-bold mb-4 tracking-tight bg-gradient-to-br from-white via-gray-100 to-gray-400 bg-clip-text text-transparent">
                            SignalStack
                        </h1>
                        <p className="text-xl md:text-2xl text-gray-400 font-light tracking-wide mb-8">
                            Know Exactly When to Buy & Sell
                        </p>
                    </div>
                </div>

                {/* Interactive Simulator Section */}
                <div className="w-full max-w-6xl mx-auto mb-16 fade-in-scale px-4">
                    <StrategySimulator mode="demo" />
                </div>

                {/* How It Works Section */}
                <div className="w-full max-w-6xl mx-auto mb-16">
                    <div className="text-center mb-10">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">How It Works</h2>
                        <p className="text-gray-400 text-lg max-w-2xl mx-auto">
                            Our proprietary system combines multiple technical indicators to identify high-probability trading opportunities
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* Step 1 */}
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <BarChart3 className="text-cyan-400" size={24} />
                            </div>
                            <div className="text-cyan-400 font-bold text-sm mb-2">STEP 1</div>
                            <h3 className="text-xl font-bold mb-3">Data Analysis</h3>
                            <p className="text-gray-400 leading-relaxed">
                                We continuously analyze price movements, volume, momentum, and market sentiment across multiple timeframes
                            </p>
                        </div>

                        {/* Step 2 */}
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Target className="text-purple-400" size={24} />
                            </div>
                            <div className="text-purple-400 font-bold text-sm mb-2">STEP 2</div>
                            <h3 className="text-xl font-bold mb-3">Signal Generation</h3>
                            <p className="text-gray-400 leading-relaxed">
                                When all indicators align, we generate a clear buy or sell signal with precise entry points
                            </p>
                        </div>

                        {/* Step 3 */}
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-green-500/20 to-emerald-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <CheckCircle2 className="text-green-400" size={24} />
                            </div>
                            <div className="text-green-400 font-bold text-sm mb-2">STEP 3</div>
                            <h3 className="text-xl font-bold mb-3">Take Action</h3>
                            <p className="text-gray-400 leading-relaxed">
                                You receive instant notifications and can execute trades with confidence, knowing the data supports your decision
                            </p>
                        </div>
                    </div>
                </div>

                {/* Understanding Signals Section */}
                <div className="w-full max-w-6xl mx-auto mb-16">
                    <div className="backdrop-blur-xl bg-[#121212]/60 border border-white/[0.08] rounded-3xl p-8 md:p-12">
                        <h2 className="text-3xl md:text-4xl font-bold mb-8 text-center">Understanding the Signals</h2>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            {/* Buy Signals */}
                            <div className="space-y-4">
                                <div className="flex items-center gap-3 mb-4">
                                    <div className="w-10 h-10 rounded-full bg-[#32D74B]/20 flex items-center justify-center">
                                        <div className="w-5 h-5 rounded-full bg-[#32D74B]"></div>
                                    </div>
                                    <h3 className="text-2xl font-bold text-[#32D74B]">Buy Signals</h3>
                                </div>
                                <p className="text-gray-300 leading-relaxed">
                                    Green dots appear when our system identifies oversold conditions and bullish momentum building. This is when the crowd is fearful, but the data shows opportunity.
                                </p>
                                <ul className="space-y-2 text-gray-400">
                                    <li className="flex items-start gap-2">
                                        <CheckCircle2 className="w-5 h-5 text-[#32D74B] mt-0.5 flex-shrink-0" />
                                        <span>Multiple indicators confirm upward potential</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle2 className="w-5 h-5 text-[#32D74B] mt-0.5 flex-shrink-0" />
                                        <span>Price has reached support levels</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle2 className="w-5 h-5 text-[#32D74B] mt-0.5 flex-shrink-0" />
                                        <span>Market sentiment is overly negative</span>
                                    </li>
                                </ul>
                            </div>

                            {/* Sell Signals */}
                            <div className="space-y-4">
                                <div className="flex items-center gap-3 mb-4">
                                    <div className="w-10 h-10 rounded-full bg-[#FF453A]/20 flex items-center justify-center">
                                        <div className="w-5 h-5 rounded-full bg-[#FF453A]"></div>
                                    </div>
                                    <h3 className="text-2xl font-bold text-[#FF453A]">Sell Signals</h3>
                                </div>
                                <p className="text-gray-300 leading-relaxed">
                                    Red dots appear when our system identifies overbought conditions and bearish momentum. This is when the crowd is greedy, but the data suggests caution.
                                </p>
                                <ul className="space-y-2 text-gray-400">
                                    <li className="flex items-start gap-2">
                                        <CheckCircle2 className="w-5 h-5 text-[#FF453A] mt-0.5 flex-shrink-0" />
                                        <span>Multiple indicators signal downward pressure</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle2 className="w-5 h-5 text-[#FF453A] mt-0.5 flex-shrink-0" />
                                        <span>Price has reached resistance levels</span>
                                    </li>
                                    <li className="flex items-start gap-2">
                                        <CheckCircle2 className="w-5 h-5 text-[#FF453A] mt-0.5 flex-shrink-0" />
                                        <span>Market sentiment is overly positive</span>
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Why It Works Section */}
                <div className="w-full max-w-6xl mx-auto mb-16">
                    <div className="backdrop-blur-xl bg-gradient-to-br from-[#121212]/60 to-[#1a1a1a]/60 border border-white/[0.08] rounded-3xl p-8 md:p-12 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent"></div>

                        <h2 className="text-3xl md:text-4xl font-bold mb-6 text-center">
                            <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
                                The Contrarian Advantage
                            </span>
                        </h2>

                        <p className="text-lg text-gray-300 leading-relaxed max-w-3xl mx-auto text-center mb-8">
                            Most traders lose money because they buy when everyone is buying (high prices) and sell when everyone is selling (low prices). Our system does the opposite.
                        </p>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="bg-[#0d0d0f]/60 rounded-2xl p-6 border border-red-500/20">
                                <div className="text-red-400 font-bold text-sm mb-2">❌ EMOTIONAL TRADING</div>
                                <h3 className="text-xl font-bold mb-3 text-red-400">Following the Crowd</h3>
                                <ul className="space-y-2 text-gray-400 text-sm">
                                    <li>• Buy when prices are high (FOMO)</li>
                                    <li>• Sell when prices are low (panic)</li>
                                    <li>• Decisions driven by fear and greed</li>
                                    <li>• No clear strategy or plan</li>
                                </ul>
                            </div>

                            <div className="bg-[#0d0d0f]/60 rounded-2xl p-6 border border-green-500/20">
                                <div className="text-green-400 font-bold text-sm mb-2">✓ DATA-DRIVEN TRADING</div>
                                <h3 className="text-xl font-bold mb-3 text-green-400">Going Against the Herd</h3>
                                <ul className="space-y-2 text-gray-400 text-sm">
                                    <li>• Buy when prices are low (opportunity)</li>
                                    <li>• Sell when prices are high (profit)</li>
                                    <li>• Decisions based on technical analysis</li>
                                    <li>• Clear signals with defined entry/exit</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Feature Grid */}
                <div className="w-full max-w-6xl mx-auto mb-16">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Brain className="text-cyan-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Multi-Indicator System</h3>
                            <p className="text-sm text-gray-400 leading-relaxed">
                                Advanced combination of technical indicators working in harmony
                            </p>
                        </div>

                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <TrendingUp className="text-purple-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Contrarian Edge</h3>
                            <p className="text-sm text-gray-400 leading-relaxed">
                                Identify opportunities when the crowd is wrong
                            </p>
                        </div>

                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-green-500/20 to-emerald-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Shield className="text-green-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Emotion-Free Trading</h3>
                            <p className="text-sm text-gray-400 leading-relaxed">
                                Remove fear and greed from your decision-making
                            </p>
                        </div>

                        <div className="backdrop-blur-xl bg-[#121212]/40 border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 group">
                            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                                <Zap className="text-orange-400" size={24} />
                            </div>
                            <h3 className="text-lg font-bold mb-2">Real-Time Signals</h3>
                            <p className="text-sm text-gray-400 leading-relaxed">
                                Get actionable insights when opportunities emerge
                            </p>
                        </div>
                    </div>
                </div>

                {/* CTA Section */}
                <div className="w-full max-w-4xl mx-auto mb-8">
                    <div className="backdrop-blur-xl bg-gradient-to-br from-cyan-500/10 via-blue-500/10 to-purple-500/10 border border-white/[0.12] rounded-3xl p-8 md:p-12 text-center">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">Ready to Start Trading Smarter?</h2>
                        <p className="text-lg text-gray-300 mb-8 max-w-2xl mx-auto">
                            Join thousands of traders who have removed emotion from their trading and started following the data
                        </p>

                        <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
                            <Link
                                to="/signup"
                                className="w-full sm:w-auto btn-primary flex items-center justify-center gap-2 group text-base px-8 py-4"
                            >
                                <span>Get Started Free</span>
                                <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                            </Link>
                            <Link
                                to="/login"
                                className="w-full sm:w-auto btn-secondary flex items-center justify-center gap-2 text-base px-8 py-4"
                            >
                                Sign In
                            </Link>
                        </div>
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
