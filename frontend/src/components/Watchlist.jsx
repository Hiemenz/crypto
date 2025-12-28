import React from 'react';
import SignalCard from './SignalCard';
import { PlusCircle } from 'lucide-react';

const Watchlist = ({ allSignals, watchlist, setWatchlist }) => {
    // watchlist is an array of symbols (strings)

    const removeFromWatchlist = (symbol) => {
        setWatchlist(prev => prev.filter(s => s !== symbol));
    };

    // Filter signals to only show watched items
    const watchedSignals = allSignals.filter(item => watchlist.includes(item.symbol));

    // If a watched item is not in the signals list (e.g. no data yet for today), 
    // we might want to still show it? For MVP, only show if we have data.
    // Or we can stub it.

    return (
        <div className="mb-12">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-white">Your Watchlist</h2>
                <span className="text-sm text-slate-400">
                    {watchedSignals.length} Active / 50 Limit
                </span>
            </div>

            {watchedSignals.length === 0 ? (
                <div className="glass-card rounded-xl p-8 text-center border-dashed border-2 border-slate-700">
                    <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-slate-800 mb-4 text-slate-400">
                        <PlusCircle />
                    </div>
                    <h3 className="text-lg font-medium text-white mb-2">Your watchlist is empty</h3>
                    <p className="text-slate-400 max-w-sm mx-auto">
                        Add assets from the "Market Pulse" section below to track high-quality signals without the noise.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {watchedSignals.map(item => (
                        <SignalCard
                            key={item.symbol}
                            {...item}
                            actionLabel="Remove"
                            onAction={removeFromWatchlist}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export default Watchlist;
