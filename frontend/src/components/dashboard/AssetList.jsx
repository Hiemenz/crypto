
import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const formatPrice = (p) => p < 1 ? p?.toFixed(5) : p?.toLocaleString(undefined, { maximumFractionDigits: 2 });

const AssetList = ({ assets, selectedSymbol, onSelect }) => {
    return (
        <div className="flex-1 overflow-y-auto">
            {assets.map((item) => {
                const isSelected = selectedSymbol === item.symbol;
                const isBuy = item.side === 'buy';
                const isSell = item.side === 'sell';

                return (
                    <div
                        key={item.symbol}
                        onClick={() => onSelect(item)}
                        className={`
                            flex items-center justify-between p-4 cursor-pointer border-b border-border-subtle transition-all duration-200
                            ${isSelected ? 'bg-active border-l-4 border-l-trade-accent' : 'hover:bg-hover bg-panel'}
                        `}
                    >
                        <div className="flex items-center gap-3">


                            <div>
                                <h3 className={`font-bold text-sm ${isSelected ? 'text-white' : 'text-primary'}`}>
                                    {item.symbol}
                                </h3>
                                <div className="flex items-center gap-1.5 mt-0.5">
                                    <span className={`text-[11px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-sm ${isBuy ? 'bg-trade-up/20 text-trade-up' :
                                        isSell ? 'bg-trade-down/20 text-trade-down' :
                                            'bg-muted/20 text-muted'
                                        }`}>
                                        {item.side}
                                    </span>
                                </div>
                            </div>
                        </div>

                        <div className="text-right">
                            <div className="font-mono font-medium text-white text-[15px]">
                                ${formatPrice(item.Close)}
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

export default AssetList;
