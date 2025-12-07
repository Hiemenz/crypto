import React from 'react';
import SignalCard from './SignalCard';
import { Sparkles } from 'lucide-react';

const Outsiders = ({ allSignals, watchlist, addToWatchlist }) => {
    // Logic: 
    // 1. Exclude items already in watchlist.
    // 2. Filter for "Excellent" or "Great" Buy/Sell signals.
    // 3. Sort by Score (descending).
    // 4. Limit to top 6?

    const outsiders = allSignals
        .filter(item => !watchlist.includes(item.symbol))
        .filter(item => {
            const sig = (item.signal || "").toLowerCase();
            // "5 indicators align" approximation: High quality signals only
            return sig.includes("excellent") || sig.includes("great");
        })
        .sort((a, b) => b.score - a.score)
        .slice(0, 9);

    if (outsiders.length === 0) return null;

    return (
        <div className="mb-12">
            <div className="flex items-center gap-2 mb-6">
                <Sparkles className="w-6 h-6 text-yellow-500" />
                <h2 className="text-2xl font-bold text-white">Market Pulse</h2>
            </div>
            <p className="text-slate-400 mb-6 -mt-4">
                High-conviction opportunities outside your watchlist.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {outsiders.map(item => (
                    <SignalCard
                        key={item.symbol}
                        {...item}
                        actionLabel="Add to Watchlist"
                        onAction={addToWatchlist}
                    />
                ))}
            </div>
        </div>
    );
};

export default Outsiders;
