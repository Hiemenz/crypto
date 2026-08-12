import React, { useState } from 'react';

const SIDE_COLORS = {
    buy: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    sell: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
    hold: 'bg-slate-700/40 text-slate-400 border-slate-600/30',
};

const SignalBadge = ({ item, onClick }) => {
    const colors = SIDE_COLORS[item.side] || SIDE_COLORS.hold;
    return (
        <button
            onClick={() => onClick && onClick(item.symbol)}
            className={`
                inline-flex flex-col items-start px-2 py-1.5 rounded border text-xs font-mono
                transition-all hover:scale-105 cursor-pointer ${colors}
            `}
            title={`${item.signal} | RSI: ${item.rsi?.toFixed(1) ?? '—'} | $${item.close?.toLocaleString() ?? '—'}`}
        >
            <span className="font-bold text-[11px]">{item.symbol.replace('-USD', '').replace('-B', '')}</span>
            <span className="text-[9px] opacity-70 truncate max-w-[60px]">
                {item.signal === 'Hold' ? '—' : item.signal}
            </span>
        </button>
    );
};

const SectorBlock = ({ sector, items, onSelect }) => {
    const buys = items.filter(i => i.side === 'buy').length;
    const sells = items.filter(i => i.side === 'sell').length;
    const sentiment = buys > sells ? 'bullish' : sells > buys ? 'bearish' : 'neutral';
    const sentimentColor = sentiment === 'bullish' ? 'text-emerald-400' : sentiment === 'bearish' ? 'text-rose-400' : 'text-slate-400';

    return (
        <div className="bg-panel border border-border-subtle rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold text-primary truncate max-w-[200px]">{sector}</h3>
                <span className={`text-[10px] font-mono ${sentimentColor}`}>
                    {buys}↑ {sells}↓
                </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
                {items.map(item => (
                    <SignalBadge key={item.symbol} item={item} onClick={onSelect} />
                ))}
            </div>
        </div>
    );
};

const HeatMapView = ({ heatmapData, activeTab, onSelectSymbol }) => {
    const [filter, setFilter] = useState('all'); // 'all' | 'buy' | 'sell' | 'hold'

    if (!heatmapData) {
        return (
            <div className="flex items-center justify-center h-64 text-muted text-sm">
                Loading heat map…
            </div>
        );
    }

    const filterBadge = (item) =>
        filter === 'all' || item.side === filter;

    if (activeTab === 'crypto') {
        const items = (heatmapData.crypto || []).filter(filterBadge);
        return (
            <div className="p-4 space-y-4">
                <FilterBar filter={filter} setFilter={setFilter} />
                <div className="bg-panel border border-border-subtle rounded-lg p-4">
                    <div className="flex flex-wrap gap-2">
                        {items.length === 0 ? (
                            <span className="text-muted text-sm">No signals match the filter.</span>
                        ) : items.map(item => (
                            <SignalBadge key={item.symbol} item={item} onClick={onSelectSymbol} />
                        ))}
                    </div>
                </div>
                <Legend />
            </div>
        );
    }

    // Stocks: sector grid
    const sectors = heatmapData.stocks || {};
    const filteredSectors = Object.fromEntries(
        Object.entries(sectors)
            .map(([s, items]) => [s, items.filter(filterBadge)])
            .filter(([, items]) => items.length > 0)
            .sort(([, a], [, b]) => {
                const score = arr => arr.filter(i => i.side === 'buy').length - arr.filter(i => i.side === 'sell').length;
                return score(b) - score(a);
            })
    );

    return (
        <div className="p-4 space-y-4">
            <FilterBar filter={filter} setFilter={setFilter} />
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {Object.entries(filteredSectors).map(([sector, items]) => (
                    <SectorBlock
                        key={sector}
                        sector={sector}
                        items={items}
                        onSelect={onSelectSymbol}
                    />
                ))}
            </div>
            <Legend />
        </div>
    );
};

const FilterBar = ({ filter, setFilter }) => (
    <div className="flex items-center gap-2">
        <span className="text-xs text-muted">Filter:</span>
        {['all', 'buy', 'sell', 'hold'].map(f => (
            <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 text-xs font-bold rounded-md transition-all capitalize
                    ${filter === f
                        ? f === 'buy' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                            : f === 'sell' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                                : 'bg-white text-black'
                        : 'text-muted border border-border-subtle hover:text-white'
                    }`}
            >
                {f}
            </button>
        ))}
    </div>
);

const Legend = () => (
    <div className="flex items-center gap-4 text-[11px] text-muted pt-1">
        <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-emerald-500/30 border border-emerald-500/40 inline-block" />
            Buy signal
        </span>
        <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-rose-500/30 border border-rose-500/40 inline-block" />
            Sell signal
        </span>
        <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-slate-700/50 border border-slate-600/40 inline-block" />
            Hold
        </span>
        <span className="ml-auto">Click a badge to view chart</span>
    </div>
);

export default HeatMapView;
