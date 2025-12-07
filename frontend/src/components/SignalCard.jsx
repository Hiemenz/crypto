import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const SignalCard = ({ symbol, signal, score, price, change, onAction, actionLabel }) => {
    const isBuy = signal.toLowerCase().includes('buy');
    const isSell = signal.toLowerCase().includes('sell');

    let statusColor = "text-slate-400";
    let statusBg = "bg-slate-800";
    let Icon = Minus;

    if (isBuy) {
        statusColor = "text-green-400";
        statusBg = "bg-green-500/10";
        Icon = TrendingUp;
    } else if (isSell) {
        statusColor = "text-red-400";
        statusBg = "bg-red-500/10";
        Icon = TrendingDown;
    } else {
        // Hold / Neutral
        statusColor = "text-blue-400";
        statusBg = "bg-blue-500/10";
    }

    // Format price
    const formattedPrice = price != null
        ? (price < 1 ? price.toFixed(5) : price.toLocaleString(undefined, { maximumFractionDigits: 2 }))
        : 'N/A';

    return (
        <div className="glass-card rounded-xl p-5 hover:border-slate-600 transition-all duration-300">
            <div className="flex justify-between items-start mb-4">
                <div>
                    <h3 className="text-xl font-bold tracking-tight text-white">{symbol}</h3>
                    <div className="flex items-center gap-2 mt-1">
                        <span className="text-2xl font-semibold">${formattedPrice}</span>
                        {/* Change would be here if available in JSON */}
                    </div>
                </div>
                <div className={`rounded-full p-2 ${statusBg}`}>
                    <Icon className={`w-6 h-6 ${statusColor}`} />
                </div>
            </div>

            <div className="space-y-3">
                {/* Signal Badge */}
                <div className="flex justify-between items-center">
                    <span className="text-sm text-slate-400">Signal</span>
                    <span className={`font-medium px-2 py-0.5 rounded text-sm border ${statusColor} border-opacity-20 ${statusBg}`}>
                        {signal || "Neutral"}
                    </span>
                </div>

                {/* Score Bar */}
                <div>
                    <div className="flex justify-between text-sm mb-1">
                        <span className="text-slate-400">Score</span>
                        <span className="font-bold text-white">{score}</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-700 rounded-full overflow-hidden">
                        <div
                            className={`h-full rounded-full transition-all duration-500 ${isBuy ? 'bg-gradient-to-r from-green-500 to-emerald-400' : (isSell ? 'bg-gradient-to-r from-red-500 to-orange-400' : 'bg-blue-500')}`}
                            style={{ width: `${score}%` }}
                        />
                    </div>
                </div>
            </div>

            {/* Action Button */}
            {onAction && (
                <button
                    onClick={() => onAction(symbol)}
                    className="mt-5 w-full py-2 bg-slate-700 hover:bg-slate-600 active:bg-slate-700 text-white text-sm font-medium rounded-lg transition-colors border border-transparent hover:border-slate-500"
                >
                    {actionLabel}
                </button>
            )}
        </div>
    );
};

export default SignalCard;
