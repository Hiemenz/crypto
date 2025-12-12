import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const SignalCard = ({ symbol, signal, score, price, change, onAction, actionLabel }) => {
    const isBuy = signal.toLowerCase().includes('buy');
    const isSell = signal.toLowerCase().includes('sell');

    let statusColor = "text-slate-400";
    let statusBg = "bg-slate-800/50";
    let Icon = Minus;
    let gradientClass = "from-slate-500/20 to-slate-600/20";

    if (isBuy) {
        statusColor = "text-[#32D74B]";
        statusBg = "bg-[#32D74B]/10";
        Icon = TrendingUp;
        gradientClass = "from-green-500/20 to-emerald-500/20";
    } else if (isSell) {
        statusColor = "text-[#FF453A]";
        statusBg = "bg-[#FF453A]/10";
        Icon = TrendingDown;
        gradientClass = "from-red-500/20 to-orange-500/20";
    } else {
        // Hold / Neutral
        statusColor = "text-[#0A84FF]";
        statusBg = "bg-[#0A84FF]/10";
        gradientClass = "from-blue-500/20 to-cyan-500/20";
    }

    // Format price
    const formattedPrice = price != null
        ? (price < 1 ? price.toFixed(5) : price.toLocaleString(undefined, { maximumFractionDigits: 2 }))
        : 'N/A';

    return (
        <div className="card-elevated p-6 group transition-all duration-300 hover:scale-[1.02]">
            {/* Gradient overlay on hover */}
            <div className={`absolute inset-0 bg-gradient-to-br ${gradientClass} opacity-0 group-hover:opacity-100 transition-opacity duration-300 rounded-2xl pointer-events-none`}></div>

            <div className="relative z-10">
                <div className="flex justify-between items-start mb-4">
                    <div>
                        <h3 className="text-xl font-bold tracking-tight text-white mb-2">{symbol}</h3>
                        <div className="flex items-center gap-2">
                            <span className="text-2xl font-semibold text-white">${formattedPrice}</span>
                        </div>
                    </div>
                    <div className={`rounded-xl p-2.5 ${statusBg} transition-all duration-300 group-hover:scale-110`}>
                        <Icon className={`w-6 h-6 ${statusColor}`} />
                    </div>
                </div>

                <div className="space-y-4">
                    {/* Signal Badge */}
                    <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-400 font-medium">Signal</span>
                        <span className={`font-semibold px-3 py-1.5 rounded-lg text-sm ${statusColor} ${statusBg} border border-white/5`}>
                            {signal || "Neutral"}
                        </span>
                    </div>

                    {/* Score Bar */}
                    <div>
                        <div className="flex justify-between text-sm mb-2">
                            <span className="text-gray-400 font-medium">Confidence</span>
                            <span className="font-bold text-white">{score}%</span>
                        </div>
                        <div className="h-2 w-full bg-[#1E2228] rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all duration-500 ${isBuy ? 'bg-gradient-to-r from-[#32D74B] to-emerald-400' :
                                        (isSell ? 'bg-gradient-to-r from-[#FF453A] to-orange-400' :
                                            'bg-gradient-to-r from-[#0A84FF] to-cyan-400')
                                    }`}
                                style={{ width: `${score}%` }}
                            />
                        </div>
                    </div>
                </div>

                {/* Action Button */}
                {onAction && (
                    <button
                        onClick={() => onAction(symbol)}
                        className="btn-secondary mt-5 w-full py-2.5 text-sm font-medium"
                    >
                        {actionLabel}
                    </button>
                )}
            </div>
        </div>
    );
};

export default SignalCard;
